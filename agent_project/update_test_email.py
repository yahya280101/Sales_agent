import os
import sys

# Set environment variables (same as run_server.py)
os.environ['DB_DRIVER'] = 'ODBC Driver 18 for SQL Server'
os.environ['DB_SERVER'] = 'pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com'
os.environ['DB_PORT'] = '1433'
os.environ['DB_NAME'] = 'WideWorldImporters_Base'
os.environ['DB_USER'] = 'hackathon_ro_08'
os.environ['DB_PASSWORD'] = 'vN1#sTb9'

from analytics import get_conn, run_sql

print("Fetching first customer with email...")

# Get the first customer
query = """
SELECT TOP 1
    c.CustomerID,
    c.CustomerName,
    c.PrimaryContactPersonID,
    p.PersonID,
    p.FullName AS ContactName,
    p.EmailAddress AS CurrentEmail
FROM Sales.Customers c
LEFT JOIN Application.People p ON c.PrimaryContactPersonID = p.PersonID
WHERE p.EmailAddress IS NOT NULL
ORDER BY c.CustomerName
"""

df = run_sql(query)

if df.empty:
    print("No customers found with email addresses!")
    sys.exit(1)

customer = df.iloc[0]
print(f"\nFirst Customer:")
print(f"  Customer ID: {customer['CustomerID']}")
print(f"  Customer Name: {customer['CustomerName']}")
print(f"  Contact Name: {customer['ContactName']}")
print(f"  Contact Person ID: {customer['PrimaryContactPersonID']}")
print(f"  Current Email: {customer['CurrentEmail']}")

# Update the email address
new_email = 'mundisgl@gmail.com'
person_id = int(customer['PrimaryContactPersonID'])

print(f"\nUpdating email to: {new_email}")

update_query = f"""
UPDATE Application.People
SET EmailAddress = '{new_email}'
WHERE PersonID = {person_id}
"""

try:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(update_query)
    conn.commit()
    print(f"✅ Successfully updated email address!")
    print(f"\nCustomer '{customer['CustomerName']}' contact email is now: {new_email}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ Error updating email: {e}")
    sys.exit(1)

print("\n✨ You can now test sending emails to this customer in the Email Center!")
print("   They will be delivered to mundisgl@gmail.com")

