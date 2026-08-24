# InvoiceSync — lightweight invoicing for freelancers

Stop copying 60–90 minutes every month from Toggl/Clockify + spreadsheets into invoice templates. InvoiceSync pulls tracked hours, builds branded PDFs, and emails clients.

Single process, runs locally with `python app.py`, debuggable with `print()`, server-rendered HTML.

## Stack (strict per spec)
- **Python FastAPI** (backend) + **SQLite** (no Postgres) + **HTMX** + **Tailwind via CDN** (no React/Node build) + **Stripe** + **reportlab** (no WeasyPrint/Cairo)
- Deps: `fastapi uvicorn[standard] jinja2 python-multipart reportlab stripe requests` only

## Features (MVP only)
1. **Auth**: register/login/logout, PBKDF2 hash, httpOnly cookie sessions
2. **Clients**: name, email, currency, hourly rate, custom fields (PO number, tax ID)
3. **Time import**: store Toggl/Clockify API token, call REST API for date range, fallback to manual CSV paste
4. **Generate invoice**: pick client + date range → pulls `time_entries` → line items → preview → branded PDF
5. **PDF**: reportlab `pdf.py`, download + email via SMTP
6. **Recurring**: monthly recurring template, internal `asyncio` loop every 60s (also `POST /invoices/recurring/run`)
7. **Stripe**: $12/mo or $99/yr via Checkout + webhook `free` (5/mo) → `pro` (unlimited)

## Quick start
```bash
pip install -r requirements.txt
# optional env
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
export STRIPE_PRICE_MONTHLY=price_...  # else ad-hoc $12 created
export STRIPE_PRICE_ANNUAL=price_...   # else ad-hoc $99
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587 SMTP_USER=you@example.com SMTP_PASS=... SMTP_FROM=...
export DB_PATH=./invoicesync.db

python app.py
# http://localhost:8000
```

## Routes
```
GET  /, /login, /register, /dashboard
POST /register, /login, /logout
GET/POST /clients, /clients/{id}
POST /import-time
GET/POST /invoices/new, POST /invoices/{id}/send, GET /invoices/{id}/pdf, GET /invoices/{id}
POST /invoices/recurring/run
GET  /billing, POST /billing/checkout, POST /stripe/webhook
```

## CSV fallback format
```
description,seconds,date
Design,7200,2026-08-01
Dev,2.5h,2026-08-02   # also supports 2.5, 2.5h, 01:30:00
```

## Stripe test
Without keys, checkout redirects to `https://checkout.stripe.com/pay/test_invoice_sync`. Webhook without signature:
```bash
curl -X POST http://localhost:8000/stripe/webhook -H 'Content-Type: application/json' \
  -d '{"type":"checkout.session.completed","data":{"object":{"customer_email":"you@example.com"}}}'
```

## Free tier enforcement
`free` → 5 invoices/month; 6th returns `200` with clear upgrade message on `GET/POST /invoices/new`. `pro` unlimited.

## Project status
Tests: register 303, add client, CSV import, invoice amount, PDF, Stripe redirect, limit block, recurring, email.
