"""PDF generation via reportlab — lightweight, no Cairo."""
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors

BRAND = HexColor("#2563EB")
DARK = HexColor("#0F172A")
MUTED = HexColor("#64748B")
BG_LIGHT = HexColor("#F1F5F9")

ZERO_DECIMAL_SET = {
    "JPY", "KRW", "VND", "CLP", "BIF", "DJF", "GNF", "KMF", "MGA", "PYG", "RWF", "UGX", "VUV", "XAF", "XOF", "XPF"
}
ZERO_DECIMAL_CURRENCIES = {c.lower() for c in ZERO_DECIMAL_SET}

TOP_CURRENCIES = [
    {"code": "USD", "symbol": "$", "name": "US Dollar", "decimals": 2},
    {"code": "EUR", "symbol": "€", "name": "Euro", "decimals": 2},
    {"code": "GBP", "symbol": "£", "name": "British Pound", "decimals": 2},
    {"code": "JPY", "symbol": "¥", "name": "Japanese Yen", "decimals": 0},
    {"code": "CAD", "symbol": "CA$", "name": "Canadian Dollar", "decimals": 2},
    {"code": "AUD", "symbol": "A$", "name": "Australian Dollar", "decimals": 2},
    {"code": "CHF", "symbol": "CHF", "name": "Swiss Franc", "decimals": 2},
    {"code": "SGD", "symbol": "S$", "name": "Singapore Dollar", "decimals": 2},
    {"code": "INR", "symbol": "₹", "name": "Indian Rupee", "decimals": 2},
    {"code": "NZD", "symbol": "NZ$", "name": "New Zealand Dollar", "decimals": 2},
    {"code": "CNY", "symbol": "¥", "name": "Chinese Yuan", "decimals": 2},
    {"code": "HKD", "symbol": "HK$", "name": "Hong Kong Dollar", "decimals": 2},
    {"code": "BRL", "symbol": "R$", "name": "Brazilian Real", "decimals": 2},
    {"code": "MXN", "symbol": "MX$", "name": "Mexican Peso", "decimals": 2},
    {"code": "SEK", "symbol": "kr", "name": "Swedish Krona", "decimals": 2},
    {"code": "NOK", "symbol": "kr", "name": "Norwegian Krone", "decimals": 2},
    {"code": "DKK", "symbol": "kr", "name": "Danish Krone", "decimals": 2},
    {"code": "PLN", "symbol": "zł", "name": "Polish Zloty", "decimals": 2},
    {"code": "ZAR", "symbol": "R", "name": "South African Rand", "decimals": 2},
    {"code": "AED", "symbol": "AED", "name": "UAE Dirham", "decimals": 2},
    {"code": "SAR", "symbol": "SAR", "name": "Saudi Riyal", "decimals": 2},
    {"code": "KRW", "symbol": "₩", "name": "South Korean Won", "decimals": 0},
    {"code": "THB", "symbol": "฿", "name": "Thai Baht", "decimals": 2},
    {"code": "IDR", "symbol": "Rp", "name": "Indonesian Rupiah", "decimals": 2},
    {"code": "MYR", "symbol": "RM", "name": "Malaysian Ringgit", "decimals": 2},
    {"code": "PHP", "symbol": "₱", "name": "Philippine Peso", "decimals": 2},
    {"code": "VND", "symbol": "₫", "name": "Vietnamese Dong", "decimals": 0},
    {"code": "TRY", "symbol": "₺", "name": "Turkish Lira", "decimals": 2},
    {"code": "ILS", "symbol": "₪", "name": "Israeli Shekel", "decimals": 2},
    {"code": "CZK", "symbol": "Kč", "name": "Czech Koruna", "decimals": 2},
    {"code": "CLP", "symbol": "CLP$", "name": "Chilean Peso", "decimals": 0},
]

CURRENCY_SYMBOLS = {c["code"]: c["symbol"] for c in TOP_CURRENCIES}
CURRENCY_MAP = {c["code"]: c for c in TOP_CURRENCIES}

RATES_TO_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "JPY": 0.0067, "CAD": 0.74,
    "AUD": 0.65, "CHF": 1.12, "SGD": 0.75, "INR": 0.012, "NZD": 0.60,
    "CNY": 0.14, "HKD": 0.13, "BRL": 0.18, "MXN": 0.052, "SEK": 0.095,
    "NOK": 0.093, "DKK": 0.145, "PLN": 0.25, "ZAR": 0.055, "AED": 0.27,
    "SAR": 0.27, "KRW": 0.00073, "THB": 0.028, "IDR": 0.000062,
    "MYR": 0.22, "PHP": 0.017, "VND": 0.000039, "TRY": 0.029,
    "ILS": 0.27, "CZK": 0.043, "CLP": 0.0011,
}

def to_minor_units(amount: float, currency: str = "USD") -> int:
    curr = (currency or "USD").upper().strip()
    if curr in ZERO_DECIMAL_SET:
        return int(round(float(amount or 0)))
    return int(round(float(amount or 0) * 100))

def from_minor_units(minor: int, currency: str = "USD") -> float:
    curr = (currency or "USD").upper().strip()
    if curr in ZERO_DECIMAL_SET:
        return float(minor or 0)
    return round(float(minor or 0) / 100.0, 2)

# 5-locale formatter dict (stdlib only, ~40 LOC)
LOCALES_FORMAT = {
    "en-US": {"t": ",", "d": ".", "group": "std"},
    "en-IN": {"t": ",", "d": ".", "group": "in"},
    "de-DE": {"t": ".", "d": ",", "group": "std"},
    "fr-FR": {"t": "\u202f", "d": ",", "group": "std"},
    "ja-JP": {"t": ",", "d": ".", "group": "std"},
}

def format_locale_number(val: float, loc: str = "en-US", is_zero_dec: bool = False) -> str:
    cfg = LOCALES_FORMAT.get(loc, LOCALES_FORMAT["en-US"])
    t_sep, d_sep, grp = cfg["t"], cfg["d"], cfg["group"]
    abs_v = abs(val)
    if is_zero_dec:
        int_part = str(int(round(abs_v)))
        dec_part = ""
    else:
        rounded = round(abs_v, 2)
        int_part = str(int(rounded))
        dec_part = f"{rounded:.2f}".split(".")[1]

    if grp == "in" and len(int_part) > 3:
        last3 = int_part[-3:]
        rem = int_part[:-3]
        parts = []
        while len(rem) > 2:
            parts.append(rem[-2:])
            rem = rem[:-2]
        if rem:
            parts.append(rem)
        parts.reverse()
        grouped = t_sep.join(parts) + t_sep + last3
    else:
        parts = []
        rem = int_part
        while len(rem) > 3:
            parts.append(rem[-3:])
            rem = rem[:-3]
        if rem:
            parts.append(rem)
        parts.reverse()
        grouped = t_sep.join(parts)

    return grouped if is_zero_dec else f"{grouped}{d_sep}{dec_part}"

def fmt_money(amount, currency: str = "USD", locale: str = None) -> str:
    try:
        amt = float(amount or 0)
    except Exception:
        amt = 0.0
    curr = (currency or "USD").upper().strip()
    is_zero = curr in ZERO_DECIMAL_SET or curr.lower() in ZERO_DECIMAL_CURRENCIES
    symbol = CURRENCY_SYMBOLS.get(curr, curr + " ")
    sign = "-" if amt < 0 else ""
    if not locale:
        if curr == "INR":
            locale = "en-IN"
        elif curr == "JPY":
            locale = "ja-JP"
        else:
            locale = "en-US"
    num_str = format_locale_number(amt, locale, is_zero_dec=is_zero)
    return f"{sign}{symbol}{num_str} {curr}"

def generate_invoice_pdf(invoice, client, time_entries, user_email, user=None, out_dir="pdfs"):
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"{invoice['number']}.pdf")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
        title=f"Invoice {invoice['number']}",
        author="InvoiceSync",
    )

    styles = getSampleStyleSheet()
    s_title = styles["Title"].clone("t")
    s_title.fontSize = 22
    s_title.textColor = BRAND
    s_title.leading = 24

    s_h = styles["Heading2"].clone("h")
    s_h.fontSize = 11
    s_h.textColor = DARK
    s_h.spaceAfter = 4

    s_small = styles["Normal"].clone("sm")
    s_small.fontSize = 9
    s_small.textColor = MUTED
    s_small.leading = 12

    s_norm = styles["Normal"].clone("n")
    s_norm.fontSize = 10
    s_norm.leading = 13

    s_right = styles["Normal"].clone("r")
    s_right.fontSize = 10
    s_right.alignment = 2  # right
    s_right.leading = 13

    story = []

    # Header: brand / logo + invoice number
    u_dict = dict(user) if user else {}
    b_name = u_dict.get("business_name") or ""
    b_addr = u_dict.get("business_address") or ""
    b_city = u_dict.get("business_city") or ""
    b_country = u_dict.get("business_country") or ""
    b_tax = u_dict.get("business_tax_id") or ""
    b_logo = u_dict.get("logo_path") or ""

    header_left = []
    if b_logo and os.path.exists(b_logo):
        try:
            from reportlab.platypus import Image as RLImage
            header_left.append(RLImage(b_logo, width=28*mm, height=14*mm, kind='proportional'))
            header_left.append(Spacer(1, 2*mm))
        except Exception:
            pass
    brand_display = b_name if b_name else "InvoiceSync"
    sub_display = "Freelance invoicing, synced." if not b_name else "Professional Freelance Invoice"
    header_left.append(Paragraph(f'<b>{brand_display}</b><br/><font size=8 color="#64748B">{sub_display}</font>', s_small))

    header_data = [
        [header_left,
         Paragraph(f'<font size=22 color="#2563EB"><b>{invoice["number"]}</b></font><br/><font size=9 color="#64748B">{invoice["status"].upper()} • {invoice["period_start"]} → {invoice["period_end"]}</font>', s_right)]
    ]
    t = Table(header_data, colWidths=[85*mm, 85*mm])
    t.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0)]))
    story.append(t)
    story.append(Spacer(1, 6*mm))
    # line
    story.append(Table([[""]], colWidths=[170*mm], style=TableStyle([("LINEBELOW", (0,0), (-1,-1), 0.6, BRAND)])))
    story.append(Spacer(1, 6*mm))

    # From / To
    from_lines = []
    if b_name:
        from_lines.append(f"<b>{b_name}</b>")
    addr_line = ", ".join(x for x in [b_addr, b_city, b_country] if x)
    if addr_line:
        from_lines.append(f"<font color=\"#475569\">{addr_line}</font>")
    if b_tax:
        from_lines.append(f"<font size=8 color=\"#64748B\">Tax ID / GST: {b_tax}</font>")
    from_lines.append(f"{user_email}")
    from_lines.append('<font size=8 color="#94A3B8">via InvoiceSync</font>')
    from_block = "<b>From</b><br/>" + "<br/>".join(from_lines)

    custom = ""
    try:
        import json
        cf = client["custom_fields_json"]
        if cf:
            data = json.loads(cf) if isinstance(cf, str) else cf
            if isinstance(data, dict):
                for k,v in data.items():
                    custom += f"<br/><b>{k}:</b> {v}"
            elif isinstance(data, str) and data.strip():
                custom += f"<br/>{data}"
    except Exception as e:
        print("[PDF-CF-ERR]", e)
        custom = ""

    curr = ((invoice["currency"] if "currency" in invoice.keys() and invoice["currency"] else client["currency"]) or "USD").strip().upper()
    client_locale = (client["locale"] if "locale" in client.keys() and client["locale"] else None) or ("ja-JP" if curr == "JPY" else ("en-IN" if curr == "INR" else "en-US"))
    
    home_curr = (u_dict.get("base_currency") or "USD").strip().upper()
    user_locale = u_dict.get("locale") or "en-US"
    approx_line = ""
    if curr != home_curr:
        rate_val = RATES_TO_USD.get(curr, 1.0) / RATES_TO_USD.get(home_curr, 1.0)
        approx_amt = float(invoice["amount"] or 0) * rate_val
        today_s = datetime.now().strftime("%Y-%m-%d")
        approx_line = f"<br/><font size=7 color=\"#64748B\">≈ {fmt_money(approx_amt, home_curr, user_locale)} (1 {curr} ≈ {rate_val:g} {home_curr} as of {today_s})</font>"

    to_block = f'<b>Bill to</b><br/><b>{client["name"]}</b><br/>{client["email"] or ""}<br/>Currency: {curr}{custom}'
    due_str = ""
    try:
        _due = invoice["due_date"] if "due_date" in invoice.keys() else None
        if _due:
            due_str = str(_due)[:10]
    except Exception:
        due_str = ""

    terms_str = ""
    try:
        _terms = invoice["terms"] if "terms" in invoice.keys() else None
        if _terms:
            terms_str = f"<b>Terms:</b> {_terms}<br/><br/>"
    except Exception:
        terms_str = ""

    info_block = (
        f'<b>Period</b><br/>{invoice["period_start"]} to {invoice["period_end"]}<br/><br/>'
        f'{terms_str}'
        f'<b>Issued</b><br/>{invoice["created_at"][:10]}<br/><br/>'
        f'<b>Due</b><br/>{due_str or "on receipt"}<br/><br/>'
        f'<b>Amount</b><br/><font size=13 color="#2563EB"><b>{fmt_money(invoice["amount"], curr, client_locale)}</b></font>{approx_line}'
    )

    t2 = Table([[Paragraph(from_block, s_norm), Paragraph(to_block, s_norm), Paragraph(info_block, s_small)]], colWidths=[55*mm, 60*mm, 55*mm])
    t2.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4)]))
    story.append(t2)
    story.append(Spacer(1, 6*mm))

    # Line items or time entries
    notes_val = ""
    try:
        notes_val = (invoice["notes"] if "notes" in invoice.keys() else "") or ""
    except Exception:
        notes_val = ""

    line_items_data = None
    try:
        if "line_items_json" in invoice.keys() and invoice["line_items_json"]:
            line_items_data = json.loads(invoice["line_items_json"])
    except Exception as e:
        print("[PDF-LINEITEMS-ERR]", e)
        line_items_data = None

    if line_items_data:
        story.append(Paragraph("Invoice items", s_h))
        data = [[Paragraph("<b>Description</b>", s_small), Paragraph("<b>Qty / Hrs</b>", s_small), Paragraph("<b>Rate</b>", s_small), Paragraph("<b>Tax</b>", s_small), Paragraph("<b>Line total</b>", s_small)]]
        subtotal = 0.0
        total_tax = 0.0
        for itm in line_items_data:
            d_desc = str(itm.get("desc") or "-")
            d_qty = float(itm.get("qty") or 1.0)
            d_rate = float(itm.get("rate") or 0.0)
            d_tax_pct = float(itm.get("tax") or 0.0)
            item_line_total = d_qty * d_rate
            item_tax_amt = item_line_total * d_tax_pct / 100.0
            subtotal += item_line_total
            total_tax += item_tax_amt
            data.append([
                Paragraph(d_desc, s_small),
                Paragraph(f"{d_qty:g}", s_small),
                Paragraph(fmt_money(d_rate, curr, client_locale), s_small),
                Paragraph(f"{d_tax_pct:g}%" if d_tax_pct else "-", s_small),
                Paragraph(fmt_money(item_line_total + item_tax_amt, curr, client_locale), s_small),
            ])

        if notes_val.strip():
            data.append([
                Paragraph(f"<b>Customer Notes:</b> {notes_val.strip()}", s_small), "", "", "", ""
            ])

        data.append([
            Paragraph("", s_small), Paragraph("Subtotal", s_small), Paragraph("", s_small), Paragraph("", s_small), Paragraph(fmt_money(subtotal, curr, client_locale), s_small),
        ])
        if total_tax > 0:
            data.append([
                Paragraph("", s_small), Paragraph("Tax", s_small), Paragraph("", s_small), Paragraph("", s_small), Paragraph(fmt_money(total_tax, curr, client_locale), s_small),
            ])
        data.append([
            Paragraph("", s_small), Paragraph("<b>Total</b>", s_small), Paragraph("", s_small), Paragraph("", s_small), Paragraph(f"<b>{fmt_money(invoice['amount'], curr, client_locale)}</b>{approx_line}", s_small)
        ])
        tbl = Table(data, colWidths=[70*mm, 24*mm, 28*mm, 20*mm, 28*mm], repeatRows=1)
        t_styles = [
            ("BACKGROUND", (0,0), (-1,0), BRAND),
            ("TEXTCOLOR", (0,0), (-1,0), white),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,0), 8),
            ("TOPPADDING", (0,0), (-1,0), 8),
            ("BACKGROUND", (0,1), (-1,-2), white),
            ("BACKGROUND", (0,-1), (-1,-1), BG_LIGHT),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#E2E8F0")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ]
        if notes_val.strip():
            notes_row_idx = len(data) - (3 if total_tax > 0 else 2)
            t_styles.append(("SPAN", (0, notes_row_idx), (-1, notes_row_idx)))
            t_styles.append(("BACKGROUND", (0, notes_row_idx), (-1, notes_row_idx), HexColor("#F8FAFC")))
        tbl.setStyle(TableStyle(t_styles))
        story.append(tbl)
    elif time_entries:
        story.append(Paragraph("Time entries", s_h))
        data = [[Paragraph("<b>Date</b>", s_small), Paragraph("<b>Description</b>", s_small), Paragraph("<b>Hours</b>", s_small), Paragraph("<b>Rate</b>", s_small), Paragraph("<b>Line total</b>", s_small)]]
        rate = float(client["rate"] or 0)
        for te in time_entries:
            secs = int(te["seconds"])
            hrs = secs / 3600
            line_total = hrs * rate if rate else 0
            data.append([
                Paragraph(te["date"], s_small),
                Paragraph(te["description"] or "-", s_small),
                Paragraph(f"{hrs:.2f}", s_small),
                Paragraph(f"{fmt_money(rate, curr, client_locale)}/h" if rate else "-", s_small),
                Paragraph(fmt_money(line_total, curr, client_locale), s_small),
            ])
        taxp = 0
        try:
            taxp = float((client["tax_percent"] if "tax_percent" in client.keys() else 0) or 0)
        except Exception:
            taxp = 0
        total_hrs = sum(int(te["seconds"]) for te in time_entries) / 3600
        subtotal = sum(int(te["seconds"]) / 3600 * rate for te in time_entries)
        taxamt = subtotal * taxp / 100

        if notes_val.strip():
            data.append([
                Paragraph(f"<b>Customer Notes:</b> {notes_val.strip()}", s_small), "", "", "", ""
            ])

        data.append([
            Paragraph("", s_small), Paragraph("Subtotal", s_small), Paragraph(f"{total_hrs:.2f}h", s_small), Paragraph("", s_small), Paragraph(fmt_money(subtotal, curr, client_locale), s_small),
        ])
        if taxp:
            data.append([
                Paragraph("", s_small), Paragraph(f"Tax ({taxp:g}%)", s_small), Paragraph("", s_small), Paragraph("", s_small), Paragraph(fmt_money(taxamt, curr, client_locale), s_small),
            ])
        data.append([
            Paragraph("", s_small), Paragraph("<b>Total</b>", s_small), Paragraph(f"<b>{total_hrs:.2f}h</b>", s_small), Paragraph("", s_small), Paragraph(f"<b>{fmt_money(invoice['amount'], curr, client_locale)}</b>{approx_line}", s_small)
        ])
        tbl = Table(data, colWidths=[28*mm, 72*mm, 20*mm, 28*mm, 22*mm], repeatRows=1)
        t_styles = [
            ("BACKGROUND", (0,0), (-1,0), BRAND),
            ("TEXTCOLOR", (0,0), (-1,0), white),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,0), 8),
            ("TOPPADDING", (0,0), (-1,0), 8),
            ("BACKGROUND", (0,1), (-1,-2), white),
            ("BACKGROUND", (0,-1), (-1,-1), BG_LIGHT),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#E2E8F0")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ]
        if notes_val.strip():
            notes_row_idx = len(data) - (3 if not taxp else 4)
            t_styles.append(("SPAN", (0, notes_row_idx), (-1, notes_row_idx)))
            t_styles.append(("BACKGROUND", (0, notes_row_idx), (-1, notes_row_idx), HexColor("#F8FAFC")))

        tbl.setStyle(TableStyle(t_styles))
        story.append(tbl)
    else:
        # Fixed amount case
        story.append(Paragraph(f"Fixed total: <b>{fmt_money(invoice['amount'], curr, client_locale)}</b>{approx_line}", s_small))
        if notes_val.strip():
            story.append(Spacer(1, 4*mm))
            story.append(Paragraph(f"<b>Customer Notes / Terms:</b><br/>{notes_val.strip().replace(chr(10), '<br/>')}", s_small))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(f"Thank you for your business. {'Payment due by ' + due_str + '.' if due_str else 'Payment due on receipt.'} Questions? Reply to this invoice email.", s_small))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph('<font size=7 color="#94A3B8">Generated by InvoiceSync — lightweight invoicing for freelancers. InvoiceSync does not store card data.</font>', s_small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BRAND)
        canvas.setLineWidth(0.6)
        canvas.line(18*mm, 12*mm, 210*mm - 18*mm, 12*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(105*mm, 8*mm, f"Invoice {invoice['number']} • InvoiceSync • {datetime.now().strftime('%Y-%m-%d')}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"[PDF] wrote {pdf_path} amount={invoice['amount']}")
    return pdf_path
