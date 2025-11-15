import os
import json
from datetime import datetime
from typing import Optional, List, Dict

import pandas as pd

try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    HAS_OPENAI = True
except Exception:
    client = None
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
    if {'revenue', 'cogs'}.issubset(df.columns):
        df_sorted = df.sort_values('month')
        if len(df_sorted) > 1:
            first_rev = df_sorted['revenue'].iloc[0]
            last_rev = df_sorted['revenue'].iloc[-1]
            rev_change = ((last_rev - first_rev) / first_rev * 100) if first_rev > 0 else 0
            summary_parts.append(f"Revenue trend: {rev_change:+.1f}% over period")

            if (df_sorted['cogs'] > 0).any():
                df_sorted['margin'] = (df_sorted['revenue'] - df_sorted['cogs']) / df_sorted['revenue'] * 100
                avg_margin = df_sorted['margin'].mean()
                summary_parts.append(f"Average gross margin: {avg_margin:.1f}%")

    result = "; ".join(summary_parts)
    return result if result else "Data retrieved successfully."


def summarize_dataframe(df: pd.DataFrame, question: str, max_rows: int = 12, context: Optional[str] = None) -> str:
    """Analyze data and provide intelligent insights about trends, anomalies, and business implications."""
    if df.empty:
        return "No data available for analysis."

    api_key = os.getenv('OPENAI_API_KEY')
    if HAS_OPENAI and api_key and api_key.startswith('sk-'):
        try:
            sample = df.head(max_rows).to_csv(index=False)
            stats = df.describe(include='all').to_string()
            context_block = f"\n\nAdditional business context:\n{context}\n" if context else ""
            prompt = f"""You are a sales analyst. Analyze this data and answer the question.

Dataset (first {max_rows} rows):
{sample}

Summary statistics:
{stats}

Question: {question}
{context_block}

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
        except Exception:
            pass

    return analyze_patterns(df, question, context)


def analyze_patterns(df: pd.DataFrame, question: str, context: Optional[str] = None) -> str:
    """Provide heuristic analysis using pandas/numpy pattern detection."""
    insights = []
    numeric_cols = df.select_dtypes(include=['number']).columns

    for col in numeric_cols:
        data = df[col].dropna()
        if len(data) == 0:
            continue

        total = data.sum()
        mean = data.mean()
        std = data.std()
        min_val = data.min()
        max_val = data.max()

        if len(data) > 1:
            first_half = data.iloc[:len(data)//2].mean()
            second_half = data.iloc[len(data)//2:].mean()
            change_pct = ((second_half - first_half) / first_half * 100) if first_half else 0
            trend = "increasing" if change_pct > 10 else ("decreasing" if change_pct < -10 else "stable")
            insights.append(f"{col.title()}: {trend.capitalize()} trend ({change_pct:+.1f}%) from {first_half:,.0f} to {second_half:,.0f}")

        if std > mean * 0.5:
            insights.append(f"{col.title()}: High volatility (Range: {min_val:,.0f} - {max_val:,.0f})")

    if {'revenue', 'cogs'}.issubset(df.columns):
        df_clean = df[['revenue', 'cogs']].dropna()
        if len(df_clean) > 0:
            margin = ((df_clean['revenue'] - df_clean['cogs']) / df_clean['revenue'] * 100).mean()
            insights.append(f"Average gross margin: {margin:.1f}%")

    if 'roi' in df.columns:
        roi_clean = df['roi'].dropna()
        if len(roi_clean) > 0:
            insights.append(f"Average ROI: {roi_clean.mean():.2f}x")

    if context:
        insights.append(f"Contextual notes: {context}")
    if not insights:
        insights.append("Data analyzed successfully but no significant patterns detected.")

    return ". ".join(insights) + "."


def forecast_with_llm(history: List[Dict], months_ahead: int = 6, item_name: str = "product") -> Dict:
    """Use the OpenAI model to generate numeric demand forecasts with explanation."""
    if not HAS_OPENAI or client is None:
        raise RuntimeError("LLM forecasting unavailable")
    if not history:
        raise ValueError("History is required for forecasting")

    months_ahead = max(1, min(int(months_ahead), 12))
    formatted_history = []
    for row in history[-24:]:
        month = row['month']
        if hasattr(month, 'strftime'):
            month = month.strftime('%Y-%m')
        formatted_history.append(f"{month}: {float(row['units']):.0f}")

    prompt = f"""You are a demand forecasting assistant. Given historical monthly units for a {item_name},
predict the next {months_ahead} months of units sold.

History:
{chr(10).join(formatted_history)}

Return strictly JSON with the structure:
{{
  "forecast": [{{"month":"YYYY-MM","units":1234}}, ... exactly {months_ahead} entries],
  "explanation": "Short explanation (20-40 words) describing the drivers behind the forecast"
}}
Months must be consecutive calendar months immediately following the latest history month."""

    try:
        resp = client.chat.completions.create(
            model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2,
            timeout=10
        )
        text = resp.choices[0].message.content.strip()
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            raise ValueError("LLM response missing JSON object")
        parsed = json.loads(text[start:end+1])
        forecast_payload = parsed.get('forecast', [])
        explanation = parsed.get('explanation', '').strip()
        cleaned = []
        for entry in forecast_payload[:months_ahead]:
            month = entry.get('month')
            units = float(entry.get('units', 0))
            cleaned.append({'month': month, 'units': units})
        if len(cleaned) != months_ahead:
            raise ValueError("LLM returned incorrect number of months")
        return {'forecast': cleaned, 'explanation': explanation}
    except Exception as exc:
        raise RuntimeError(f"LLM forecast failed: {exc}")
