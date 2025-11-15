@echo off
set OPENAI_API_KEY=sk-placeholder
set DB_DRIVER=ODBC Driver 18 for SQL Server
set DB_SERVER=pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com
set DB_PORT=1433
set DB_NAME=WideWorldImporters_Base
set DB_USER=hackathon_ro_08
set DB_PASSWORD=vN1#sTb9

cd /d "C:\Users\mundi\Desktop\Pepsico2\Sales_agent\agent_project"
C:\Python312\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause

