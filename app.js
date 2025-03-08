let activeTableName = null;
let activeColumns = [];
let activeSuggestions = [];
let chartInstance = null; // for aggregator chart reuse

// 1) Upload
document.getElementById('uploadBtn').addEventListener('click', uploadFile);

async function uploadFile() {
  const fileInput = document.getElementById('fileInput');
  const uploadMessage = document.getElementById('uploadMessage');
  const columnsList = document.getElementById('columnsList');
  const suggestionsList = document.getElementById('suggestionsList');

  // Reset
  uploadMessage.textContent = '';
  columnsList.textContent = 'No columns yet.';
  suggestionsList.innerHTML = '';
  activeTableName = null;
  activeColumns = [];
  activeSuggestions = [];

  if (fileInput.files.length === 0) {
    uploadMessage.textContent = 'Please select a file first.';
    uploadMessage.classList.add('error');
    return;
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const response = await fetch('/upload', {
      method: 'POST',
      body: formData
    });
    const data = await response.json();

    if (!response.ok) {
      uploadMessage.textContent = data.error || 'Upload failed.';
      uploadMessage.classList.add('error');
      return;
    }

    uploadMessage.textContent = data.message || 'File uploaded successfully!';
    uploadMessage.classList.remove('error');
    uploadMessage.classList.add('success');

    // Store table info
    activeTableName = data.table_name;
    activeColumns = data.columns;
    activeSuggestions = data.suggestions || [];

    // Show columns
    if (activeColumns.length > 0) {
      columnsList.textContent = activeColumns.join(', ');
    } else {
      columnsList.textContent = 'No columns detected.';
    }

    // Render suggestions
    renderSuggestions(activeSuggestions);

  } catch (error) {
    uploadMessage.textContent = 'Error uploading file: ' + error;
    uploadMessage.classList.add('error');
  }
}

function renderSuggestions(suggestions) {
  const suggestionsList = document.getElementById('suggestionsList');
  suggestionsList.innerHTML = '';

  if (suggestions.length === 0) {
    suggestionsList.textContent = 'No suggestions generated.';
    return;
  }

  const ul = document.createElement('ul');
  suggestions.forEach(sugg => {
    const li = document.createElement('li');
    li.textContent = sugg;
    li.classList.add('suggestion-item');
    li.addEventListener('click', () => {
      document.getElementById('queryInput').value = sugg;
    });
    ul.appendChild(li);
  });
  suggestionsList.appendChild(ul);
}

// 2) Handle English Query
document.getElementById('queryBtn').addEventListener('click', handleQuery);

async function handleQuery() {
  const queryInput = document.getElementById('queryInput');
  const queryMessage = document.getElementById('queryMessage');
  const resultsDiv = document.getElementById('results');
  const chartCanvas = document.getElementById('chartCanvas');

  // Reset
  queryMessage.textContent = '';
  resultsDiv.innerHTML = '';
  chartCanvas.style.display = 'none';

  if (!activeTableName) {
    queryMessage.textContent = 'Please upload a file first.';
    queryMessage.classList.add('error');
    return;
  }

  if (queryInput.value.trim() === '') {
    queryMessage.textContent = 'Please enter a query.';
    queryMessage.classList.add('error');
    return;
  }

  try {
    const response = await fetch('/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: queryInput.value,
        table_name: activeTableName
      })
    });
    const data = await response.json();

    if (!response.ok) {
      queryMessage.textContent = data.error || 'Query failed.';
      queryMessage.classList.add('error');
      return;
    }

    // If invalid format or correction needed
    if (data.sql === 'Invalid query format') {
      queryMessage.textContent = 'Invalid query format.';
      queryMessage.classList.add('error');

      if (data.corrected) {
        queryMessage.textContent += ` Did you mean: "${data.corrected}"?`;
      }
      return;
    }

    // Show the generated SQL
    queryMessage.textContent = `SQL: ${data.sql}`;
    queryMessage.classList.remove('error');
    queryMessage.classList.add('success');

    // Render results
    if (data.rows && data.columns) {
      if (data.rows.length === 0) {
        resultsDiv.innerHTML = '<p>No rows returned.</p>';
      } else {
        renderTable(data.columns, data.rows, resultsDiv);
        // aggregator queries often return 2 columns => draw bar chart
        if (data.columns.length === 2) {
          renderBarChart(data.columns, data.rows, chartCanvas);
        }
      }
    }
  } catch (error) {
    queryMessage.textContent = 'Error processing query: ' + error;
    queryMessage.classList.add('error');
  }
}

// 3) SQL Playground
document.getElementById('rawSqlBtn').addEventListener('click', handleRawSQL);

async function handleRawSQL() {
  const rawSqlInput = document.getElementById('rawSqlInput');
  const rawSqlMessage = document.getElementById('rawSqlMessage');
  const rawSqlResults = document.getElementById('rawSqlResults');

  rawSqlMessage.textContent = '';
  rawSqlResults.innerHTML = '';

  if (!rawSqlInput.value.trim()) {
    rawSqlMessage.textContent = 'Please enter a SQL statement.';
    rawSqlMessage.classList.add('error');
    return;
  }

  try {
    const response = await fetch('/execute_sql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_sql: rawSqlInput.value })
    });
    const data = await response.json();

    if (!response.ok) {
      rawSqlMessage.textContent = data.error || 'SQL execution failed.';
      rawSqlMessage.classList.add('error');
      return;
    }

    rawSqlMessage.textContent = 'SQL executed successfully!';
    rawSqlMessage.classList.remove('error');
    rawSqlMessage.classList.add('success');

    if (data.rows && data.columns) {
      if (data.rows.length === 0) {
        rawSqlResults.innerHTML = '<p>No rows returned.</p>';
      } else {
        renderTable(data.columns, data.rows, rawSqlResults);
      }
    }
  } catch (error) {
    rawSqlMessage.textContent = 'Error executing SQL: ' + error;
    rawSqlMessage.classList.add('error');
  }
}

// Helper: Render Table
function renderTable(columns, rows, container) {
  let tableHTML = '<table><thead><tr>';
  columns.forEach(col => {
    tableHTML += `<th>${col}</th>`;
  });
  tableHTML += '</tr></thead><tbody>';

  rows.forEach(row => {
    tableHTML += '<tr>';
    row.forEach(cell => {
      tableHTML += `<td>${cell}</td>`;
    });
    tableHTML += '</tr>';
  });

  tableHTML += '</tbody></table>';
  container.innerHTML = tableHTML;
}

// Helper: Render Bar Chart
function renderBarChart(columns, rows, chartCanvas) {
  // Cleanup old chart
  if (chartInstance) {
    chartInstance.destroy();
  }

  chartCanvas.style.display = 'block';
  const labels = rows.map(r => r[0]);
  const values = rows.map(r => r[1]);

  chartInstance = new Chart(chartCanvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: columns[1],
        data: values,
        backgroundColor: 'rgba(54, 162, 235, 0.6)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1
      }]
    },
    options: {
      scales: {
        y: { beginAtZero: true }
      }
    }
  });
}
