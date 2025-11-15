# Sales Agent (LLM + Analytics)

This project provides a lightweight agent layer on top of your `WideWorldImporters_Base` database. It runs SQL to compute ROI-related metrics, plots them, and uses an LLM (OpenAI) to summarize insights. A simple FastAPI web UI is included.

## Setup

1. Create a Python virtual environment and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set required environment variables (example):

```bash
export OPENAI_API_KEY="sk-..."
export DB_DRIVER="ODBC Driver 18 for SQL Server"
export DB_SERVER="pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com"
export DB_PORT=1433
export DB_NAME="WideWorldImporters_Base"
export DB_USER="hackathon_ro_08"
export DB_PASSWORD="vN1#sTb9"
```

3. Run the FastAPI app:

```bash
cd agent_project
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

4. Open the UI in your browser:

```
http://localhost:8000/
```

## Endpoints

- `GET /api/roi` - returns the ROI PNG image
- `POST /api/ask` - JSON `{ "question": "..." }` returns `{ summary, plot }`

## Notes

- The agent uses OpenAI; set `OPENAI_API_KEY` to enable text summaries.
- The ROI computation is a simple start: revenue from invoice lines, COGS from stock item cost. Update `analytics.py` if you have more accurate cost data.
- For production, secure environment variables and consider using a caching layer and rate limits for LLM calls.

*** End of README.md
