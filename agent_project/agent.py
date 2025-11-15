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
                        <p style="margin: 8px 0 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'appreciation': {
            'subject': f'Thank You, {recipient_name}! 🙏',
            'preview_text': f"You've spent {fmt_currency(customer_data.get('total_spent', 0))} with us",
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #22c55e, #16a34a); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 32px;">🙏 Thank You!</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95; font-size: 16px;">For Being a Valued Partner</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">We wanted to take a moment to express our sincere gratitude for your continued partnership with PepsiCo.</p>
                        
                        <div style="background: linear-gradient(135deg, #f0fdf4, #dcfce7); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 4px solid #22c55e;">
                            <h3 style="margin: 0 0 15px 0; color: #16a34a;">Your Partnership Impact</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 10px 0; color: #666;">Total Investment:</td><td style="padding: 10px 0; text-align: right; font-weight: 700; font-size: 20px; color: #16a34a;">{fmt_currency(customer_data.get('total_spent', 0))}</td></tr>
                                <tr><td style="padding: 10px 0; color: #666;">Partnership Since:</td><td style="padding: 10px 0; text-align: right; font-weight: 600;">{customer_data.get('years_as_customer', 'Many')} years</td></tr>
                                <tr><td style="padding: 10px 0; color: #666;">Orders Placed:</td><td style="padding: 10px 0; text-align: right; font-weight: 600;">{customer_data.get('order_count', '100+')} orders</td></tr>
                            </table>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">Your trust in our products and services drives us to continuously improve and innovate. We're honored to be part of your success story.</p>
                        
                        <div style="background: #0054a6; color: white; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                            <p style="margin: 0; font-size: 18px; font-weight: 600;">🎁 Special Offer for You</p>
                            <p style="margin: 12px 0 0; font-size: 14px; opacity: 0.9;">As a token of appreciation, enjoy 10% off your next order with code: <strong style="font-size: 16px; letter-spacing: 1px;">VALUED2025</strong></p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">We look forward to serving you for many years to come. If there's anything we can do to enhance your experience, please don't hesitate to reach out.</p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">With gratitude,<br><strong>The PepsiCo Team</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'product_recommendation': {
            'subject': f'Handpicked Products Just for You, {recipient_name}',
            'preview_text': 'Based on your purchase history, we think you\'ll love these',
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #8b5cf6, #7c3aed); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 28px;">🛍️ Recommendations for You</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95;">Based on your preferences</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">Based on your purchase history of <strong>{customer_data.get('previous_products', 'quality PepsiCo products')}</strong>, we've selected some items we think you'll love!</p>
                        
                        <div style="background: linear-gradient(135deg, #faf5ff, #f3e8ff); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 4px solid #8b5cf6;">
                            <h3 style="margin: 0 0 15px 0; color: #7c3aed;">Your Shopping Profile</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 8px 0; color: #666;">Total Spent:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{fmt_currency(customer_data.get('total_spent', 0))}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Favorite Categories:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get('top_category', 'Beverages')}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Last Order:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get('days_since_order', 30)} days ago</td></tr>
                            </table>
                        </div>
                        
                        <h3 style="color: #7c3aed; margin: 30px 0 20px;">🌟 Recommended Products</h3>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 15px 0;">
                            <div style="display: table; width: 100%;">
                                <div style="display: table-cell; vertical-align: middle; width: 60%;">
                                    <h4 style="margin: 0; color: #333;">Premium Product Line</h4>
                                    <p style="margin: 8px 0; font-size: 14px; color: #666;">Perfect complement to your current selection</p>
                                </div>
                                <div style="display: table-cell; vertical-align: middle; text-align: right;">
                                    <span style="background: #22c55e; color: white; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">TRENDING</span>
                                </div>
                            </div>
                        </div>
                        
                        <div style="background: #0054a6; color: white; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                            <p style="margin: 0; font-size: 18px; font-weight: 600;">📦 Bundle & Save</p>
                            <p style="margin: 12px 0 0; font-size: 14px; opacity: 0.9;">Order these products together and save <strong style="font-size: 18px;">15%</strong></p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">Ready to order? Reply to this email or contact your sales representative to place an order today!</p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">Happy shopping!<br><strong>PepsiCo Sales Team</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'follow_up': {
            'subject': f'Checking In With You, {recipient_name}',
            'preview_text': 'How can we better serve you?',
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #3b82f6, #2563eb); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 28px;">📞 Let's Connect</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95;">We value your feedback</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">We noticed it's been <strong>{customer_data.get('days_since_order', 30)} days</strong> since your last order, and we wanted to check in to see how everything is going.</p>
                        
                        <div style="background: linear-gradient(135deg, #eff6ff, #dbeafe); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 4px solid #3b82f6;">
                            <h3 style="margin: 0 0 15px 0; color: #2563eb;">Your Recent Activity</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 8px 0; color: #666;">Last Order Date:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get('last_order_date', 'N/A')}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Last Order Value:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{fmt_currency(customer_data.get('last_order_amount', 0))}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Total Orders:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get('order_count', 'N/A')}</td></tr>
                            </table>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">We're here to help with:</p>
                        <ul style="font-size: 16px; line-height: 1.8; color: #333;">
                            <li>Product recommendations</li>
                            <li>Inventory management</li>
                            <li>Special pricing inquiries</li>
                            <li>Order scheduling</li>
                        </ul>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                            <p style="margin: 0; font-size: 14px; color: #666;"><strong>Have questions or need assistance?</strong></p>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #666;">Simply reply to this email or call us at <strong>1-800-PEPSICO</strong></p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">We're committed to your success and look forward to hearing from you soon!</p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">Best regards,<br><strong>Your PepsiCo Account Manager</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'seasonal_promotion': {
            'subject': f'🎉 Exclusive {customer_data.get("season", "Seasonal")} Promotion Inside!',
            'preview_text': f'Save {customer_data.get("discount", "15%")} on your favorite products',
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 32px;">🎉 Special Promotion</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95; font-size: 18px;">{customer_data.get("season", "Seasonal")} Sale Event!</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">Great news! We're offering an exclusive <strong>{customer_data.get("promotion_type", "seasonal")}</strong> promotion just for valued customers like you.</p>
                        
                        <div style="background: linear-gradient(135deg, #fef3c7, #fde68a); padding: 30px; border-radius: 12px; margin: 25px 0; border: 3px dashed #f59e0b; text-align: center;">
                            <p style="margin: 0; font-size: 14px; color: #92400e; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">Exclusive Offer</p>
                            <p style="margin: 15px 0; font-size: 48px; font-weight: 700; color: #d97706; line-height: 1;">{customer_data.get("discount", "15%")}</p>
                            <p style="margin: 0; font-size: 18px; color: #92400e; font-weight: 600;">OFF Your Next Order</p>
                            <div style="background: white; padding: 12px 24px; border-radius: 25px; margin: 20px auto 0; display: inline-block;">
                                <p style="margin: 0; font-size: 16px; color: #d97706; font-weight: 700; letter-spacing: 2px;">Code: <span style="font-size: 20px;">{customer_data.get("promo_code", "SAVE2025")}</span></p>
                            </div>
                        </div>
                        
                        <div style="background: linear-gradient(135deg, #fff7ed, #ffedd5); padding: 20px; border-radius: 8px; margin: 25px 0; border-left: 4px solid #f59e0b;">
                            <h3 style="margin: 0 0 15px 0; color: #c2410c;">Promotion Details</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 8px 0; color: #666;">Valid Until:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get("valid_until", "Dec 31, 2025")}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Minimum Order:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{fmt_currency(customer_data.get("min_order", 500))}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Applies To:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get("product_category", "All Products")}</td></tr>
                            </table>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;"><strong>Why this offer is perfect for you:</strong></p>
                        <ul style="font-size: 16px; line-height: 1.8; color: #333;">
                            <li>Save on your favorite PepsiCo products</li>
                            <li>Stock up for the busy season ahead</li>
                            <li>Exclusive pricing not available to everyone</li>
                            <li>Limited time - expires soon!</li>
                        </ul>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="#" style="background: #d97706; color: white; padding: 16px 40px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px; display: inline-block;">🛒 Shop Now & Save</a>
                        </div>
                        
                        <p style="font-size: 14px; line-height: 1.6; color: #666; margin-top: 25px;"><em>*Terms and conditions apply. Offer valid for select customers. Cannot be combined with other promotions.</em></p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">Don't miss out!<br><strong>The PepsiCo Sales Team</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'order_confirmation': {
            'subject': f'✅ Order Confirmed - #{customer_data.get("order_id", "ORD-12345")}',
            'preview_text': f'Your order of {fmt_currency(customer_data.get("order_total", 0))} is confirmed',
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 28px;">✅ Order Confirmed!</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95;">Thank you for your order</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">Great news! Your order has been confirmed and is being processed.</p>
                        
                        <div style="background: linear-gradient(135deg, #f0fdf4, #dcfce7); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 4px solid #10b981;">
                            <h3 style="margin: 0 0 15px 0; color: #059669;">Order Details</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 10px 0; color: #666;">Order Number:</td><td style="padding: 10px 0; text-align: right; font-weight: 700; font-size: 16px;">{customer_data.get("order_id", "ORD-12345")}</td></tr>
                                <tr><td style="padding: 10px 0; color: #666;">Order Date:</td><td style="padding: 10px 0; text-align: right; font-weight: 600;">{customer_data.get("order_date", "Today")}</td></tr>
                                <tr><td style="padding: 10px 0; color: #666;">Estimated Delivery:</td><td style="padding: 10px 0; text-align: right; font-weight: 600;">{customer_data.get("delivery_date", "5-7 business days")}</td></tr>
                                <tr style="border-top: 2px solid #10b981;"><td style="padding: 12px 0; font-size: 18px; font-weight: 600;">Order Total:</td><td style="padding: 12px 0; text-align: right; font-size: 22px; font-weight: 700; color: #059669;">{fmt_currency(customer_data.get("order_total", 0))}</td></tr>
                            </table>
                        </div>
                        
                        <h3 style="color: #059669; margin: 30px 0 15px;">📦 What's Next?</h3>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0; border-left: 3px solid #10b981;">
                            <p style="margin: 0; font-weight: 600; color: #333;">1. Order Processing</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Your order is being prepared (24-48 hours)</p>
                        </div>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0; border-left: 3px solid #10b981;">
                            <p style="margin: 0; font-weight: 600; color: #333;">2. Shipment</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">You'll receive a tracking number via email</p>
                        </div>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0; border-left: 3px solid #10b981;">
                            <p style="margin: 0; font-weight: 600; color: #333;">3. Delivery</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Arrival within {customer_data.get("delivery_date", "5-7 business days")}</p>
                        </div>
                        
                        <div style="background: #0054a6; color: white; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                            <p style="margin: 0; font-size: 14px; opacity: 0.9;">Need help with your order?</p>
                            <p style="margin: 10px 0 0; font-size: 16px; font-weight: 600;">Contact us: 1-800-PEPSICO</p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">Thank you for choosing PepsiCo! We appreciate your business and look forward to serving you again.</p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">Best regards,<br><strong>PepsiCo Order Fulfillment Team</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'welcome': {
            'subject': f'👋 Welcome to PepsiCo, {recipient_name}!',
            'preview_text': f'Enjoy {customer_data.get("welcome_discount", "10%")} off your first order',
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #ec4899, #db2777); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 36px;">👋 Welcome!</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95; font-size: 18px;">We're thrilled to have you</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">Welcome to the PepsiCo family! We're excited to begin this partnership with you and look forward to supporting your business growth.</p>
                        
                        <div style="background: linear-gradient(135deg, #fdf2f8, #fce7f3); padding: 30px; border-radius: 12px; margin: 25px 0; border: 3px dashed #ec4899; text-align: center;">
                            <p style="margin: 0; font-size: 14px; color: #9f1239; font-weight: 600; text-transform: uppercase;">Welcome Gift</p>
                            <p style="margin: 15px 0; font-size: 48px; font-weight: 700; color: #db2777; line-height: 1;">{customer_data.get("welcome_discount", "10%")}</p>
                            <p style="margin: 0; font-size: 18px; color: #9f1239; font-weight: 600;">OFF Your First Order</p>
                            <div style="background: white; padding: 12px 24px; border-radius: 25px; margin: 20px auto 0; display: inline-block;">
                                <p style="margin: 0; font-size: 16px; color: #db2777; font-weight: 700; letter-spacing: 2px;">Code: <span style="font-size: 20px;">WELCOME10</span></p>
                            </div>
                        </div>
                        
                        <h3 style="color: #db2777; margin: 30px 0 15px;">🎯 Why Partner With PepsiCo?</h3>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0;">
                            <p style="margin: 0; font-weight: 600; color: #333;">✨ Premium Product Portfolio</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Access to world-class beverage and snack brands</p>
                        </div>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0;">
                            <p style="margin: 0; font-weight: 600; color: #333;">📞 Dedicated Support</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Your personal account manager is here to help</p>
                        </div>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0;">
                            <p style="margin: 0; font-weight: 600; color: #333;">🚚 Reliable Delivery</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">On-time delivery you can count on</p>
                        </div>
                        <div style="background: #f8f9fa; padding: 15px 20px; border-radius: 8px; margin: 10px 0;">
                            <p style="margin: 0; font-weight: 600; color: #333;">💰 Competitive Pricing</p>
                            <p style="margin: 5px 0 0; font-size: 14px; color: #666;">Best value for premium quality</p>
                        </div>
                        
                        <div style="background: #0054a6; color: white; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                            <p style="margin: 0; font-size: 16px; font-weight: 600;">🚀 Ready to Get Started?</p>
                            <p style="margin: 12px 0 0; font-size: 14px; opacity: 0.9;">Reply to this email or call us to place your first order</p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">We're here to answer any questions you may have. Don't hesitate to reach out – we're committed to your success!</p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">Here's to a successful partnership!<br><strong>The PepsiCo Onboarding Team</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        },
        'win_back': {
            'subject': f'We Miss You, {recipient_name}! 🔙 Special Offer Inside',
            'preview_text': f'Come back and save {customer_data.get("incentive", "20%")} on your next order',
            'body': f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f6fb;">
                    <div style="background: linear-gradient(135deg, #6366f1, #4f46e5); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0;">
                        <h1 style="margin: 0; font-size: 32px;">We Miss You! 🔙</h1>
                        <p style="margin: 12px 0 0; opacity: 0.95; font-size: 16px;">Come back and save big</p>
                    </div>
                    <div style="padding: 40px 30px; background: #ffffff;">
                        <p style="font-size: 16px; line-height: 1.6;">Dear {recipient_name},</p>
                        <p style="font-size: 16px; line-height: 1.6;">We noticed it's been <strong>{customer_data.get("days_inactive", 180)} days</strong> since your last order, and we miss working with you!</p>
                        
                        <div style="background: linear-gradient(135deg, #eef2ff, #e0e7ff); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 4px solid #6366f1;">
                            <h3 style="margin: 0 0 15px 0; color: #4338ca;">Your Account History</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 8px 0; color: #666;">Previous Total Spent:</td><td style="padding: 8px 0; text-align: right; font-weight: 700; font-size: 18px; color: #4f46e5;">{fmt_currency(customer_data.get("total_spent", 0))}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Orders Placed:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get("order_count", "Many")}</td></tr>
                                <tr><td style="padding: 8px 0; color: #666;">Last Order:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{customer_data.get("last_order_date", "Some time ago")}</td></tr>
                            </table>
                        </div>
                        
                        <div style="background: linear-gradient(135deg, #fef3c7, #fde68a); padding: 30px; border-radius: 12px; margin: 25px 0; border: 3px dashed #f59e0b; text-align: center;">
                            <p style="margin: 0; font-size: 14px; color: #92400e; font-weight: 600; text-transform: uppercase;">Exclusive Win-Back Offer</p>
                            <p style="margin: 15px 0; font-size: 48px; font-weight: 700; color: #d97706; line-height: 1;">{customer_data.get("incentive", "20%")}</p>
                            <p style="margin: 0; font-size: 18px; color: #92400e; font-weight: 600;">OFF Your Return Order</p>
                            <div style="background: white; padding: 12px 24px; border-radius: 25px; margin: 20px auto 0; display: inline-block;">
                                <p style="margin: 0; font-size: 16px; color: #d97706; font-weight: 700; letter-spacing: 2px;">Code: <span style="font-size: 20px;">COMEBACK20</span></p>
                            </div>
                            <p style="margin: 15px 0 0; font-size: 12px; color: #92400e;">⏰ Limited time offer - expires in 30 days</p>
                        </div>
                        
                        <h3 style="color: #4f46e5; margin: 30px 0 15px;">✨ What's New at PepsiCo</h3>
                        <ul style="font-size: 16px; line-height: 1.8; color: #333;">
                            <li><strong>New Products:</strong> Exciting additions to our portfolio</li>
                            <li><strong>Better Pricing:</strong> More competitive rates than ever</li>
                            <li><strong>Improved Service:</strong> Faster delivery and support</li>
                            <li><strong>Exclusive Deals:</strong> Special offers for returning customers</li>
                        </ul>
                        
                        <div style="background: #0054a6; color: white; padding: 20px; border-radius: 8px; margin: 25px 0; text-align: center;">
                            <p style="margin: 0; font-size: 18px; font-weight: 600;">💬 Let's Reconnect</p>
                            <p style="margin: 12px 0 0; font-size: 14px; opacity: 0.9;">Reply to this email or call <strong>1-800-PEPSICO</strong></p>
                            <p style="margin: 8px 0 0; font-size: 14px; opacity: 0.9;">We'd love to hear from you!</p>
                        </div>
                        
                        <p style="font-size: 16px; line-height: 1.6;">We value your business and would love the opportunity to serve you again. This special offer is our way of saying "welcome back!"</p>
                        
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 30px;">We hope to hear from you soon!<br><strong>Your Friends at PepsiCo</strong></p>
                    </div>
                    <div style="background: #f5f6fb; padding: 20px 30px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                        <p style="margin: 0;">© 2025 PepsiCo. All rights reserved.</p>
                    </div>
                </div>
            """
        }
    }
    
    template = templates.get(email_type, templates['appreciation'])
    template['generated_by'] = 'fallback'
    return template