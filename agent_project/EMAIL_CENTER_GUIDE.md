# 📧 Email Center - Complete Guide

## 🎉 What's New

Your PepsiCo Sales Analytics dashboard now has an **AI-Powered Email Center** that generates personalized emails using OpenAI!

---

## ✨ Features

### 8 Email Types Available:

1. **💰 Payment Reminder** - Professional reminders for overdue invoices
2. **🙏 Customer Appreciation** - Thank loyal customers
3. **🛍️ Product Recommendation** - Suggest products based on purchase history
4. **📞 Follow-up** - Check in after interactions
5. **🎉 Seasonal Promotion** - Announce special offers
6. **✅ Order Confirmation** - Confirm order details
7. **👋 Welcome Email** - Greet new customers
8. **🔙 Win-Back Campaign** - Re-engage inactive customers

### Key Capabilities:

✅ **OpenAI Integration** - Generates unique, personalized emails  
✅ **Customer Search** - Find and select recipients easily  
✅ **Auto-populate Data** - Pulls customer info from database  
✅ **Live Preview** - See email before sending  
✅ **One-Click Send** - SMTP integration ready  
✅ **Always CC mundisgl@gmail.com** - Stay in the loop  

---

## 🚀 How to Use

### Step 1: Access Email Center

Open your dashboard: **http://localhost:8000**

Scroll down to the **Email Center** section (below Demand Forecasts)

### Step 2: Configure Email

1. **Select Email Type** from dropdown (default: Payment Reminder)
2. **Search for Customer** - Type name or email to filter
3. **Select Customer** from the list
4. **Add Context** (optional) - Any special notes or details

### Step 3: Generate with AI

Click **"Generate Email with AI"** button

- ⏳ OpenAI will craft a personalized email (takes 3-10 seconds)
- ✨ Email appears in the preview panel
- 📝 Subject line, preview text, and full HTML body generated

### Step 4: Review & Send

- **Preview** the email in the right panel
- **Regenerate** if you want a different version
- **Send Email** - Automatically CCs mundisgl@gmail.com

---

## 🔧 Setup SMTP (Required for Sending)

The system can generate emails right now, but to **send** them, you need SMTP credentials.

### Option 1: Use Gmail

1. Enable 2-Factor Authentication on your Gmail
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Set environment variables in `run_server.py`:

```python
os.environ['SMTP_SERVER'] = 'smtp.gmail.com'
os.environ['SMTP_PORT'] = '587'
os.environ['SMTP_USERNAME'] = 'your-email@gmail.com'
os.environ['SMTP_PASSWORD'] = 'your-app-password'
```

### Option 2: Use SendGrid

```python
os.environ['SMTP_SERVER'] = 'smtp.sendgrid.net'
os.environ['SMTP_PORT'] = '587'
os.environ['SMTP_USERNAME'] = 'apikey'
os.environ['SMTP_PASSWORD'] = 'your-sendgrid-api-key'
```

**Restart the server** after adding credentials.

---

## 📊 API Endpoints

### 1. Get Customer List
```http
GET /api/customers-list?limit=100&search=acme
```

Returns customers with email addresses.

### 2. Generate Email Draft
```http
POST /api/generate-email-draft
Content-Type: application/json

{
  "email_type": "appreciation",
  "recipient_name": "John Doe",
  "recipient_email": "john@example.com",
  "customer_id": 123,
  "additional_context": "Thank them for 5 years of partnership"
}
```

Returns AI-generated email with subject, preview, and HTML body.

### 3. Send Email
```http
POST /api/send-email
Content-Type: application/json

{
  "to_email": "customer@example.com",
  "subject": "Thank You!",
  "body_html": "<html>...</html>",
  "cc_email": "mundisgl@gmail.com"
}
```

Sends email via SMTP.

---

## 🎨 Email Templates

Each email type has specific context and tone:

| Type | Tone | Use Case |
|------|------|----------|
| Payment Reminder | Professional & Firm | Overdue invoices |
| Appreciation | Warm & Grateful | Thank loyal customers |
| Product Recommendation | Enthusiastic | Cross-sell/upsell |
| Follow-up | Friendly & Helpful | Post-interaction check-in |
| Seasonal Promotion | Exciting | Limited-time offers |
| Order Confirmation | Clear & Reassuring | Confirm purchases |
| Welcome | Welcoming | New customer onboarding |
| Win-Back | Enticing | Re-engage inactive customers |

---

## 💡 Tips for Best Results

1. **Select the right customer** - The AI uses their purchase history
2. **Add context** - Specific details make better emails
3. **Review before sending** - Always preview first
4. **Regenerate if needed** - Each generation is unique
5. **Test with yourself** - Send to your own email first

---

## 🤖 How AI Generation Works

1. **Fetches customer data** from database (spending, invoices, etc.)
2. **Builds context** specific to email type
3. **Calls OpenAI API** with detailed prompt
4. **Returns** subject, preview text, and HTML body
5. **Falls back** to templates if OpenAI unavailable

---

## 🔍 Example Workflow

**Scenario**: Send appreciation email to top customer

1. Select "Customer Appreciation" from dropdown
2. Search for "Tailspin Toys"
3. Select "Tailspin Toys (Aarav Sai) - aarav@tailspintoys.com"
4. Add context: "Thank them for being our #1 customer in Q4"
5. Click "Generate Email with AI"
6. Review the personalized email
7. Click "Send Email"
8. ✅ Email sent to customer + CC to mundisgl@gmail.com

---

## 📧 Always CC mundisgl@gmail.com

Every email sent through the system automatically CCs mundisgl@gmail.com so you stay informed of all communications.

---

## 🛠️ Troubleshooting

### "SMTP credentials not configured"
- Set SMTP environment variables in `run_server.py`
- Restart server after adding credentials

### "No customers with email found"
- Check database has contacts with email addresses
- Verify Application.People table has EmailAddress values

### "Failed to generate email"
- Check OpenAI API key is valid
- System will fall back to basic templates
- Check console logs for details

### Email generation is slow
- Normal! OpenAI takes 3-10 seconds
- Consider caching common templates

---

## 📂 Files Modified

1. **agent.py** - Added `generate_email_draft()` and `generate_fallback_email()`
2. **app.py** - Added email endpoints and SMTP integration
3. **index.html** - Added Email Center UI section
4. **run_server.py** - Environment variables for SMTP

---

## 🎯 Next Steps

1. ✅ Configure SMTP credentials
2. ✅ Test email generation
3. ✅ Send test email to yourself
4. ✅ Use in production!

---

## 🌟 Pro Tips

- **Batch campaigns**: Generate multiple emails and review before sending
- **A/B testing**: Regenerate emails to test different messaging
- **Personalization**: Add specific context for better results
- **Automation**: Use n8n workflow for scheduled campaigns
- **Analytics**: Track open rates (requires email service provider)

---

## ✨ Status

✅ Server Running: http://localhost:8000  
✅ Email Center Live  
✅ OpenAI Integration Active  
✅ 8 Email Templates Ready  
✅ Customer Database Connected  
🔧 SMTP: Configure to enable sending  

**Ready to send personalized emails powered by AI!** 🚀

