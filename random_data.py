import pandas as pd
import numpy as np

# Set a seed for reproducibility
np.random.seed(42)

# Sample lists for generating random names and locations
first_names = ['John', 'Jane', 'Michael', 'Michelle', 'Chris', 'Katy', 'James', 'Linda', 'Robert', 'Patricia']
last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix']
states = ['NY', 'CA', 'IL', 'TX', 'AZ']

data = []
for i in range(1, 101):
    first = np.random.choice(first_names)
    last = np.random.choice(last_names)
    city = np.random.choice(cities)
    state = np.random.choice(states)
    email = f"{first.lower()}.{last.lower()}@example.com"
    phone = f"({np.random.randint(200,1000)}) {np.random.randint(200,1000)}-{np.random.randint(1000,10000)}"
    data.append([i, first, last, email, city, state, phone])

columns = ['CustomerID', 'FirstName', 'LastName', 'Email', 'City', 'State', 'Phone']
customers = pd.DataFrame(data, columns=columns)

# Save the dataset to an Excel file
customers.to_excel('100_customers.xlsx', index=False)

print("Excel file '100_customers.xlsx' with 100 people data generated successfully!")
print(customers.head())
