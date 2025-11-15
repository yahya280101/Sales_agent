# DB Schema Visualizer

Small Python project to extract database schema metadata from a SQL Server database and produce DBML and PlantUML files, plus a helper to render PlantUML to PNG via the public PlantUML server.

Files added
- `export_schema.py`: connects to the DB and writes `schema.dbml` and `schema.puml`.
- `render_plantuml.py`: renders a `.puml` to `png` using `https://www.plantuml.com/plantuml`.
- `requirements.txt`: Python dependencies.

Prerequisites (macOS / zsh)
- Python 3.8+
- ODBC driver for SQL Server (msodbcsql17 or later). Install via Homebrew if needed:
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install --no-sandbox msodbcsql17
```
- Install Python deps:
```bash
python3 -m pip install -r requirements.txt
```

Usage

1) Export DB schema files (DBML + PlantUML)
```bash
python3 export_schema.py \
  --server pepsaco-db-standard.c1oqimeoszvd.eu-west-2.rds.amazonaws.com \
  --port 1433 \
  --database WideWorldImporters_Base \
  --user hackathon_ro_08 \
  --password 'vN1#sTb9' \
  --out-prefix schema
```
This will create `schema.dbml` and `schema.puml` in the current folder.

2) Render the PlantUML to PNG (uses the public PlantUML server)
```bash
python3 render_plantuml.py schema.puml -o schema.png
```

Notes and options
- If you prefer `dbdiagram.io`, open `schema.dbml` and paste into https://dbdiagram.io.
- The public PlantUML server has size limits for very large schemas. For large databases, consider manually grouping tables or using a local PlantUML server or the PlantUML JAR.
- The script uses `pyodbc`. If you have connection or driver errors, verify your ODBC driver and driver name (change `--driver` flag if needed).

If you want, I can run these steps locally if you provide exported CSVs or run the commands and paste `schema.puml` back here — then I will render and return the PNG.
