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

# SMTP Email Configuration
os.environ['SMTP_SERVER'] = 'smtp.gmail.com'
os.environ['SMTP_PORT'] = '587'
os.environ['SMTP_USERNAME'] = 't60029350@gmail.com'
os.environ['SMTP_PASSWORD'] = 'tfyenebmjhkhlxdf'  # Gmail App Password (spaces removed)

print("[INFO] Environment configured")
print("[INFO] Python:", sys.executable)
print("[INFO] Starting server...")

try:
    import uvicorn
    print("[OK] uvicorn imported")
    
    import app
    print("[OK] app module imported")
    
    print("\n" + "="*60)
    print("SERVER STARTING ON http://0.0.0.0:8000")
    print("="*60 + "\n")
    
    uvicorn.run(app.app, host="0.0.0.0", port=8000, log_level="info")
    
except Exception as e:
    print(f"\n[ERROR] Failed to start: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


