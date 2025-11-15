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

print("[INFO] Testing app import...")
try:
    import app
    print("[OK] App imported successfully!")
    print("[INFO] Starting server...")
    
    import uvicorn
    uvicorn.run(app.app, host="0.0.0.0", port=8000, log_level="info")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


