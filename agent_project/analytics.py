import os
import pandas as pd
import pyodbc
import plotly.express as px
import plotly.io as pio
from datetime import datetime
import numpy as np

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
    df = df.loc[(df['revenue'] != 0) | (df['cogs'] != 0) | (df['gross_margin'] != 0)]
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


# =======================
# New Analytics Features
# =======================

def top_customers(start_date: str = '2023-01-01', end_date: str = None, limit: int = 10) -> pd.DataFrame:
    """Get top customers by total revenue."""
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    SELECT TOP {limit}
      c.CustomerID, c.CustomerName,
      SUM(il.ExtendedPrice) as total_revenue,
      COUNT(DISTINCT i.InvoiceID) as order_count,
      ROUND(AVG(il.ExtendedPrice), 2) as avg_order_value,
      ROUND(SUM(il.LineProfit), 2) as total_profit
    FROM [Sales].[Customers] c
    JOIN [Sales].[Invoices] i ON c.CustomerID = i.CustomerID
    JOIN [Sales].[InvoiceLines] il ON i.InvoiceID = il.InvoiceID
    WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY c.CustomerID, c.CustomerName
    ORDER BY total_revenue DESC
    """
    return run_sql(q)


def top_products(start_date: str = '2023-01-01', end_date: str = None, limit: int = 10) -> pd.DataFrame:
    """Get top products by units sold."""
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    SELECT TOP {limit}
      si.StockItemID, si.StockItemName, si.Brand,
      SUM(il.Quantity) as total_units,
      ROUND(SUM(il.ExtendedPrice), 2) as total_revenue,
      ROUND(SUM(il.LineProfit), 2) as total_profit,
      ROUND(SUM(il.LineProfit) / NULLIF(SUM(il.ExtendedPrice), 0) * 100, 2) as profit_margin_pct
    FROM [Warehouse].[StockItems] si
    JOIN [Sales].[InvoiceLines] il ON si.StockItemID = il.StockItemID
    JOIN [Sales].[Invoices] i ON i.InvoiceID = il.InvoiceID
    WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY si.StockItemID, si.StockItemName, si.Brand
    ORDER BY total_units DESC
    """
    return run_sql(q)


def salesperson_performance(start_date: str = '2023-01-01', end_date: str = None) -> pd.DataFrame:
    """Get salesperson performance metrics."""
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    SELECT
      COALESCE(p.FullName, 'Unknown') as salesperson,
      COUNT(DISTINCT i.InvoiceID) as total_invoices,
      ROUND(SUM(il.ExtendedPrice), 2) as total_revenue,
      ROUND(SUM(il.LineProfit), 2) as total_profit,
      ROUND(AVG(il.ExtendedPrice), 2) as avg_line_value,
      ROUND(SUM(il.LineProfit) / NULLIF(SUM(il.ExtendedPrice), 0) * 100, 2) as profit_margin_pct
    FROM [Sales].[Invoices] i
    JOIN [Sales].[InvoiceLines] il ON i.InvoiceID = il.InvoiceID
    LEFT JOIN [Application].[People] p ON i.SalespersonPersonID = p.PersonID
    WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY p.PersonID, p.FullName
    ORDER BY total_revenue DESC
    """
    return run_sql(q)


def customer_segmentation(start_date: str = '2023-01-01', end_date: str = None) -> pd.DataFrame:
    """Segment customers by purchase value and frequency."""
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    WITH customer_stats AS (
      SELECT
        c.CustomerID,
        c.CustomerName,
        SUM(il.ExtendedPrice) as total_spent,
        COUNT(DISTINCT i.InvoiceID) as purchase_count,
        AVG(il.ExtendedPrice) as avg_order_value
      FROM [Sales].[Customers] c
      JOIN [Sales].[Invoices] i ON c.CustomerID = i.CustomerID
      JOIN [Sales].[InvoiceLines] il ON i.InvoiceID = il.InvoiceID
      WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
      GROUP BY c.CustomerID, c.CustomerName
    )
    SELECT
      CustomerID,
      CustomerName,
      total_spent,
      purchase_count,
      ROUND(avg_order_value, 2) as avg_order_value,
      CASE
        WHEN total_spent > 500000 AND purchase_count > 50 THEN 'VIP'
        WHEN total_spent > 250000 AND purchase_count > 25 THEN 'High Value'
        WHEN total_spent > 50000 THEN 'Regular'
        ELSE 'At Risk'
      END as segment
    FROM customer_stats
    ORDER BY total_spent DESC
    """
    return run_sql(q)


def sales_by_location(start_date: str = '2023-01-01', end_date: str = None, limit: int = 100) -> pd.DataFrame:
    """Aggregate revenue by customer delivery city/state/country with lat/long if available."""
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')
    q = f"""
    SELECT TOP {limit}
      ct.CityName,
      sp.StateProvinceName,
      co.CountryName,
      SUM(il.ExtendedPrice) AS total_revenue,
      COUNT(DISTINCT i.InvoiceID) AS invoice_count,
      COUNT(DISTINCT i.CustomerID) AS unique_customers,
      AVG(CASE WHEN ct.Location IS NOT NULL THEN ct.Location.Lat ELSE NULL END) AS latitude,
      AVG(CASE WHEN ct.Location IS NOT NULL THEN ct.Location.Long ELSE NULL END) AS longitude
    FROM [Sales].[Invoices] i
    JOIN [Sales].[Customers] c ON c.CustomerID = i.CustomerID
    JOIN [Application].[Cities] ct ON ct.CityID = c.DeliveryCityID
    JOIN [Application].[StateProvinces] sp ON sp.StateProvinceID = ct.StateProvinceID
    JOIN [Application].[Countries] co ON co.CountryID = sp.CountryID
    JOIN [Sales].[InvoiceLines] il ON il.InvoiceID = i.InvoiceID
    WHERE i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
      AND co.CountryName IN ('United States', 'United States of America')
    GROUP BY ct.CityName, sp.StateProvinceName, co.CountryName
    ORDER BY total_revenue DESC
    """
    return run_sql(q)


def plot_bar_chart(df: pd.DataFrame, x: str, y: str, title: str, out_path: str, color: str = None):
    """Create a bar chart and export as PNG."""
    if df.empty:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=20))
        fig.update_layout(title=title)
    else:
        fig = px.bar(df, x=x, y=y, title=title, color=color or x,
                    labels={x: x.replace('_', ' ').title(), y: y.replace('_', ' ').title()},
                    template='plotly_white')
        fig.update_layout(height=600, showlegend=False)
    
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    pio.write_image(fig, out_path, scale=2, width=1400, height=800)
    return out_path


def product_monthly_units(stock_item_id: int, start_date: str, end_date: str) -> pd.DataFrame:
    """Get monthly units sold for a specific stock item."""
    q = f"""
    SELECT
      DATEFROMPARTS(YEAR(i.InvoiceDate), MONTH(i.InvoiceDate), 1) AS [month],
      si.StockItemID,
      si.StockItemName,
      SUM(il.Quantity) AS total_units
    FROM [Sales].[InvoiceLines] il
    JOIN [Sales].[Invoices] i ON i.InvoiceID = il.InvoiceID
    JOIN [Warehouse].[StockItems] si ON si.StockItemID = il.StockItemID
    WHERE il.StockItemID = {stock_item_id}
      AND i.InvoiceDate BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY DATEFROMPARTS(YEAR(i.InvoiceDate), MONTH(i.InvoiceDate), 1), si.StockItemID, si.StockItemName
    ORDER BY [month]
    """
    return run_sql(q)


def forecast_product_demand(stock_item_id: int = None, start_date: str = '2015-01-01',
                            end_date: str = None, months_ahead: int = 6) -> dict:
    """Forecast future product demand using simple linear trend."""
    end_date = end_date or datetime.utcnow().strftime('%Y-%m-%d')

    if not stock_item_id:
        top = top_products(start_date, end_date, limit=1)
        if top.empty:
            raise RuntimeError('No products available for forecasting')
        stock_item_id = int(top.iloc[0]['StockItemID'])

    history_df = product_monthly_units(stock_item_id, start_date, end_date)
    if history_df.empty:
        raise RuntimeError('No historical data for selected product')

    history_df['month'] = pd.to_datetime(history_df['month'])
    history_df = history_df.sort_values('month')
    stock_item_name = history_df.iloc[0]['StockItemName']

    x = np.arange(len(history_df))
    y = history_df['total_units'].values.astype(float)
    if len(x) >= 2:
        slope, intercept = np.polyfit(x, y, 1)
    else:
        slope, intercept = 0.0, y[0]

    recent_window = min(6, len(history_df))
    recent_avg = history_df['total_units'].tail(recent_window).mean()
    min_floor = recent_avg * 0.6

    last_month = history_df['month'].iloc[-1]
    forecast = []
    for step in range(1, months_ahead + 1):
        future_month = (last_month + pd.offsets.MonthBegin(step)).normalize()
        future_index = len(history_df) + (step - 1)
        trend_value = slope * future_index + intercept
        blended = 0.7 * trend_value + 0.3 * recent_avg
        value = max(min_floor, blended)
        forecast.append({'month': future_month, 'units': float(value)})

    history = [{'month': row['month'], 'units': float(row['total_units'])} for _, row in history_df.iterrows()]

    return {
        'stock_item': {'id': int(stock_item_id), 'name': stock_item_name},
        'history': history,
        'forecast': forecast,
        'start_date': start_date,
        'end_date': end_date,
        'explanation': 'Baseline linear trend forecast blended with recent performance.'
    }


def get_unpaid_invoices(days_overdue: int = 0, limit: int = 100) -> pd.DataFrame:
    """
    Get customers with unpaid invoices (OutstandingBalance > 0).
    
    Args:
        days_overdue: Minimum days past payment terms (0 = all unpaid)
        limit: Maximum number of records to return
    
    Returns:
        DataFrame with customer info, invoice details, and contact information
    """
    query = f"""
    SELECT TOP {limit}
        c.CustomerID,
        c.CustomerName,
        c.PhoneNumber,
        c.PaymentDays,
        p.EmailAddress AS ContactEmail,
        p.FullName AS ContactName,
        ct.InvoiceID,
        ct.TransactionDate,
        ct.TransactionAmount,
        ct.OutstandingBalance,
        DATEDIFF(DAY, DATEADD(DAY, c.PaymentDays, ct.TransactionDate), GETDATE()) AS DaysOverdue,
        i.InvoiceDate,
        salesperson.FullName AS SalespersonName,
        salesperson.EmailAddress AS SalespersonEmail
    FROM [Sales].[CustomerTransactions] ct
    INNER JOIN [Sales].[Customers] c ON ct.CustomerID = c.CustomerID
    LEFT JOIN [Application].[People] p ON c.PrimaryContactPersonID = p.PersonID
    LEFT JOIN [Sales].[Invoices] i ON ct.InvoiceID = i.InvoiceID
    LEFT JOIN [Application].[People] salesperson ON i.SalespersonPersonID = salesperson.PersonID
    WHERE ct.OutstandingBalance > 0
        AND ct.IsFinalized = 1
        AND DATEDIFF(DAY, DATEADD(DAY, c.PaymentDays, ct.TransactionDate), GETDATE()) >= {days_overdue}
    ORDER BY ct.OutstandingBalance DESC, ct.TransactionDate ASC;
    """
    return run_sql(query)