from fastapi import FastAPI, Request, HTTPException, APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
from datetime import datetime, date
import re
from numbers import Number
import json
import urllib.request
import urllib.error
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from analytics import (
    compute_roi, plot_timeseries, plot_bar_chart,
    top_customers, top_products, salesperson_performance, customer_segmentation,
    sales_by_location, forecast_product_demand, get_unpaid_invoices,
    find_products_by_name, find_customer_by_name, customer_metrics,
    customer_monthly_sales, customer_top_products
)
from agent import summarize_dataframe, forecast_with_llm, customer_insight_with_llm, generate_email_draft
import pandas as pd

app = FastAPI(title='Sales Agent')

# Create outputs directory
os.makedirs('agent_outputs', exist_ok=True)

# Create API router FIRST (before static mounts)
api_router = APIRouter()

DEFAULT_SMTP_USERNAME = os.getenv('DEFAULT_SMTP_USERNAME', 't60029350@gmail.com')
RAW_APP_PASSWORD = os.getenv('DEFAULT_SMTP_APP_PASSWORD') or 'tfye nebm jhkh lxdf'
DEFAULT_SMTP_APP_PASSWORDS = []
if RAW_APP_PASSWORD:
    DEFAULT_SMTP_APP_PASSWORDS.append(RAW_APP_PASSWORD)
    compact = RAW_APP_PASSWORD.replace(' ', '')
    if compact and compact not in DEFAULT_SMTP_APP_PASSWORDS:
        DEFAULT_SMTP_APP_PASSWORDS.append(compact)

class AskRequest(BaseModel):
    question: str
    start_date: Optional[str] = '2015-01-01'
    end_date: Optional[str] = '2016-12-31'


class EmailDraftRequest(BaseModel):
    email_type: str
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


class AudioSessionRequest(BaseModel):
    start_date: Optional[str] = '2015-01-01'
    end_date: Optional[str] = '2016-12-31'


class CustomerIntentRequest(BaseModel):
    customer_name: str
    start_date: Optional[str] = '2015-01-01'
    end_date: Optional[str] = '2016-12-31'


def to_serializable(value):
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, Number):
        try:
            float_val = float(value)
        except Exception:
            return value
        return int(float_val) if float_val.is_integer() else float_val
    return value


def build_customer_name_variants(name: str) -> list[str]:
    """Return variations attempting to enforce the Customer-X-X-X format."""
    variants = []

    def push(val):
        if val and val not in variants:
            variants.append(val)

    cleaned = (name or '').strip()
    push(cleaned)
    tokens = [tok for tok in re.split(r'[^A-Za-z0-9]+', cleaned) if tok]
    if tokens:
        title_tokens = [tok.title() for tok in tokens]
        slug = "Customer-" + "-".join(title_tokens)
        push(slug)
        push(slug.upper())
    return variants


def build_context_summary(start_date: str, end_date: str) -> str:
    parts = []
    try:
        roi_df = compute_roi(start_date, end_date)
        if not roi_df.empty:
            revenue = roi_df['revenue'].sum()
            cogs = roi_df['cogs'].sum()
            margin = roi_df['gross_margin'].sum()
            avg_roi = roi_df['roi'].dropna().mean() if roi_df['roi'].notna().any() else 0
            parts.append(f"Revenue {revenue:,.0f}, COGS {cogs:,.0f}, gross margin {margin:,.0f}, avg ROI {avg_roi:.2f}x.")
    except Exception:
        pass
    try:
        customers = top_customers(start_date, end_date, limit=3)
        if not customers.empty:
            formatted = ", ".join(f"{row.CustomerName} ({row.total_revenue:,.0f})" for _, row in customers.iterrows())
            parts.append(f"Top customers: {formatted}.")
    except Exception:
        pass
    try:
        products = top_products(start_date, end_date, limit=3)
        if not products.empty:
            formatted = ", ".join(f"{row.StockItemName} ({row.total_units:,.0f} units)" for _, row in products.iterrows())
            parts.append(f"Top products: {formatted}.")
    except Exception:
        pass
    try:
        perf = salesperson_performance(start_date, end_date).head(3)
        if not perf.empty:
            formatted = ", ".join(f"{row.salesperson or 'Unknown'} ({row.total_revenue:,.0f})" for _, row in perf.iterrows())
            parts.append(f"Sales leaders: {formatted}.")
    except Exception:
        pass
    return " ".join(parts) if parts else "No contextual metrics available."


@api_router.post('/audio-session')
def create_audio_session(body: AudioSessionRequest = Body(None)):
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail='OPENAI_API_KEY not configured')
    start = body.start_date if body and body.start_date else '2015-01-01'
    end = body.end_date if body and body.end_date else '2016-12-31'
    context_summary = build_context_summary(start, end)
    kickoff_prompt = (
        "PepsiCoPilot here. Share two punchy insights with numbers from this data: "
        f"{context_summary}. Invite the user to ask follow-ups."
    )
    payload = {
        'model': os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-12-17'),
        'voice': os.getenv('OPENAI_REALTIME_VOICE', 'verse'),
        'instructions': (
            "You are PepsiCoPilot, an energetic conversational sales analyst for PepsiCo leadership. "
            "Always speak clearly, cite concrete numbers, and keep responses under 80 words unless the user requests detail. "
            "Lead with 2-3 'smart' insights referencing ROI, growth trends, top customers, or risk signals from the context summary. "
            "If the user asks for next steps, recommend specific actions.\n"
            f"Context summary:\n{context_summary}"
        )
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/realtime/sessions',
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.read().decode('utf-8', errors='ignore'))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if status >= 400:
        raise HTTPException(status_code=status, detail=resp_body.decode('utf-8', errors='ignore'))
    session_payload = json.loads(resp_body.decode('utf-8'))
    session_payload['pepsico_context'] = context_summary
    session_payload['pepsico_kickoff'] = kickoff_prompt
    return JSONResponse(session_payload)


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
    """List customers with contact info to drive the email center UI."""
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
            safe_search = search.replace("'", "''")
            query += f" AND (c.CustomerName LIKE '%{safe_search}%' OR p.FullName LIKE '%{safe_search}%')"
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post('/generate-email-draft')
def api_generate_email_draft(request: EmailDraftRequest):
    """Generate an AI-powered email draft using OpenAI."""
    try:
        customer_data = request.customer_data or {}
        if request.customer_id and not customer_data:
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

        draft = generate_email_draft(
            email_type=request.email_type,
            recipient_name=request.recipient_name,
            customer_data=customer_data,
            additional_context=request.additional_context
        )
        return JSONResponse({'success': True, 'draft': draft, 'recipient_email': request.recipient_email})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post('/send-email')
def api_send_email(request: SendEmailRequest):
    """Send emails via SMTP using configured credentials."""
    try:
        smtp_server = request.smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = request.smtp_port or int(os.getenv('SMTP_PORT', '465'))
        smtp_username = request.smtp_username or os.getenv('SMTP_USERNAME') or DEFAULT_SMTP_USERNAME
        from_email = request.from_email or smtp_username or 'noreply@pepsico.com'

        password_candidates = []
        if request.smtp_password:
            password_candidates.append(request.smtp_password)
        env_pw = os.getenv('SMTP_PASSWORD')
        if env_pw:
            password_candidates.append(env_pw)
        password_candidates.extend(DEFAULT_SMTP_APP_PASSWORDS)

        # Remove duplicates while preserving order
        deduped_passwords = []
        for pw in password_candidates:
            if pw and pw not in deduped_passwords:
                deduped_passwords.append(pw)

        if not smtp_username or not deduped_passwords:
            return JSONResponse({
                'success': False,
                'message': 'SMTP credentials not configured. Provide SMTP_USERNAME/PASSWORD env vars or in the request.'
            }, status_code=400)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = request.subject
        msg['From'] = from_email
        msg['To'] = request.to_email
        if request.cc_email:
            msg['Cc'] = request.cc_email
        msg.attach(MIMEText(request.body_html, 'html'))

        auth_error = None
        context = ssl.create_default_context()
        for smtp_password in deduped_passwords:
            try:
                if smtp_port == 465:
                    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                        server.login(smtp_username, smtp_password)
                        recipients = [request.to_email]
                        if request.cc_email:
                            recipients.append(request.cc_email)
                        server.sendmail(from_email, recipients, msg.as_string())
                else:
                    with smtplib.SMTP(smtp_server, smtp_port) as server:
                        server.starttls(context=context)
                        server.login(smtp_username, smtp_password)
                        recipients = [request.to_email]
                        if request.cc_email:
                            recipients.append(request.cc_email)
                        server.sendmail(from_email, recipients, msg.as_string())
                return JSONResponse({'success': True, 'message': f'Email sent successfully to {request.to_email}'})
            except smtplib.SMTPAuthenticationError as err:
                auth_error = err
                continue
        message = f'Failed to authenticate with Gmail SMTP: {auth_error}' if auth_error else 'Failed to send email.'
        return JSONResponse({'success': False, 'message': message}, status_code=500)
    except Exception as exc:
        return JSONResponse({'success': False, 'message': f'Failed to send email: {exc}'}, status_code=500)


@api_router.get('/unpaid-invoices')
def api_unpaid_invoices(days_overdue: int = 0, limit: int = 100):
    """Return customers with unpaid invoices and related contact details."""
    try:
        df = get_unpaid_invoices(days_overdue, limit)
        if df.empty:
            return JSONResponse({'count': 0, 'unpaid_invoices': [], 'message': 'No unpaid invoices found'})

        records = []
        for _, row in df.iterrows():
            records.append({
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
            })

        total_outstanding = float(df['OutstandingBalance'].sum())
        return JSONResponse({
            'count': len(records),
            'total_outstanding': total_outstanding,
            'unpaid_invoices': records,
            'generated_at': datetime.utcnow().isoformat()
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post('/customer-intent')
async def api_customer_intent(req: CustomerIntentRequest):
    customer_name = (req.customer_name or '').strip()
    if not customer_name:
        raise HTTPException(status_code=400, detail="customer_name is required")

    try:
        matches = pd.DataFrame()
        tried_variants = build_customer_name_variants(customer_name)
        for variant in tried_variants:
            matches = find_customer_by_name(variant, limit=5)
            if not matches.empty:
                customer_name = variant
                break
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {exc}")

    if matches.empty:
        raise HTTPException(status_code=404, detail="Customer not found")

    lower_name = customer_name.lower()
    exact_rows = matches[matches['CustomerName'].str.lower() == lower_name]
    row = exact_rows.iloc[0] if not exact_rows.empty else matches.iloc[0]

    customer_id = int(row.CustomerID)
    metrics_raw = customer_metrics(customer_id, req.start_date, req.end_date)
    if not metrics_raw:
        raise HTTPException(status_code=404, detail="No sales data in the selected range for this customer")
    metrics = {k: to_serializable(v) for k, v in metrics_raw.items()}

    def safe_field(value):
        return None if pd.isna(value) else value

    monthly_df = customer_monthly_sales(customer_id, req.start_date, req.end_date)
    monthly_records = []
    for _, r in monthly_df.iterrows():
        month_value = r['month']
        if hasattr(month_value, 'isoformat'):
            month_value = month_value.isoformat()
        monthly_records.append({
            'month': month_value,
            'revenue': float(r['revenue']) if pd.notna(r['revenue']) else 0.0,
            'profit': float(r['profit']) if pd.notna(r['profit']) else 0.0
        })

    top_df = customer_top_products(customer_id, req.start_date, req.end_date, limit=5)
    top_records = []
    for _, r in top_df.iterrows():
        top_records.append({
            'name': r['StockItemName'],
            'units': float(r['total_units']) if pd.notna(r['total_units']) else 0.0,
            'revenue': float(r['revenue']) if pd.notna(r['revenue']) else 0.0,
            'profit': float(r['profit']) if pd.notna(r['profit']) else 0.0
        })

    customer_payload = {
        'id': customer_id,
        'name': safe_field(row.CustomerName) or customer_name,
        'category': safe_field(row.CustomerCategoryName),
        'phone': safe_field(row.PhoneNumber),
        'website': safe_field(row.WebsiteURL),
        'credit_limit': to_serializable(row.CreditLimit if not pd.isna(row.CreditLimit) else None),
        'location': {
            'city': safe_field(row.CityName),
            'state': safe_field(row.StateProvinceName),
            'country': safe_field(row.CountryName)
        }
    }

    try:
        narrative = customer_insight_with_llm(customer_payload['name'], metrics, monthly_records, top_records)
    except Exception:
        narrative = {'insight': 'Unable to generate AI analysis at this time.', 'highlights': []}

    response = {
        'customer': customer_payload,
        'metrics': metrics,
        'monthly': monthly_records,
        'top_products': top_records,
        'insight': narrative.get('insight'),
        'highlights': narrative.get('highlights', [])
    }
    return JSONResponse(response)


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
