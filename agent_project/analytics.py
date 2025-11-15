import os
import pandas as pd
import pyodbc
import plotly.express as px
import plotly.io as pio
from datetime import datetime

pio.kaleido.scope.default_format = "png"


def get_conn():
    """Create a pyodbc connection using env vars.

    Required env vars: DB_DRIVER, DB_SERVER, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    """
    driver = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')
    server = os.getenv('DB_SERVER')
    port = os.getenv('DB_PORT', '1433')
    database = os.getenv('DB_NAME')
    uid = os.getenv('DB_USER')
    pwd = os.getenv('DB_PASSWORD')

    if not all([server, database, uid, pwd]):
        raise RuntimeError('Missing DB connection environment variables. Set DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD')

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={uid};PWD={pwd};"
        f"Encrypt=yes;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def run_sql(query: str) -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql(query, conn)
    finally:
        conn.close()
    return df


def monthly_revenue(start_date: str = '2023-01-01', end_date: str = None) -> pd.DataFrame:
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    SELECT
      DATEFROMPARTS(YEAR(i.InvoiceDate), MONTH(i.InvoiceDate), 1) AS [month],
      SUM(il.ExtendedPrice) AS revenue
    FROM [Sales].[Invoices] i
    JOIN [Sales].[InvoiceLines] il ON il.InvoiceID = i.InvoiceID
    WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY DATEFROMPARTS(YEAR(i.InvoiceDate), MONTH(i.InvoiceDate), 1)
    ORDER BY [month];
    """
    return run_sql(q)


def monthly_cogs(start_date: str = '2023-01-01', end_date: str = None) -> pd.DataFrame:
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    SELECT
      DATEFROMPARTS(YEAR(i.InvoiceDate), MONTH(i.InvoiceDate), 1) AS [month],
      SUM(il.Quantity * COALESCE(s.LastCostPrice, si.UnitPrice)) AS cogs
    FROM [Sales].[Invoices] i
    JOIN [Sales].[InvoiceLines] il ON il.InvoiceID = i.InvoiceID
    JOIN [Warehouse].[StockItems] si ON si.StockItemID = il.StockItemID
    LEFT JOIN [Warehouse].[StockItemHoldings] s ON s.StockItemID = si.StockItemID
    WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY DATEFROMPARTS(YEAR(i.InvoiceDate), MONTH(i.InvoiceDate), 1)
    ORDER BY [month];
    """
    return run_sql(q)


def compute_roi(start_date: str = '2023-01-01', end_date: str = None) -> pd.DataFrame:
    rev = monthly_revenue(start_date, end_date)
    cogs = monthly_cogs(start_date, end_date)
    df = pd.merge(rev, cogs, on='month', how='outer').fillna(0)
    df['gross_margin'] = df['revenue'] - df['cogs']
    # define ROI as gross_margin / cogs (avoid divide by zero)
    df['roi'] = df.apply(lambda r: (r['gross_margin'] / r['cogs']) if r['cogs'] else None, axis=1)
    df = df.sort_values('month')
    return df


def plot_timeseries(df: pd.DataFrame, y_cols: list, title: str, out_path: str):
    """Create a line chart with multiple series and export as PNG."""
    if df.empty or len(df) == 0:
        # Create empty placeholder plot
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=20))
        fig.update_layout(title=title, xaxis_title="Month", yaxis_title="Value")
    else:
        # Ensure month is datetime for proper x-axis
        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df['month']):
            df['month'] = pd.to_datetime(df['month'])
        
        fig = px.line(df, x='month', y=y_cols, markers=True, title=title,
                     labels={'month': 'Month', 'value': 'Amount'},
                     line_shape='linear')
        fig.update_xaxes(tickformat="%Y-%m")
        fig.update_layout(
            legend_title_text='Metrics',
            hovermode='x unified',
            height=600,
            template='plotly_white'
        )
    
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    pio.write_image(fig, out_path, scale=2, width=1400, height=800)
    return out_path
