# 📧 Automated Email Alerts for Unpaid Invoices

This guide explains how to automatically send email reminders when customers have unpaid invoices using either **Zapier** or **n8n**.

---

## 🎯 Overview

The system sends automated email alerts to **mundisgl@gmail.com** (and optionally to customers) when invoices are overdue based on the `Sales_CustomerTransactions` table's `OutstandingBalance` field.

### Key Features:
- ✅ Automatic detection of unpaid invoices
- ✅ Configurable overdue threshold (e.g., 30+ days)
- ✅ Customer contact information included
- ✅ Professional HTML email templates
- ✅ Scheduled daily/weekly checks
- ✅ Always CC mundisgl@gmail.com

---

## 📊 API Endpoint

### **GET** `/api/unpaid-invoices`

**Base URL:** `http://localhost:8000/api/unpaid-invoices`

**Query Parameters:**
- `days_overdue` (int, default: 0) - Minimum days past payment terms (0 = all unpaid)
- `limit` (int, default: 100) - Maximum number of records to return

**Example Request:**
```bash
curl "http://localhost:8000/api/unpaid-invoices?days_overdue=30&limit=50"
```

**Example Response:**
```json
{
  "count": 3,
  "total_outstanding": 15420.50,
  "generated_at": "2025-11-15T09:00:00.000Z",
  "unpaid_invoices": [
    {
      "customer_id": 123,
      "customer_name": "Acme Corporation",
      "phone_number": "+1-555-0123",
      "contact_email": "accounts@acme.com",
      "contact_name": "John Doe",
      "invoice_id": 45678,
      "invoice_date": "2025-09-15",
      "transaction_date": "2025-09-15",
      "transaction_amount": 5250.00,
      "outstanding_balance": 5250.00,
      "days_overdue": 45,
      "payment_terms_days": 30,
      "salesperson_name": "Jane Smith",
      "salesperson_email": "jane.smith@pepsico.com"
    }
  ]
}
```

---

## 🔧 Option 1: n8n Setup (Recommended - Free & Self-Hosted)

### Prerequisites
1. Install n8n: `npm install n8n -g` or use Docker
2. SMTP email credentials (Gmail, SendGrid, etc.)
3. Your server accessible at `http://localhost:8000`

### Step-by-Step Setup

#### 1. Start n8n
```bash
n8n start
```
Access n8n at http://localhost:5678

#### 2. Import the Workflow
1. Click **"Workflows"** → **"Import from File"**
2. Select `n8n_unpaid_invoices_workflow.json`
3. The workflow will be imported with all nodes configured

#### 3. Configure SMTP Credentials
1. Click on the **"Send Email Reminder"** node
2. Click **"Create New Credential"**
3. Choose your email provider:
   - **Gmail**: Use App Password (not regular password)
   - **SendGrid**: Use API Key
   - **Custom SMTP**: Enter server details

**Gmail Setup:**
- Host: `smtp.gmail.com`
- Port: `465` (SSL) or `587` (TLS)
- User: Your Gmail address
- Password: [Generate App Password](https://myaccount.google.com/apppasswords)
- From Email: Your Gmail address

#### 4. Update Email Settings
In the **"Send Email Reminder"** node:
- **CC Email**: `mundisgl@gmail.com` (already configured)
- **From Email**: Your email address
- **Sender Name**: PepsiCo Accounts Receivable

#### 5. Adjust Schedule (Optional)
In the **"Schedule Trigger"** node:
- Default: Weekdays at 9 AM (`0 9 * * 1-5`)
- Custom: Edit cron expression
  - Daily at 8 AM: `0 8 * * *`
  - Every Monday at 10 AM: `0 10 * * 1`
  - Twice daily (9 AM & 5 PM): `0 9,17 * * *`

#### 6. Test the Workflow
1. Click **"Execute Workflow"** button
2. Check the execution log for any errors
3. Verify email delivery to mundisgl@gmail.com

#### 7. Activate the Workflow
Toggle the **"Active"** switch at the top right to enable automatic execution.

---

## ⚡ Option 2: Zapier Setup

### Prerequisites
1. Zapier account (Free tier works)
2. Email service connected (Gmail recommended)

### Step-by-Step Setup

#### 1. Create a New Zap
1. Go to [zapier.com](https://zapier.com) → **"Create Zap"**
2. Name it: "PepsiCo Unpaid Invoices Alert"

#### 2. Add Trigger
1. **Trigger**: Choose **"Schedule by Zapier"**
2. **Event**: Every Day
3. **Time of Day**: 9:00 AM
4. **Time Zone**: Your timezone

#### 3. Add Webhooks by Zapier
1. Click **"+"** to add an action
2. Choose **"Webhooks by Zapier"**
3. **Action Event**: GET
4. **URL**: `http://localhost:8000/api/unpaid-invoices?days_overdue=30&limit=100`
   - ⚠️ **Important**: If running locally, use [ngrok](https://ngrok.com) to expose your server:
     ```bash
     ngrok http 8000
     ```
     Then use the ngrok URL: `https://abc123.ngrok.io/api/unpaid-invoices`

5. Test the webhook and verify data is returned

#### 4. Add Filter (Optional)
1. Click **"+"** → **"Filter"**
2. **Condition**: Only continue if...
   - `count` (Number) Greater than `0`
3. This prevents emails when no invoices are overdue

#### 5. Add Looping by Zapier
1. Click **"+"** → **"Looping by Zapier"**
2. **Create Loop From Line Items**: Yes
3. **Input**: Select `unpaid_invoices` from webhook data
4. This will process each invoice individually

#### 6. Add Gmail Send Email
1. Click **"+"** → **"Gmail"** → **"Send Email"**
2. Connect your Gmail account
3. Configure email:

**To**: `{{customer_email}}` (from loop data)
**CC**: `mundisgl@gmail.com`
**Subject**: `Payment Reminder - Invoice #{{invoice_id}} Overdue`

**Body (HTML)**:
```html
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: linear-gradient(135deg, #0054a6 0%, #003d79 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }
    .content { background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }
    .invoice-details { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }
    .amount { font-size: 24px; color: #d32f2f; font-weight: bold; }
    .footer { background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Payment Reminder</h1>
    </div>
    <div class="content">
      <p>Dear {{contact_name}},</p>
      
      <p>This is a friendly reminder that we have an outstanding invoice that requires your attention.</p>
      
      <div class="invoice-details">
        <h3>Invoice Details</h3>
        <p><strong>Customer:</strong> {{customer_name}}</p>
        <p><strong>Invoice #:</strong> {{invoice_id}}</p>
        <p><strong>Invoice Date:</strong> {{invoice_date}}</p>
        <p><strong>Original Amount:</strong> ${{transaction_amount}}</p>
        <p><strong>Outstanding Balance:</strong> <span class="amount">${{outstanding_balance}}</span></p>
        <p><strong>Days Overdue:</strong> {{days_overdue}} days</p>
        <p><strong>Payment Terms:</strong> Net {{payment_terms_days}} days</p>
      </div>
      
      <p>Please remit payment at your earliest convenience to avoid any service interruption or late fees.</p>
      
      <p>If you have already sent payment, please disregard this notice.</p>
      
      <p><strong>Questions?</strong> Contact {{salesperson_name}} at {{salesperson_email}}</p>
      
      <p>Best regards,<br>
      <strong>PepsiCo Accounts Receivable</strong></p>
    </div>
    <div class="footer">
      <p>This is an automated reminder from PepsiCo Sales Analytics System</p>
      <p>&copy; 2025 PepsiCo. All rights reserved.</p>
    </div>
  </div>
</body>
</html>
```

#### 7. Test & Activate
1. Click **"Test & Continue"** on each step
2. Verify email arrives at mundisgl@gmail.com
3. Turn on the Zap

---

## 🔐 Production Deployment Notes

### For Public/Remote Access:

1. **Deploy to Cloud** (Recommended)
   - Deploy your FastAPI app to Heroku, AWS, Azure, or DigitalOcean
   - Update the API URL in your automation workflow

2. **Use ngrok** (Quick Testing)
   ```bash
   ngrok http 8000
   ```
   - Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)
   - Use this in Zapier/n8n instead of localhost

3. **Secure the Endpoint** (Optional)
   - Add API key authentication
   - Use HTTPS only
   - Restrict IP addresses

### Email Provider Recommendations:
- **SendGrid**: 100 emails/day free
- **Gmail**: 500 emails/day (with App Password)
- **AWS SES**: Pay as you go, very cheap
- **Mailgun**: 5,000 emails/month free

---

## 📋 Customization Options

### Adjust Overdue Threshold
Change `days_overdue` parameter:
- `0` = All unpaid invoices
- `7` = 7+ days overdue
- `30` = 30+ days overdue (recommended)
- `60` = 60+ days overdue (critical)

### Multiple Alert Levels
Create separate workflows for different thresholds:
1. **Warning**: 7 days overdue → Friendly reminder
2. **Urgent**: 30 days overdue → Firm reminder
3. **Critical**: 60+ days overdue → Final notice

### Custom Email Recipients
In n8n or Zapier, modify the email node to send to:
- Customer contact
- Account manager (mundisgl@gmail.com)
- Sales rep
- Finance team

---

## 🧪 Testing

### Test the API Endpoint
```bash
# Get all unpaid invoices
curl http://localhost:8000/api/unpaid-invoices

# Get invoices 30+ days overdue
curl "http://localhost:8000/api/unpaid-invoices?days_overdue=30"

# Limit results
curl "http://localhost:8000/api/unpaid-invoices?days_overdue=30&limit=10"
```

### Test Email Delivery
1. Manually trigger the workflow
2. Check spam folder if email doesn't arrive
3. Verify all fields are populated correctly
4. Confirm CC to mundisgl@gmail.com works

---

## 🛠️ Troubleshooting

### Common Issues:

**Issue**: "Connection refused" or "Can't reach localhost"
- **Solution**: Use ngrok or deploy to a public server

**Issue**: Emails not sending
- **Solution**: Check SMTP credentials, enable "Less secure apps" for Gmail, or use App Password

**Issue**: No data returned from API
- **Solution**: Verify the database has unpaid invoices with `OutstandingBalance > 0`

**Issue**: Emails go to spam
- **Solution**: Add SPF/DKIM records, use a verified domain, or use a professional email service

**Issue**: Workflow runs but no emails
- **Solution**: Check the filter/condition - may be filtering out all records

---

## 📞 Support

For questions or issues:
- **Email**: mundisgl@gmail.com
- **API Documentation**: http://localhost:8000/docs
- **n8n Docs**: https://docs.n8n.io
- **Zapier Help**: https://help.zapier.com

---

## 🚀 Next Steps

1. ✅ Test the API endpoint manually
2. ✅ Set up n8n or Zapier workflow
3. ✅ Configure email credentials
4. ✅ Test with a single invoice
5. ✅ Activate automatic scheduling
6. ✅ Monitor for a week to ensure reliability
7. ✅ Adjust thresholds and schedules as needed

**Automation Status**: Ready to deploy! 🎉

