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

ZERO_DECIMAL_CURRENCIES = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf"
}

CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "CAD": "CA$",
    "AUD": "A$",
    "JPY": "¥",
    "CHF": "CHF",
    "SGD": "S$",
    "NZD": "NZ$",
    "AED": "AED",
}

def format_indian_grouping(num_str: str) -> str:
    """Format integer string using Indian numbering: 1,00,000"""
    if len(num_str) <= 3:
        return num_str
    last3 = num_str[-3:]
    remaining = num_str[:-3]
    parts = []
    while len(remaining) > 2:
        parts.append(remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        parts.append(remaining)
    parts.reverse()
    return ",".join(parts) + "," + last3

def fmt_money(amount, currency: str = "USD") -> str:
    """One helper fmt_money(amount, currency): symbol + code + locale grouping."""
    try:
        amt = float(amount or 0)
    except Exception:
        amt = 0.0
    curr = (currency or "USD").upper().strip()
    is_zero = curr.lower() in ZERO_DECIMAL_CURRENCIES
    symbol = CURRENCY_SYMBOLS.get(curr, curr + " ")
    sign = "-" if amt < 0 else ""
    abs_amt = abs(amt)

    if curr == "INR":
        if is_zero:
            int_part = str(int(round(abs_amt)))
            formatted = format_indian_grouping(int_part)
        else:
            cents = f"{abs_amt:.2f}".split(".")[1]
            int_part = str(int(abs_amt))
            formatted = f"{format_indian_grouping(int_part)}.{cents}"
        return f"{sign}{symbol}{formatted} {curr}"
    else:
        if is_zero:
            formatted = f"{abs_amt:,.0f}"
        else:
            formatted = f"{abs_amt:,.2f}"
        return f"{sign}{symbol}{formatted} {curr}"

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

    curr = client["currency"] or "USD"
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
        f'<b>Amount</b><br/><font size=13 color="#2563EB"><b>{fmt_money(invoice["amount"], curr)}</b></font>'
    )

    t2 = Table([[Paragraph(from_block, s_norm), Paragraph(to_block, s_norm), Paragraph(info_block, s_small)]], colWidths=[55*mm, 60*mm, 55*mm])
    t2.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4)]))
    story.append(t2)
    story.append(Spacer(1, 6*mm))

    # Line items
    story.append(Paragraph("Time entries", s_h))
    notes_val = ""
    try:
        notes_val = (invoice["notes"] if "notes" in invoice.keys() else "") or ""
    except Exception:
        notes_val = ""

    if time_entries:
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
                Paragraph(f"{fmt_money(rate, curr)}/h" if rate else "-", s_small),
                Paragraph(fmt_money(line_total, curr), s_small),
            ])
        # totals rows: subtotal / tax / total (single money-math with app)
        taxp = 0
        try:
            taxp = float((client["tax_percent"] if "tax_percent" in client.keys() else 0) or 0)
        except Exception:
            taxp = 0
        total_hrs = sum(int(te["seconds"]) for te in time_entries) / 3600
        subtotal = sum(int(te["seconds"]) / 3600 * rate for te in time_entries)
        taxamt = subtotal * taxp / 100

        # Customer notes above totals if present
        if notes_val.strip():
            data.append([
                Paragraph(f"<b>Notes:</b> {notes_val.strip()}", s_small), "", "", "", ""
            ])

        data.append([
            Paragraph("", s_small), Paragraph("Subtotal", s_small), Paragraph(f"{total_hrs:.2f}h", s_small), Paragraph("", s_small), Paragraph(fmt_money(subtotal, curr), s_small),
        ])
        if taxp:
            data.append([
                Paragraph("", s_small), Paragraph(f"Tax ({taxp:g}%)", s_small), Paragraph("", s_small), Paragraph("", s_small), Paragraph(fmt_money(taxamt, curr), s_small),
            ])
        data.append([
            Paragraph("", s_small), Paragraph("<b>Total</b>", s_small), Paragraph(f"<b>{total_hrs:.2f}h</b>", s_small), Paragraph("", s_small), Paragraph(f"<b>{fmt_money(invoice['amount'], curr)}</b>", s_small)
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
            # span the notes row across columns
            notes_row_idx = len(data) - (3 if not taxp else 4)
            t_styles.append(("SPAN", (0, notes_row_idx), (-1, notes_row_idx)))
            t_styles.append(("BACKGROUND", (0, notes_row_idx), (-1, notes_row_idx), HexColor("#F8FAFC")))

        tbl.setStyle(TableStyle(t_styles))
        story.append(tbl)
    else:
        # Fixed amount case (no time entries, but invoice amount set)
        story.append(Paragraph(f"No time entries for period. Fixed total: <b>{fmt_money(invoice['amount'], client['currency'])}</b>", s_small))
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
