import os
import pandas as pd
from typing import Optional

try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False


def local_summarize(df: pd.DataFrame, question: str) -> str:
    """Fallback local analysis without OpenAI API."""
    if df.empty:
        return "No data available for the requested period."
    
    summary_parts = []
    
    # Basic stats
    for col in df.select_dtypes(include=['number']).columns:
        total = df[col].sum()
        avg = df[col].mean()
        max_val = df[col].max()
        summary_parts.append(f"{col}: Total={total:,.2f}, Avg={avg:,.2f}, Max={max_val:,.2f}")
    
    # Trend analysis
    if 'revenue' in df.columns and 'cogs' in df.columns:
        df_sorted = df.sort_values('month')
        if len(df_sorted) > 1:
            first_rev = df_sorted['revenue'].iloc[0]
            last_rev = df_sorted['revenue'].iloc[-1]
            rev_change = ((last_rev - first_rev) / first_rev * 100) if first_rev > 0 else 0
            summary_parts.append(f"Revenue trend: {rev_change:+.1f}% over period")
            
            # Gross margin
            if (df_sorted['cogs'] > 0).any():
                df_sorted['margin'] = (df_sorted['revenue'] - df_sorted['cogs']) / df_sorted['revenue'] * 100
                avg_margin = df_sorted['margin'].mean()
                summary_parts.append(f"Average gross margin: {avg_margin:.1f}%")
    
    result = "; ".join(summary_parts)
    return result if result else "Data retrieved successfully."


import os
from openai import OpenAI
import pandas as pd
from typing import Optional

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def summarize_dataframe(df: pd.DataFrame, question: str, max_rows: int = 12) -> str:
    """Analyze data and provide intelligent insights about trends, anomalies, and business implications.
    
    Falls back to pattern-based analysis if LLM fails.
    """
    if df.empty:
        return "No data available for analysis."
    
    # Try LLM first if API key exists
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key and api_key.startswith('sk-'):
        try:
            sample = df.head(max_rows).to_csv(index=False)
            stats = df.describe(include='all').to_string()
            prompt = f"""You are a sales analyst. Analyze this data and answer the question.

Dataset (first {max_rows} rows):
{sample}

Summary statistics:
{stats}

Question: {question}

Provide a concise analysis (4-6 sentences) including:
- Key trends or patterns
- Notable changes or anomalies
- Business implications
- Specific numbers where relevant"""
            
            resp = client.chat.completions.create(
                model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                timeout=10
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            # Fall through to pattern-based analysis
            pass
    
    # Pattern-based analysis when LLM unavailable
    return analyze_patterns(df, question)


def analyze_patterns(df: pd.DataFrame, question: str) -> str:
    """Provide intelligent analysis using pandas/numpy pattern detection."""
    insights = []
    
    # Numeric columns analysis
    numeric_cols = df.select_dtypes(include=['number']).columns
    
    for col in numeric_cols:
        if col in df.columns:
            data = df[col].dropna()
            if len(data) == 0:
                continue
                
            total = data.sum()
            mean = data.mean()
            std = data.std()
            min_val = data.min()
            max_val = data.max()
            
            # Detect trends
            if len(data) > 1:
                first_half = data.iloc[:len(data)//2].mean()
                second_half = data.iloc[len(data)//2:].mean()
                change_pct = ((second_half - first_half) / first_half * 100) if first_half != 0 else 0
                
                trend = "increasing" if change_pct > 10 else ("decreasing" if change_pct < -10 else "stable")
                insights.append(f"{col.title()}: {trend.capitalize()} trend ({change_pct:+.1f}%) from {first_half:,.0f} to {second_half:,.0f}")
            
            # Volatility
            if std > mean * 0.5:
                insights.append(f"{col.title()}: High volatility (Range: {min_val:,.0f} - {max_val:,.0f})")
    
    # Multi-column relationships
    if 'revenue' in df.columns and 'cogs' in df.columns:
        df_clean = df[['revenue', 'cogs']].dropna()
        if len(df_clean) > 0:
            margin = ((df_clean['revenue'] - df_clean['cogs']) / df_clean['revenue'] * 100).mean()
            insights.append(f"Average gross margin: {margin:.1f}%")
    
    if 'roi' in df.columns:
        roi_clean = df['roi'].dropna()
        if len(roi_clean) > 0:
            avg_roi = roi_clean.mean()
            insights.append(f"Average ROI: {avg_roi:.2f}x")
    
    if not insights:
        insights.append("Data analyzed successfully but no significant patterns detected.")
    
    return ". ".join(insights) + "."
