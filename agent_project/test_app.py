import os
import sys

# Set environment variables
os.environ['OPENAI_API_KEY'] = 'sk-placeholder'
os.environ['DB_DRIVER'] = 'ODBC Driver 18 for SQL Server'
os.environ['DB_SERVER'] = 'pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com'
os.environ['DB_PORT'] = '1433'
os.environ['DB_NAME'] = 'WideWorldImporters_Base'
os.environ['DB_USER'] = 'hackathon_ro_08'
os.environ['DB_PASSWORD'] = 'vN1#sTb9'

print("Testing imports...")
try:
    print("1. Importing FastAPI...")
    from fastapi import FastAPI
    print("   [OK] FastAPI")
    
    print("2. Importing uvicorn...")
    import uvicorn
    print("   [OK] uvicorn")
    
    print("3. Importing app module...")
    import app
    print("   [OK] app module")
    
    print("\n[SUCCESS] All imports successful!")
    print("\nStarting uvicorn server on http://0.0.0.0:8000")
    uvicorn.run(app.app, host="0.0.0.0", port=8000)
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

