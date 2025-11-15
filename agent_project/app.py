from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
from analytics import (
    compute_roi, plot_timeseries, plot_bar_chart,
    top_customers, top_products, salesperson_performance, customer_segmentation,
    sales_by_location, forecast_product_demand
)
from agent import summarize_dataframe, forecast_with_llm
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

        try:
            llm_output = forecast_with_llm(history_for_llm, months_ahead, result['stock_item']['name'])
            result['forecast'] = [{'month': f['month'], 'units': f['units']} for f in llm_output.get('forecast', [])]
            if llm_output.get('explanation'):
                result['explanation'] = llm_output['explanation']
        except Exception:
            pass

        for section in ('history', 'forecast'):
            for row in result[section]:
                if hasattr(row['month'], 'isoformat'):
                    row['month'] = row['month'].date().isoformat()
        return JSONResponse(result)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
