import os
import re
import random
import string
import sqlite3
import difflib
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='')

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Store info about each uploaded table
active_tables = {}  # { table_name: { 'columns': [...], 'suggestions': [...] } }

def generate_table_name():
    """Generate a random table name like 'table_ab12xy'."""
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"table_{suffix}"

@app.route('/')
def index():
    return send_from_directory('', 'index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Upload CSV/XLSX, create a unique table in SQLite, build suggestions."""
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = file.filename
    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Unique table name
    table_name = generate_table_name()

    # Read CSV or XLSX
    try:
        if filename.lower().endswith('.csv'):
            df = pd.read_csv(file_path)
        elif filename.lower().endswith('.xlsx'):
            df = pd.read_excel(file_path, engine='openpyxl')
        else:
            return jsonify({"error": "Unsupported file type"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {e}"}), 400

    # Write to SQLite
    db_path = os.path.join(UPLOAD_FOLDER, 'data.db')
    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(table_name, conn, if_exists='replace', index=False)
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Failed to create table: {e}"}), 400
    conn.close()

    columns = list(df.columns)
    suggestions = build_suggestions(columns, df)

    active_tables[table_name] = {
        'columns': columns,
        'suggestions': suggestions
    }

    return jsonify({
        "message": f"File uploaded and table '{table_name}' created successfully!",
        "table_name": table_name,
        "columns": columns,
        "suggestions": suggestions
    })

def build_suggestions(columns, df):
    """
    Generate dynamic queries: "Show <col> in <val>", "Total <num> by <cat>",
    "Count <col> by <cat>", "Average <num> by <cat>", plus "Show all data".
    """
    suggestions = ["Show all data"]
    numeric_cols = []
    categorical_cols = []

    for col in columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
        else:
            categorical_cols.append(col)

    # "Show <col> in <val>" for first 3 unique values in each categorical col
    for col in categorical_cols:
        unique_vals = df[col].dropna().unique()[:3]
        for val in unique_vals:
            suggestions.append(f"Show {col} in {val}")

    # Aggregators: total, count, average
    for num_col in numeric_cols[:2]:
        for cat_col in categorical_cols[:2]:
            suggestions.append(f"Total {num_col} by {cat_col}")
            suggestions.append(f"Count {cat_col} by {num_col}")  # just an example
            suggestions.append(f"Average {num_col} by {cat_col}")

    return suggestions

def sanitize_input(user_input: str) -> str:
    """Remove quotes/semicolons to reduce SQL injection risk."""
    return re.sub(r"[;'\"]", "", user_input)

def fuzzy_match_column(user_col, actual_cols):
    """Use difflib to find the closest matching column name."""
    user_col = user_col.strip()
    candidates = difflib.get_close_matches(user_col, actual_cols, n=1, cutoff=0.6)
    if candidates:
        return candidates[0]
    return None

def translate_query_to_sql(query_text, table_name):
    """
    Extended patterns:
      - "Show all data"
      - "Show X in Y"       => SELECT * FROM table WHERE LOWER("X") = LOWER('Y')
      - "Total X by Y"      => SELECT "Y", SUM("X") FROM table GROUP BY "Y"
      - "Count X by Y"      => SELECT "Y", COUNT("X") FROM table GROUP BY "Y"
      - "Average X by Y"    => SELECT "Y", AVG("X") FROM table GROUP BY "Y"
    """
    query_text = sanitize_input(query_text.lower())
    table_info = active_tables.get(table_name, {})
    columns = table_info.get('columns', [])

    # 1) "Show all data"
    if re.search(r"show all data", query_text):
        return f"SELECT * FROM {table_name}"

    # 2) "Show X in Y"
    match_filter = re.search(r"show (.*) in (.*)", query_text)
    if match_filter:
        col_user = match_filter.group(1).strip()
        val_user = match_filter.group(2).strip()
        col_matched = fuzzy_match_column(col_user, columns)
        if col_matched:
            val_user = sanitize_input(val_user)
            col_matched_quoted = f'"{col_matched}"'
            return (f"SELECT * FROM {table_name} "
                    f"WHERE LOWER({col_matched_quoted}) = LOWER('{val_user}')")
        else:
            return "Invalid query format"

    # 3) Aggregators
    # e.g., "Total X by Y", "Count X by Y", "Average X by Y"
    # We'll unify them in a single pattern with group(1) = aggregator, group(2)= colSum, group(3)= colGroup
    match_agg = re.search(r"(total|count|average)\s+(.*)\s+by\s+(.*)", query_text)
    if match_agg:
        agg_op = match_agg.group(1).strip()     # total|count|average
        col_sum_user = match_agg.group(2).strip()
        col_group_user = match_agg.group(3).strip()

        col_sum_matched = fuzzy_match_column(col_sum_user, columns)
        col_group_matched = fuzzy_match_column(col_group_user, columns)
        if col_sum_matched and col_group_matched:
            col_sum_quoted = f'"{col_sum_matched}"'
            col_group_quoted = f'"{col_group_matched}"'

            if agg_op == 'total':
                return (f"SELECT {col_group_quoted}, SUM({col_sum_quoted}) "
                        f"FROM {table_name} GROUP BY {col_group_quoted}")
            elif agg_op == 'count':
                return (f"SELECT {col_sum_quoted}, COUNT(*) "
                        f"FROM {table_name} GROUP BY {col_sum_quoted}")
            elif agg_op == 'average':
                return (f"SELECT {col_group_quoted}, AVG({col_sum_quoted}) "
                        f"FROM {table_name} GROUP BY {col_group_quoted}")
        else:
            return "Invalid query format"

    return "Invalid query format"

def attempt_correction(query_text, table_name):
    """
    If we get "Invalid query format," we try to guess a corrected query:
    1) Check if user typed "show all <val> in <col>" reversed pattern.
    2) Check minor spelling differences from known aggregator keywords.
    3) If we can guess a fix, return that. Otherwise, return None.
    """
    # Example: user typed "Show all male in Sex" instead of "Show Sex in male"
    # We'll do a quick pattern check: "show all (.*) in (.*)"
    match_reversed = re.search(r"show all (.*) in (.*)", query_text.lower())
    if match_reversed:
        val_user = match_reversed.group(1).strip()
        col_user = match_reversed.group(2).strip()
        # We'll guess the corrected query is "Show col_user in val_user"
        corrected = f"Show {col_user} in {val_user}"
        return corrected

    # Additional checks: e.g., user typed "totl" or "avrage"
    # We'll do a quick difflib on aggregator keywords
    aggregator_keywords = ["total", "count", "average"]
    tokens = query_text.split()
    corrected_tokens = []
    changed = False
    for token in tokens:
        # If token is close to aggregator keywords
        candidates = difflib.get_close_matches(token, aggregator_keywords, n=1, cutoff=0.8)
        if candidates:
            corrected_tokens.append(candidates[0])
            changed = True
        else:
            corrected_tokens.append(token)
    if changed:
        corrected_query = " ".join(corrected_tokens)
        return corrected_query

    return None

@app.route('/translate', methods=['POST'])
def translate_query():
    """Translate English -> SQL, attempt correction if invalid, then run."""
    data = request.get_json()
    query_text = data.get('query', '')
    table_name = data.get('table_name', '')

    if not table_name or table_name not in active_tables:
        return jsonify({"error": "Invalid or missing table name."}), 400

    sql_query = translate_query_to_sql(query_text, table_name)
    if sql_query == "Invalid query format":
        # Try correction
        corrected = attempt_correction(query_text, table_name)
        return jsonify({
            "sql": sql_query,
            "corrected": corrected  # might be None if no fix found
        }), 200

    # If valid, run it
    db_path = os.path.join(UPLOAD_FOLDER, 'data.db')
    if not os.path.exists(db_path):
        return jsonify({"error": "No database found. Please upload a file first."}), 400

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        conn.close()

        return jsonify({
            "sql": sql_query,
            "rows": rows,
            "columns": col_names
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/execute_sql', methods=['POST'])
def execute_sql():
    """Directly execute raw SQL from the user (SQL Playground)."""
    data = request.get_json()
    raw_sql = data.get('raw_sql', '')

    db_path = os.path.join(UPLOAD_FOLDER, 'data.db')
    if not os.path.exists(db_path):
        return jsonify({"error": "No database found. Please upload a file first."}), 400

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(raw_sql)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        conn.close()

        return jsonify({
            "rows": rows,
            "columns": col_names
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
