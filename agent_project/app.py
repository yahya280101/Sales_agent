from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
from analytics import compute_roi, plot_timeseries
from agent import summarize_dataframe
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
            return HTTPException(status_code=400, detail="No data for the requested date range")
        out_path = os.path.join('agent_outputs', 'roi.png')
        plot_timeseries(df, ['revenue', 'cogs', 'gross_margin'], 'Monthly Revenue / COGS / Gross Margin', out_path)
        return FileResponse(out_path, media_type='image/png')
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
    try:
        summary = summarize_dataframe(df, req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({
        'summary': summary,
        'plot': '/agent_outputs/roi.png'
    })


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
