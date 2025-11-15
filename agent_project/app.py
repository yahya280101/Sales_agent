from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
from datetime import datetime
from analytics import (
    compute_roi, plot_timeseries, plot_bar_chart,
    top_customers, top_products, salesperson_performance, customer_segmentation,
    sales_by_location, forecast_product_demand, get_unpaid_invoices
)
from agent import summarize_dataframe, forecast_with_llm, generate_email_draft
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd

app = FastAPI(title='Sales Agent')

# Create outputs directory
os.makedirs('agent_outputs', exist_ok=True)

# Create API router FIRST (before static mounts)
api_router = APIRouter()


class AskRequest(BaseModel):
    question: str
    start_date: Optional[str] = '2015-01-01'
    end_date: Optional[str] = '2016-12-31'


class EmailDraftRequest(BaseModel):
    email_type: str  # payment_reminder, product_recommendation, appreciation, etc.
    recipient_name: str
    recipient_email: str
    customer_id: Optional[int] = None
    customer_data: Optional[dict] = None
    additional_context: Optional[str] = None


class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body_html: str
    from_email: Optional[str] = None
    cc_email: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None


def describe_forecast_rows(rows):
    if not rows:
        return "No forecast insights available."

    def fmt_month(value):
        if not value:
            return "N/A"
        try:
            return datetime.fromisoformat(str(value)).strftime('%b %Y')
        except ValueError:
            try:
                return datetime.strptime(str(value), '%Y-%m').strftime('%b %Y')
            except Exception:
                return str(value)

    units = [float(r['units']) for r in rows if r.get('units') is not None]
    if not units:
        return "Forecast values unavailable."
    first = rows[0]
    last = rows[-1]
    peak = max(rows, key=lambda r: r.get('units', 0))
    trough = min(rows, key=lambda r: r.get('units', 0))
    delta = last['units'] - first['units']
    trend = 'rise' if delta >= 0 else 'decline'
    return (
        f"Demand is projected to {trend} from {first['units']:,.0f} units in {fmt_month(first['month'])} "
        f"to {last['units']:,.0f} by {fmt_month(last['month'])}. "
        f"Peak demand hits {peak['units']:,.0f} units in {fmt_month(peak['month'])}, "
        f"while the weakest month sits at {trough['units']:,.0f}."
    )


@api_router.get('/roi')
def api_roi(start_date: str = '2015-01-01', end_date: str = '2016-12-31'):
    """Generate and return ROI plot as PNG."""
    try:
        df = compute_roi(start_date, end_date)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")
        out_path = os.path.join('agent_outputs', 'roi.png')
        plot_timeseries(df, ['revenue', 'cogs', 'gross_margin'], 'Monthly Revenue / COGS / Gross Margin', out_path)
        return FileResponse(out_path, media_type='image/png')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/roi-data')
def api_roi_data(start_date: str = '2015-01-01', end_date: str = '2016-12-31'):
    """Return ROI timeseries data with summary metrics for interactive charts."""
    try:
        df = compute_roi(start_date, end_date)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")
        df = df.sort_values('month')
        records = []
        for _, row in df.iterrows():
            records.append({
                'month': row['month'].isoformat() if hasattr(row['month'], 'isoformat') else str(row['month']),
                'revenue': float(row['revenue']),
                'cogs': float(row['cogs']),
                'gross_margin': float(row['gross_margin']),
                'roi': float(row['roi']) if row['roi'] is not None else None
            })

        revenue_sum = df['revenue'].sum()
        gross_margin_sum = df['gross_margin'].sum()
        gross_margin_pct = (gross_margin_sum / revenue_sum * 100) if revenue_sum else 0
        roi_series = df['roi'].dropna()
        roi_trend = 0
        if len(roi_series) >= 2 and roi_series.iloc[0] != 0:
            roi_trend = (roi_series.iloc[-1] - roi_series.iloc[0]) / abs(roi_series.iloc[0]) * 100

        return JSONResponse({
            'data': records,
            'summary': {
                'gross_margin_pct': gross_margin_pct,
                'roi_trend_pct': roi_trend
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post('/ask')
async def api_ask(req: AskRequest):
    # compute ROI table and summarize
    df = compute_roi(req.start_date, req.end_date)
    # create a small plot and save
    os.makedirs('agent_outputs', exist_ok=True)
    plot_path = os.path.join('agent_outputs', 'roi.png')
    plot_timeseries(df, ['revenue', 'cogs', 'gross_margin'], 'Monthly Revenue / COGS / Gross Margin', plot_path)

    # Summarize via LLM
    context_parts = []
    try:
        tc = top_customers(req.start_date, req.end_date, limit=5)
        if not tc.empty:
            context_parts.append("Top customers by revenue:\n" + ", ".join(f"{row.CustomerName} (${row.total_revenue:,.0f})" for _, row in tc.iterrows()))
        tp = top_products(req.start_date, req.end_date, limit=5)
        if not tp.empty:
            context_parts.append("Top products:\n" + ", ".join(f"{row.StockItemName} ({row.total_units} units)" for _, row in tp.iterrows()))
    except Exception:
        pass
    extra_context = "\\n\\n".join(context_parts) if context_parts else None

    try:
        summary = summarize_dataframe(df, req.question, context=extra_context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({
        'summary': summary,
        'plot': '/agent_outputs/roi.png'
    })


@api_router.get('/top-customers')
def api_top_customers(start_date: str = '2015-01-01', end_date: str = '2016-12-31', limit: int = 10):
    """Get top customers by revenue with visualization."""
    try:
        df = top_customers(start_date, end_date, limit)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")

        out_path = os.path.join('agent_outputs', 'top_customers.png')
        plot_bar_chart(df, 'CustomerName', 'total_revenue', f'Top {limit} Customers by Revenue', out_path)

        return JSONResponse({
            'data': df.to_dict(orient='records'),
            'plot': '/agent_outputs/top_customers.png'
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/top-products')
def api_top_products(start_date: str = '2015-01-01', end_date: str = '2016-12-31', limit: int = 10):
    """Get top products by units sold with visualization."""
    try:
        df = top_products(start_date, end_date, limit)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")

        out_path = os.path.join('agent_outputs', 'top_products.png')
        plot_bar_chart(df, 'StockItemName', 'total_units', f'Top {limit} Products by Units Sold', out_path)

        return JSONResponse({
            'data': df.to_dict(orient='records'),
            'plot': '/agent_outputs/top_products.png'
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/salesperson-performance')
def api_salesperson_performance(start_date: str = '2015-01-01', end_date: str = '2016-12-31'):
    """Get salesperson performance metrics with visualization."""
    try:
        df = salesperson_performance(start_date, end_date)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")

        out_path = os.path.join('agent_outputs', 'salesperson_perf.png')
        plot_bar_chart(df, 'salesperson', 'total_revenue', 'Salesperson Performance by Revenue', out_path)

        return JSONResponse({
            'data': df.to_dict(orient='records'),
            'plot': '/agent_outputs/salesperson_perf.png'
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/customer-segmentation')
def api_customer_segmentation(start_date: str = '2015-01-01', end_date: str = '2016-12-31'):
    """Get customer segmentation analysis."""
    try:
        df = customer_segmentation(start_date, end_date)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")
        
        # Create visualization showing segment distribution
        segment_counts = df['segment'].value_counts().reset_index()
        segment_counts.columns = ['segment', 'count']
        
        out_path = os.path.join('agent_outputs', 'customer_segments.png')
        plot_bar_chart(segment_counts, 'segment', 'count', 'Customer Segmentation Distribution', out_path, color='segment')
        
        # Group data by segment
        segments = {}
        for segment in df['segment'].unique():
            segment_data = df[df['segment'] == segment].sort_values('total_spent', ascending=False)
            segments[segment] = segment_data.to_dict(orient='records')
        
        return JSONResponse({
            'summary': {
                'total_customers': len(df),
                'segments': {seg: len(data) for seg, data in segments.items()}
            },
            'data': segments,
            'plot': '/agent_outputs/customer_segments.png'
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/geo-sales')
def api_geo_sales(start_date: str = '2015-01-01', end_date: str = '2016-12-31', limit: int = 100):
    """Return sales aggregated by delivery city/state/country with coordinates."""
    try:
        df = sales_by_location(start_date, end_date, limit)
        if df.empty:
            raise HTTPException(status_code=400, detail="No data for the requested date range")
        return JSONResponse({
            'data': df.to_dict(orient='records'),
            'start_date': start_date,
            'end_date': end_date
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/demand-forecast')
def api_demand_forecast(stock_item_id: Optional[int] = None,
                        months_ahead: int = 6,
                        start_date: str = '2015-01-01',
                        end_date: str = '2016-12-31'):
    """Return demand forecast data for a product."""
    try:
        months_ahead = max(1, min(months_ahead, 12))
        result = forecast_product_demand(stock_item_id, start_date, end_date, months_ahead)
        history_for_llm = []
        for row in result['history']:
            month = row['month']
            if hasattr(month, 'isoformat'):
                month = month.date().isoformat()
            history_for_llm.append({'month': month, 'units': row['units']})

        explanation = result.get('explanation', '')
        try:
            llm_output = forecast_with_llm(history_for_llm, months_ahead, result['stock_item']['name'])
            result['forecast'] = [{'month': f['month'], 'units': f['units']} for f in llm_output.get('forecast', [])]
            explanation = llm_output.get('explanation', explanation)
        except Exception:
            pass

        for section in ('history', 'forecast'):
            for row in result[section]:
                if hasattr(row['month'], 'isoformat'):
                    row['month'] = row['month'].date().isoformat()
        if not explanation:
            explanation = describe_forecast_rows(result['forecast'])
        result['explanation'] = explanation
        return JSONResponse(result)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get('/customers-list')
def api_customers_list(limit: int = 100, search: Optional[str] = None):
    """Get list of customers for email recipient selection."""
    try:
        query = f"""
        SELECT TOP {limit}
            c.CustomerID,
            c.CustomerName,
            p.EmailAddress AS ContactEmail,
            p.FullName AS ContactName,
            c.PhoneNumber,
            (SELECT SUM(il.ExtendedPrice) 
             FROM Sales.Invoices i
             JOIN Sales.InvoiceLines il ON i.InvoiceID = il.InvoiceID
             WHERE i.CustomerID = c.CustomerID) AS TotalSpent
        FROM Sales.Customers c
        LEFT JOIN Application.People p ON c.PrimaryContactPersonID = p.PersonID
        WHERE p.EmailAddress IS NOT NULL
        """
        if search:
            query += f" AND (c.CustomerName LIKE '%{search}%' OR p.FullName LIKE '%{search}%')"
        query += " ORDER BY c.CustomerName"
        
        from analytics import run_sql
        df = run_sql(query)
        
        customers = []
        for _, row in df.iterrows():
            customers.append({
                'customer_id': int(row['CustomerID']),
                'customer_name': str(row['CustomerName']),
                'contact_email': str(row['ContactEmail']) if row['ContactEmail'] else None,
                'contact_name': str(row['ContactName']) if row['ContactName'] else None,
                'phone_number': str(row['PhoneNumber']) if row['PhoneNumber'] else None,
                'total_spent': float(row['TotalSpent']) if row['TotalSpent'] else 0
            })
        
        return JSONResponse({'count': len(customers), 'customers': customers})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post('/generate-email-draft')
def api_generate_email_draft(request: EmailDraftRequest):
    """Generate an AI-powered email draft using OpenAI."""
    try:
        # Enrich customer_data if customer_id is provided
        customer_data = request.customer_data or {}
        
        if request.customer_id and not customer_data:
            # Fetch customer data from database
            query = f"""
            SELECT 
                c.CustomerID,
                c.CustomerName,
                c.PaymentDays,
                (SELECT SUM(il.ExtendedPrice) 
                 FROM Sales.Invoices i
                 JOIN Sales.InvoiceLines il ON i.InvoiceID = il.InvoiceID
                 WHERE i.CustomerID = c.CustomerID) AS TotalSpent,
                (SELECT TOP 1 ct.OutstandingBalance
                 FROM Sales.CustomerTransactions ct
                 WHERE ct.CustomerID = c.CustomerID AND ct.OutstandingBalance > 0
                 ORDER BY ct.TransactionDate DESC) AS OutstandingBalance,
                (SELECT TOP 1 DATEDIFF(DAY, DATEADD(DAY, c.PaymentDays, ct.TransactionDate), GETDATE())
                 FROM Sales.CustomerTransactions ct
                 WHERE ct.CustomerID = c.CustomerID AND ct.OutstandingBalance > 0
                 ORDER BY ct.TransactionDate DESC) AS DaysOverdue
            FROM Sales.Customers c
            WHERE c.CustomerID = {request.customer_id}
            """
            from analytics import run_sql
            df = run_sql(query)
            if not df.empty:
                row = df.iloc[0]
                customer_data = {
                    'total_spent': float(row['TotalSpent']) if row['TotalSpent'] else 0,
                    'outstanding_balance': float(row['OutstandingBalance']) if row['OutstandingBalance'] else 0,
                    'days_overdue': int(row['DaysOverdue']) if row['DaysOverdue'] else 0,
                    'payment_terms_days': int(row['PaymentDays']) if row['PaymentDays'] else 30
                }
        
        # Generate email draft
        draft = generate_email_draft(
            email_type=request.email_type,
            recipient_name=request.recipient_name,
            customer_data=customer_data,
            additional_context=request.additional_context
        )
        
        return JSONResponse({
            'success': True,
            'draft': draft,
            'recipient_email': request.recipient_email
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post('/send-email')
def api_send_email(request: SendEmailRequest):
    """Send an email via SMTP."""
    try:
        # Use environment variables as defaults
        smtp_server = request.smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = request.smtp_port or int(os.getenv('SMTP_PORT', '587'))
        smtp_username = request.smtp_username or os.getenv('SMTP_USERNAME')
        smtp_password = request.smtp_password or os.getenv('SMTP_PASSWORD')
        from_email = request.from_email or smtp_username or 'noreply@pepsico.com'
        
        if not smtp_username or not smtp_password:
            return JSONResponse({
                'success': False,
                'message': 'SMTP credentials not configured. Please set SMTP_USERNAME and SMTP_PASSWORD environment variables or provide them in the request.'
            }, status_code=400)
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = request.subject
        msg['From'] = from_email
        msg['To'] = request.to_email
        if request.cc_email:
            msg['Cc'] = request.cc_email
        
        # Attach HTML body
        html_part = MIMEText(request.body_html, 'html')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            recipients = [request.to_email]
            if request.cc_email:
                recipients.append(request.cc_email)
            server.sendmail(from_email, recipients, msg.as_string())
        
        return JSONResponse({
            'success': True,
            'message': f'Email sent successfully to {request.to_email}'
        })
    except Exception as e:
        return JSONResponse({
            'success': False,
            'message': f'Failed to send email: {str(e)}'
        }, status_code=500)


@api_router.get('/unpaid-invoices')
def api_unpaid_invoices(days_overdue: int = 0, limit: int = 100):
    """
    Webhook endpoint for Zapier/n8n integration.
    Returns customers with unpaid invoices (OutstandingBalance > 0).
    
    Args:
        days_overdue: Minimum days past payment terms (0 = all unpaid, 30 = 30+ days overdue)
        limit: Maximum number of records to return (default 100)
    
    Returns:
        JSON with unpaid invoice details including customer contact info
    """
    try:
        df = get_unpaid_invoices(days_overdue, limit)
        if df.empty:
            return JSONResponse({
                'count': 0,
                'unpaid_invoices': [],
                'message': 'No unpaid invoices found'
            })
        
        # Convert DataFrame to list of dicts with proper formatting
        records = []
        for _, row in df.iterrows():
            record = {
                'customer_id': int(row['CustomerID']),
                'customer_name': str(row['CustomerName']),
                'phone_number': str(row['PhoneNumber']) if row['PhoneNumber'] else None,
                'contact_email': str(row['ContactEmail']) if row['ContactEmail'] else None,
                'contact_name': str(row['ContactName']) if row['ContactName'] else None,
                'invoice_id': int(row['InvoiceID']) if row['InvoiceID'] else None,
                'invoice_date': str(row['InvoiceDate']) if row['InvoiceDate'] else None,
                'transaction_date': str(row['TransactionDate']),
                'transaction_amount': float(row['TransactionAmount']),
                'outstanding_balance': float(row['OutstandingBalance']),
                'days_overdue': int(row['DaysOverdue']),
                'payment_terms_days': int(row['PaymentDays']),
                'salesperson_name': str(row['SalespersonName']) if row['SalespersonName'] else None,
                'salesperson_email': str(row['SalespersonEmail']) if row['SalespersonEmail'] else None
            }
            records.append(record)
        
        total_outstanding = float(df['OutstandingBalance'].sum())
        
        return JSONResponse({
            'count': len(records),
            'total_outstanding': total_outstanding,
            'unpaid_invoices': records,
            'generated_at': datetime.utcnow().isoformat()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/')
async def root():
    """Serve the main HTML UI."""
    return FileResponse('static/index.html', media_type='text/html')


# Include the API router BEFORE mounting static files
app.include_router(api_router, prefix='/api')

# Mount agent_outputs as static files for serving plots
app.mount('/agent_outputs', StaticFiles(directory='agent_outputs'), name='outputs')

# Mount remaining static files (CSS, JS, images, etc.)
app.mount('/static', StaticFiles(directory='static'), name='static')
