# ⚡ Quick Start: Unpaid Invoices Email Automation

## 🎯 What This Does

Automatically sends email alerts to **mundisgl@gmail.com** when customers have unpaid invoices.

---

## 🚀 Quick Test

### 1. Check the API Endpoint

Open your browser and visit:
```
http://localhost:8000/docs
```

Find the `/api/unpaid-invoices` endpoint and click **"Try it out"**.

### 2. Test with curl

```bash
# Get all unpaid invoices
curl "http://localhost:8000/api/unpaid-invoices?days_overdue=0&limit=10"

# Get invoices 30+ days overdue
curl "http://localhost:8000/api/unpaid-invoices?days_overdue=30&limit=10"
```

**Expected Response:**
```json
{
  "count": 0,
  "total_outstanding": 0,
  "unpaid_invoices": [],
  "generated_at": "2025-11-15T13:47:31.000Z",
  "message": "No unpaid invoices found"
}
```

*Note: If count is 0, your database has no unpaid invoices (all are paid up - great!)*

---

## 📧 Setup Email Automation

### Option A: n8n (Recommended - Free)

1. **Install n8n:**
   ```bash
   npm install n8n -g
   n8n start
   ```

2. **Import Workflow:**
   - Open http://localhost:5678
   - Click "Workflows" → "Import from File"
   - Select `n8n_unpaid_invoices_workflow.json`

3. **Configure SMTP:**
   - Click "Send Email Reminder" node
   - Add your email credentials (Gmail, SendGrid, etc.)
   - For Gmail: Use [App Password](https://myaccount.google.com/apppasswords)

4. **Activate:**
   - Toggle "Active" switch
   - Runs every weekday at 9 AM

### Option B: Zapier

1. **Create Zap** at zapier.com
2. **Trigger:** Schedule (Daily at 9 AM)
3. **Action:** Webhooks by Zapier → GET
   - URL: `http://localhost:8000/api/unpaid-invoices?days_overdue=30`
   - *For production: Use ngrok or deploy to cloud*
4. **Action:** Gmail → Send Email
   - To: `{{contact_email}}`
   - CC: `mundisgl@gmail.com`
   - Subject: Payment Reminder - Invoice Overdue

**Full setup guide:** See `AUTOMATION_SETUP.md`

---

## 🔌 For Remote/Cloud Access

If your server isn't on localhost, use **ngrok**:

```bash
# Install ngrok
# Download from https://ngrok.com

# Expose your local server
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`) and use it in your automation:
```
https://abc123.ngrok.io/api/unpaid-invoices?days_overdue=30
```

---

## 📋 Files Created

1. **`analytics.py`** - Added `get_unpaid_invoices()` function
2. **`app.py`** - Added `/api/unpaid-invoices` webhook endpoint
3. **`n8n_unpaid_invoices_workflow.json`** - Pre-configured n8n workflow
4. **`AUTOMATION_SETUP.md`** - Detailed setup instructions
5. **`INTEGRATION_QUICKSTART.md`** - This file (quick reference)

---

## 🎨 Database Tables Used

- `Sales_CustomerTransactions` - OutstandingBalance field (key!)
- `Sales_Customers` - Customer info and PaymentDays
- `Sales_Invoices` - Invoice details
- `Application_People` - Contact email addresses

---

## ✅ What's Working Now

✅ API endpoint live at `/api/unpaid-invoices`  
✅ Returns customer names, emails, invoice details  
✅ Calculates days overdue automatically  
✅ Includes salesperson contact info  
✅ Ready for Zapier or n8n integration  
✅ Professional HTML email templates provided  
✅ Always CC to mundisgl@gmail.com  

---

## 📞 Need Help?

**View Full Documentation:**
```bash
cd Sales_agent/agent_project
cat AUTOMATION_SETUP.md
```

**Test the Endpoint:**
```
http://localhost:8000/docs#/default/api_unpaid_invoices_api_unpaid_invoices_get
```

**Email:** mundisgl@gmail.com

---

## 🔥 Quick Deploy Checklist

- [ ] Server running on port 8000
- [ ] Test API endpoint returns data
- [ ] Choose automation tool (n8n or Zapier)
- [ ] Configure SMTP email credentials
- [ ] Import/create workflow
- [ ] Test email delivery
- [ ] Activate automated schedule
- [ ] Monitor for 24 hours

**Ready to automate!** 🚀

