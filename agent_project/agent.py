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
  "explanation": "Write 2-3 sentences (40-80 words) referencing specific forecast values, seasonal drivers, and risks/opportunities. Mention at least two concrete numbers from the forecast."
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


def _format_currency(value) -> str:
    if value is None:
        return "$0"
    try:
        value = float(value)
    except Exception:
        return str(value)
    return f"${value:,.0f}"


def _fallback_customer_insight(customer_name: str,
                               metrics: Dict,
                               monthly: List[Dict],
                               top_products: List[Dict]) -> Dict:
    revenue = metrics.get('revenue') or 0
    profit = metrics.get('profit') or 0
    invoices = metrics.get('invoices') or metrics.get('orders') or 0
    sentences = [
        f"{customer_name} generated {_format_currency(revenue)} in revenue and {_format_currency(profit)} in profit across the selected period."
    ]

    if invoices:
        sentences.append(f"The team processed {int(float(invoices))} invoices for this customer.")

    if monthly and len(monthly) >= 2:
        start = monthly[0]
        end = monthly[-1]
        start_rev = float(start.get('revenue') or 0)
        end_rev = float(end.get('revenue') or 0)
        if start_rev:
            change = ((end_rev - start_rev) / start_rev) * 100
            sentences.append(
                f"Revenue moved from {_format_currency(start_rev)} in {start.get('month')} "
                f"to {_format_currency(end_rev)} in {end.get('month')} ({change:+.1f}%)."
            )

    highlights = []
    if top_products:
        top = top_products[0]
        highlights.append(
            f"Top SKU {top.get('name')} contributed {_format_currency(top.get('revenue'))} "
            f"across {int(float(top.get('units') or 0))} units"
        )
    if profit:
        margin_pct = (float(profit) / revenue * 100) if revenue else None
        if margin_pct is not None:
            highlights.append(f"Average profit margin {margin_pct:.1f}%")

    # Ensure fallback strings are concise.
    insight_text = " ".join(sentences).strip()
    return {'insight': insight_text, 'highlights': highlights}


def customer_insight_with_llm(customer_name: str,
                              metrics: Dict,
                              monthly: List[Dict],
                              top_products: List[Dict]) -> Dict:
    """Ask the LLM to craft a narrative about a single customer's performance."""
    payload = {
        'customer_name': customer_name,
        'metrics': metrics,
        'monthly': monthly[-12:],
        'top_products': top_products[:5]
    }
    api_key = os.getenv('OPENAI_API_KEY')
    if HAS_OPENAI and api_key and api_key.startswith('sk-'):
        try:
            prompt = f"""You are a senior PepsiCo sales strategist.
Summarize the customer's performance using the JSON data block.
Highlight revenue, profit, trends, and product contribution.
Return strictly JSON with:
{{
  "insight": "3 sentences (<=90 words) referencing concrete numbers and months.",
  "highlights": ["short bullet with a number", "another highlight"]
}}

Data:
{json.dumps(payload, indent=2)}
"""
            resp = client.chat.completions.create(
                model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
                timeout=10
            )
            content = resp.choices[0].message.content.strip()
            start = content.find('{')
            end = content.rfind('}')
            if start == -1 or end == -1:
                raise ValueError("LLM response missing JSON block")
            parsed = json.loads(content[start:end+1])
            insight = parsed.get('insight', '').strip()
            highlights = parsed.get('highlights', [])
            if isinstance(highlights, str):
                highlights = [highlights]
            highlights = [h.strip() for h in highlights if h and isinstance(h, str)]
            if insight:
                return {'insight': insight, 'highlights': highlights}
        except Exception:
            pass
    return _fallback_customer_insight(customer_name, metrics, monthly, top_products)


def generate_email_draft(
    email_type: str,
    recipient_name: str,
    customer_data: Optional[Dict] = None,
    additional_context: Optional[str] = None
) -> Dict:
    """
    Generate professional email drafts using OpenAI based on email type and context.
    
    Args:
        email_type: Type of email (payment_reminder, product_recommendation, appreciation, 
                   follow_up, seasonal_promotion, order_confirmation, welcome, win_back)
        recipient_name: Name of the recipient
        customer_data: Dictionary with customer info (spending, products, overdue_amount, etc.)
        additional_context: Any additional context for the email
    
    Returns:
        Dict with subject, body (HTML), preview_text
    """
    if not HAS_OPENAI or client is None:
        return generate_fallback_email(email_type, recipient_name, customer_data)
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or not api_key.startswith('sk-'):
        return generate_fallback_email(email_type, recipient_name, customer_data)
    
    customer_data = customer_data or {}
    
    # Build context based on email type
    email_templates = {
        'payment_reminder': {
            'context': f"Customer: {recipient_name}. Outstanding balance: ${customer_data.get('outstanding_balance', 0):,.2f}. Days overdue: {customer_data.get('days_overdue', 0)}. Invoice #{customer_data.get('invoice_id', 'N/A')}.",
            'tone': 'professional and friendly but firm',
            'goal': 'remind the customer about an overdue payment while maintaining goodwill'
        },
        'product_recommendation': {
            'context': f"Customer: {recipient_name}. Previous purchases: {customer_data.get('previous_products', 'various products')}. Total spending: ${customer_data.get('total_spent', 0):,.2f}. Recommended products based on their purchase history.",
            'tone': 'enthusiastic and helpful',
            'goal': 'suggest products they might be interested in based on their purchase patterns'
        },
        'appreciation': {
            'context': f"Customer: {recipient_name}. Loyal customer who has spent ${customer_data.get('total_spent', 0):,.2f} over {customer_data.get('years_as_customer', 'several')} years. Thank them for their business.",
            'tone': 'warm and grateful',
            'goal': 'express genuine appreciation for their continued business'
        },
        'follow_up': {
            'context': f"Customer: {recipient_name}. Following up after {customer_data.get('follow_up_reason', 'their recent interaction')}. Last order was {customer_data.get('days_since_order', 'recently')} days ago.",
            'tone': 'friendly and helpful',
            'goal': 'check in and offer assistance while encouraging future business'
        },
        'seasonal_promotion': {
            'context': f"Customer: {recipient_name}. Announce a {customer_data.get('promotion_type', 'special')} promotion for {customer_data.get('season', 'this season')}. Discount: {customer_data.get('discount', '15%')}.",
            'tone': 'exciting and engaging',
            'goal': 'create urgency and excitement about a limited-time promotional offer'
        },
        'order_confirmation': {
            'context': f"Customer: {recipient_name}. Order #{customer_data.get('order_id', 'N/A')}. Total: ${customer_data.get('order_total', 0):,.2f}. Estimated delivery: {customer_data.get('delivery_date', '5-7 business days')}.",
            'tone': 'clear and reassuring',
            'goal': 'confirm their order details and set clear expectations'
        },
        'welcome': {
            'context': f"New customer: {recipient_name}. Welcome them to PepsiCo. First order discount: {customer_data.get('welcome_discount', '10%')}.",
            'tone': 'welcoming and enthusiastic',
            'goal': 'make a great first impression and encourage their first purchase'
        },
        'win_back': {
            'context': f"Inactive customer: {recipient_name}. Last purchase was {customer_data.get('days_inactive', 180)} days ago. They previously spent ${customer_data.get('total_spent', 0):,.2f}. Special incentive: {customer_data.get('incentive', '20% off')}.",
            'tone': 'friendly and enticing',
            'goal': 'rekindle the relationship and encourage them to return'
        }
    }
    
    template = email_templates.get(email_type, email_templates['follow_up'])
    context_str = template['context']
    if additional_context:
        context_str += f" Additional context: {additional_context}"
    
    prompt = f"""You are a professional email copywriter for PepsiCo. Write a compelling business email.

Email Type: {email_type.replace('_', ' ').title()}
Recipient: {recipient_name}
Context: {context_str}
Tone: {template.get('tone')}
Goal: {template.get('goal')}

Generate a professional email with:
1. A compelling subject line (max 60 characters)
2. A preview text (max 100 characters) 
3. HTML email body (use inline styles, modern design, responsive, PepsiCo branding colors: #0054a6 blue, #e32526 red)

The email should be:
- Personalized and engaging
- Include specific numbers/details from the context
- Have a clear call-to-action
- Be 150-250 words
- Use proper email HTML structure with inline CSS

Return strictly JSON:
{{
  "subject": "...",
  "preview_text": "...",
  "body": "...complete HTML email..."
}}"""

    try:
        resp = client.chat.completions.create(
            model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7,
            timeout=15
        )
        text = resp.choices[0].message.content.strip()
        
        # Extract JSON from response
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            raise ValueError("LLM response missing JSON")
        
        result = json.loads(text[start:end+1])
        
        return {
            'subject': result.get('subject', f'Message from PepsiCo'),
            'preview_text': result.get('preview_text', ''),
            'body': result.get('body', '<p>Email content</p>'),
            'generated_by': 'openai'
        }
    except Exception as e:
        print(f"Email generation error: {e}")
        return generate_fallback_email(email_type, recipient_name, customer_data)


def generate_fallback_email(email_type: str, recipient_name: str, customer_data: Optional[Dict] = None) -> Dict:
    """Generate comprehensive email templates with real database data when OpenAI is unavailable."""
    customer_data = customer_data or {}
    
    # Helper to format currency
    def fmt_currency(value): 
        return f"${float(value):,.2f}" if value else "$0.00"
    
    templates = {
        'payment_reminder': {
            'subject': f"Payment Reminder - Invoice #{customer_data.get('invoice_id', 'Pending')}",
            'preview_text': f"Outstanding balance: {fmt_currency(customer_data.get('outstanding_balance', 0))}",
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #0054a6, #003d79); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 28px;">💰 Payment Reminder</h1>
                        <p style="margin: 8px 0 0; opacity: 0.9;">Invoice #{customer_data.get('invoice_id', 'N/A')}</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">This is a friendly reminder regarding an outstanding balance on your account.</p>
                        
                        <div style="background: linear-gradient(135deg, #fff5f5, #ffe5e5); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 4px solid #e32526;">
                            <h3 style="margin: 0 0 15px 0; color: #e32526;">Account Summary</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 8px 0; color: #666;">Invoice Number:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get('invoice_id', 'N/A')}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Invoice Date:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get('invoice_date', 'N/A')}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Payment Terms:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">Net {customer_data.get('payment_terms_days', 30)} days</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Days Overdue:</td><td style="padding: 8px 0; text-align: right; font-weight: 600; color: #e32526;">{customer_data.get('days_overdue', 0)} days</td></tr>
                                <tr style="border-top: 2px solid #e32526;"><td style="padding: 12px 0; font-size: 18px; font-weight: 600;">Amount Due:</td><td style="padding: 12px 0; text-align: right; font-size: 24px; font-weight: 700; color: #e32526;">{fmt_currency(customer_data.get('outstanding_balance', 0))}</td></tr>
                            </table>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">Please remit payment at your earliest convenience to avoid any service interruption or late fees.</p>
                        <p style="font-size: 16px; line-height: 1.6;">If you have already sent payment, please disregard this notice. For questions about your account, please contact our accounts receivable team.</p>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 25px 0;">
                            <p style="margin: 0; font-size: 14px; color: #666;"><strong>Payment Options:</strong></p>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #666;">• Wire Transfer • Check • ACH • Credit Card</p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">Thank you for your prompt attention to this matter.</p>
                        <p style="font-size: 16px; line-height: 1.6; margin: 0;">Best regards,<br><strong>PepsiCo Accounts Receivable Team</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">This is an automated reminder from PepsiCo Sales Analytics</p>
                        <p style="margin: 8px 0 0; font-size: 12px;">Need help? Contact us at <a href="mailto:ar@pepsico.com">ar@pepsico.com</a></p>
