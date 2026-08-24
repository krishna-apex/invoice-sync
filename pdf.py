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

def generate_invoice_pdf(invoice, client, time_entries, user_email, out_dir="pdfs"):
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

    # Header: brand + invoice number
    header_data = [
        [Paragraph('<b>InvoiceSync</b><br/><font size=8 color="#64748B">Freelance invoicing, synced.</font>', s_small),
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
    from_block = f'<b>From</b><br/>{user_email}<br/><font color="#64748B">via InvoiceSync</font>'
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

    to_block = f'<b>Bill to</b><br/><b>{client["name"]}</b><br/>{client["email"] or ""}<br/>Currency: {client["currency"]}{custom}'
    info_block = f'<b>Period</b><br/>{invoice["period_start"]} to {invoice["period_end"]}<br/><br/><b>Issued</b><br/>{invoice["created_at"][:10]}<br/><br/><b>Amount</b><br/><font size=13 color="#2563EB"><b>{client["currency"]} {float(invoice["amount"]):.2f}</b></font>'
    t2 = Table([[Paragraph(from_block, s_norm), Paragraph(to_block, s_norm), Paragraph(info_block, s_small)]], colWidths=[55*mm, 60*mm, 55*mm])
    t2.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4)]))
    story.append(t2)
    story.append(Spacer(1, 6*mm))

    # Line items
    story.append(Paragraph("Time entries", s_h))
    if time_entries:
        data = [[Paragraph("<b>Date</b>", s_small), Paragraph("<b>Description</b>", s_small), Paragraph("<b>Hours</b>", s_small), Paragraph("<b>Rate</b>", s_small), Paragraph("<b>Line total</b>", s_small)]]
        rate = float(client["rate"] or 0)
        currency = client["currency"] or "USD"
        for te in time_entries:
            secs = int(te["seconds"])
            hrs = secs / 3600
            line_total = hrs * rate if rate else 0
            # if rate==0, show 0 or if fixed items we fallback to amount distribution — just show 0
            data.append([
                Paragraph(te["date"], s_small),
                Paragraph(te["description"] or "-", s_small),
                Paragraph(f"{hrs:.2f}", s_small),
                Paragraph(f"{currency} {rate:.2f}/h" if rate else "-", s_small),
                Paragraph(f"{currency} {line_total:.2f}", s_small),
            ])
        # totals row
        total_hrs = sum(int(te["seconds"]) for te in time_entries) / 3600
        data.append([
            Paragraph("", s_small), Paragraph("<b>Total</b>", s_small), Paragraph(f"<b>{total_hrs:.2f}h</b>", s_small), Paragraph("", s_small), Paragraph(f"<b>{currency} {float(invoice['amount']):.2f}</b>", s_small)
        ])
        tbl = Table(data, colWidths=[28*mm, 72*mm, 20*mm, 28*mm, 22*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
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
        ]))
        story.append(tbl)
    else:
        # Fixed amount case (no time entries, but invoice amount set)
        story.append(Paragraph(f"No time entries for period. Fixed total: <b>{client['currency']} {float(invoice['amount']):.2f}</b>", s_small))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Thank you for your business. Payment due within 14 days. Questions? Reply to this invoice email.", s_small))
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
