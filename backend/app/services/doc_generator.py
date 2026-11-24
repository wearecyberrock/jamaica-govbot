"""Document Blueprint Inspector, PDF/DOCX Auto-Fill Engine, and Visual Step Roadmap Generator."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import GENERATED_DIR, LOGO_PATH, decrypt_value
from app.models import BrandingConfig, ClientCase, InterviewPrediction, RiskFlag

GREEN_HEX = "#1a472a"
GOLD_HEX = "#d4a234"
NAVY_HEX = "#0b3c68"
RED_HEX = "#ce1126"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_blueprint_file(path: Path) -> dict[str, Any]:
    """Inspect a PDF or DOCX file for AcroForm fields, {{placeholders}}, pages, and preview text."""
    ext = path.suffix.lower()
    fields: list[str] = []
    pages = 0
    preview_text = ""

    if ext == ".pdf":
        try:
            reader = PdfReader(str(path))
            pages = len(reader.pages)
            acro = reader.get_fields() or {}
            fields = list(acro.keys())[:80]
            chunks = []
            for p in reader.pages[:3]:
                txt = (p.extract_text() or "").strip()
                if txt:
                    chunks.append(txt)
            preview_text = "\n\n".join(chunks)[:2400]
            if not fields and preview_text:
                # Extract recognizable form labels for non-AcroForm scanned/flat gov PDFs
                found = re.findall(r"(?:SECTION\s+[A-Z][^\n]{2,50}|[A-Z][A-Z /()-]{4,35}:)", preview_text)
                fields = list(dict.fromkeys([f.strip().rstrip(":") for f in found]))[:25]
        except Exception as exc:
            preview_text = f"PDF inspection notice: {exc}"
    elif ext == ".docx":
        try:
            doc = DocxDocument(str(path))
            full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            preview_text = full_text[:2400]
            fields = sorted(set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", full_text)))
            pages = max(1, len(doc.paragraphs) // 25)
        except Exception as exc:
            preview_text = f"DOCX inspection notice: {exc}"

    return {
        "file_format": ext,
        "pages": pages,
        "detected_fields": fields,
        "preview_text": preview_text,
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256_file(path) if path.exists() else "",
    }


def client_field_map(client: ClientCase) -> dict[str, str]:
    passport_plain = decrypt_value(client.passport_number_enc)
    dob_plain = decrypt_value(client.dob_enc)
    return {
        "case_id": client.case_id,
        "full_name": client.full_name or client.pseudonym,
        "pseudonym": client.pseudonym,
        "email": client.email or "Not provided",
        "phone": client.phone or "Not provided",
        "nationality": client.nationality or "Jamaica",
        "parish": client.parish or "Jamaica",
        "visa_class": client.visa_class or "B1/B2",
        "passport_number": passport_plain or "Pending verification",
        "passport_expiry": client.passport_expiry or "Pending verification",
        "dob": dob_plain or "Pending verification",
        "ds160_confirmation_id": client.ds160_confirmation_id or "Not submitted yet",
        "ais_appointment_barcode": client.ais_appointment_barcode or "Not booked yet",
        "intended_travel_date": client.intended_travel_date or "TBD",
        "intended_return_date": client.intended_return_date or "TBD",
        "purpose_of_trip": client.purpose_of_trip or "Temporary visit (B1/B2)",
        "us_destination": client.us_destination or "United States",
        "us_host_contact": client.us_host_contact or "Hotel / Not specified",
        "occupation": client.occupation or "Not specified",
        "employer_name": client.employer_name or "Not specified",
        "monthly_gross_jmd": f"JMD {client.monthly_gross_jmd:,.0f}" if client.monthly_gross_jmd else "Not verified",
        "monthly_net_jmd": f"JMD {client.monthly_net_jmd:,.0f}" if client.monthly_net_jmd else "Not verified",
        "marital_status": client.marital_status or "Not specified",
        "children_count": str(client.children_count),
        "prior_us_refusals": str(client.prior_us_refusals),
        "us_relatives_details": client.us_relatives_details or ("Yes — details pending" if client.has_us_relatives else "None reported"),
        "embassy_interview_date": client.embassy_interview_date or "Not scheduled yet",
        "standing_score": f"{client.standing_score}%",
        "generated_date": datetime.now(timezone.utc).strftime("%d %B %Y"),
    }


def generate_ds160_worksheet_pdf(
    client: ClientCase,
    flags: list[RiskFlag],
    branding: BrandingConfig | None = None,
) -> tuple[Path, dict[str, str]]:
    """Generate a branded DS-160 Preparation & Truthful Verification Worksheet PDF."""
    fields = client_field_map(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = GENERATED_DIR / f"{client.case_id}_DS160_Worksheet_{ts}.pdf"

    agency = branding.agency_name if branding else "Jahtaria Travel Services"
    doc = SimpleDocTemplate(str(out_path), pagesize=letter, topMargin=0.55 * inch, bottomMargin=0.55 * inch, leftMargin=0.6 * inch, rightMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("JTitle", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor(GREEN_HEX), spaceAfter=4)
    sub_style = ParagraphStyle("JSub", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#475569"), spaceAfter=10)
    h2_style = ParagraphStyle("JH2", parent=styles["Heading2"], fontSize=11.5, textColor=colors.HexColor(NAVY_HEX), spaceBefore=10, spaceAfter=5)
    body_style = ParagraphStyle("JBody", parent=styles["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#0f172a"))

    story = [
        Paragraph(f"{agency} — DS-160 Preparation & Verification Blueprint", title_style),
        Paragraph(
            f"Case ID: <b>{fields['case_id']}</b> | Visa Class: <b>{fields['visa_class']}</b> | "
            f"Good Standing Score: <b>{fields['standing_score']}</b> | Prepared: {fields['generated_date']}",
            sub_style,
        ),
    ]

    # Tricolor Jamaican banner line
    banner = Table([["", "", ""]], colWidths=[2.43 * inch, 2.43 * inch, 2.44 * inch], rowHeights=[5])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(GREEN_HEX)),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(GOLD_HEX)),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor(NAVY_HEX)),
    ]))
    story.append(banner)
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. Applicant Biographic & Passport Verification", h2_style))
    bio_rows = [
        ["Full Legal Name", fields["full_name"], "Nationality / Parish", f"{fields['nationality']} ({fields['parish']})"],
        ["Passport Number", fields["passport_number"], "Passport Expiry", fields["passport_expiry"]],
        ["Date of Birth", fields["dob"], "Marital Status (Legal)", fields["marital_status"]],
        ["DS-160 Barcode (AA...)", fields["ds160_confirmation_id"], "AIS Booking Barcode", fields["ais_appointment_barcode"]],
        ["Email", fields["email"], "Phone / WhatsApp", fields["phone"]],
    ]
    bio_tbl = Table(bio_rows, colWidths=[1.5 * inch, 2.15 * inch, 1.55 * inch, 2.1 * inch])
    bio_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef7f2")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef7f2")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(bio_tbl)

    story.append(Paragraph("2. Travel Plan, Employment & Financial Verification (Gross vs. Net JMD)", h2_style))
    fin_rows = [
        ["Purpose of Trip", fields["purpose_of_trip"], "U.S. Destination", fields["us_destination"]],
        ["Intended Arrival", fields["intended_travel_date"], "Intended Return", fields["intended_return_date"]],
        ["U.S. Host / Hotel", fields["us_host_contact"], "Embassy Interview", fields["embassy_interview_date"]],
        ["Occupation", fields["occupation"], "Employer / Business", fields["employer_name"]],
        ["Monthly GROSS (DS-160)", fields["monthly_gross_jmd"], "Monthly NET Take-Home", fields["monthly_net_jmd"]],
        ["Children Count", fields["children_count"], "Prior U.S. Refusals", fields["prior_us_refusals"]],
        ["U.S. Relatives Disclosed", fields["us_relatives_details"], "Good Standing", fields["standing_score"]],
    ]
    fin_tbl = Table(fin_rows, colWidths=[1.5 * inch, 2.15 * inch, 1.55 * inch, 2.1 * inch])
    fin_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f8fafc")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(fin_tbl)

    story.append(Paragraph("3. Compliance & Risk Audit Findings (Staff Review Required Before Finalization)", h2_style))
    flag_rows = [["Status", "Check Item", "Action / Verification Note"]]
    for fl in flags[:10]:
        badge = fl.severity.upper()
        flag_rows.append([badge, Paragraph(fl.title, body_style), Paragraph(fl.suggested_fix or fl.detail, body_style)])
    flag_tbl = Table(flag_rows, colWidths=[0.8 * inch, 2.5 * inch, 4.0 * inch])
    flag_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN_HEX)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(flag_tbl)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<b>Compliance Notice:</b> This worksheet assists truthful DS-160 preparation and verification against official U.S. Embassy Kingston requirements "
        "(142 Old Hope Road, Kingston). All statements submitted on Form DS-160 and during consular interviews must be 100% accurate and truthful. "
        "No visa approval is ever guaranteed.",
        ParagraphStyle("Disc", parent=body_style, fontSize=7.8, textColor=colors.HexColor("#475569")),
    ))

    doc.build(story)
    return out_path, fields


def generate_kingston_checklist_pdf(
    client: ClientCase,
    predictions: list[InterviewPrediction],
    branding: BrandingConfig | None = None,
) -> tuple[Path, dict[str, str]]:
    """Generate a U.S. Embassy Kingston Pre-Interview Document Checklist & Practice Sheet PDF."""
    fields = client_field_map(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = GENERATED_DIR / f"{client.case_id}_Kingston_Checklist_{ts}.pdf"
    agency = branding.agency_name if branding else "Jahtaria Travel Services"

    doc = SimpleDocTemplate(str(out_path), pagesize=letter, topMargin=0.55 * inch, bottomMargin=0.55 * inch, leftMargin=0.6 * inch, rightMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CTitle", parent=styles["Heading1"], fontSize=15.5, textColor=colors.HexColor(GREEN_HEX), spaceAfter=4)
    h2_style = ParagraphStyle("CH2", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor(NAVY_HEX), spaceBefore=10, spaceAfter=5)
    body_style = ParagraphStyle("CBody", parent=styles["Normal"], fontSize=9, leading=13)

    mrv_fee = "$205 USD" if client.visa_class.upper().startswith(("H", "L", "O", "P")) else "$185 USD"

    story = [
        Paragraph(f"{agency} — U.S. Embassy Kingston Pre-Interview Checklist", title_style),
        Paragraph(
            f"Applicant: <b>{fields['full_name']}</b> ({fields['case_id']}) | Visa: <b>{fields['visa_class']}</b> | "
            f"MRV Fee: <b>{mrv_fee}</b> | Location: <b>142 Old Hope Road, Kingston</b>",
            body_style,
        ),
        Spacer(1, 8),
        Paragraph("Mandatory Embassy Check-In Documents", h2_style),
    ]

    checklist_items = [
        "[ ] Valid Jamaican Passport (valid 6+ months past intended stay) + all expired passports with prior U.S. visas.",
        f"[ ] Printed Form DS-160 Confirmation Page — barcode ({fields['ds160_confirmation_id']}) MUST match AIS booking ({fields['ais_appointment_barcode']}) per April 1, 2025 rule.",
        "[ ] Printed AIS Appointment Confirmation Letter & MRV Fee Payment Receipt (ais.usvisa-info.com/en-jm/niv).",
        "[ ] One 2x2 inch (5x5 cm) white-background color visa photo taken within last 6 months (no eyeglasses).",
        "[ ] Original Employment Letter & last 3 months pay slips (verifying exact monthly GROSS vs NET JMD salary).",
        "[ ] Last 3–6 months stamped bank statements & business registration / TRN / TCC if self-employed.",
        "[ ] Jamaican RGD Birth / Marriage / Children's Certificates — photocopy reduced to 92% scale so top & bottom serial numbers are visible.",
        "[ ] Security Notice: Cellphones, smartwatches, and large bags are PROHIBITED at 142 Old Hope Road (no storage available).",
    ]
    for item in checklist_items:
        story.append(Paragraph(item, body_style))
        story.append(Spacer(1, 3))

    story.append(Paragraph("Tailored Mock Interview Preparation Questions", h2_style))
    q_rows = [["#", "Type", "Likely Consular Question Theme", "Sample Question"]]
    for idx, p in enumerate(predictions[:10], start=1):
        label = "Policy (Universal)" if p.question_type == "policy_mandatory" else f"Profile #{p.rank}"
        q_rows.append([str(idx), label, p.theme_id.replace("_", " ").title(), Paragraph(p.question_text, body_style)])
    if len(q_rows) == 1:
        q_rows.append(["1", "Standard", "Purpose Of Trip", "What is the purpose of your visit to the United States?"])

    q_tbl = Table(q_rows, colWidths=[0.4 * inch, 1.2 * inch, 1.7 * inch, 4.0 * inch])
    q_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY_HEX)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(q_tbl)

    doc.build(story)
    return out_path, fields


def generate_support_letter_docx(
    client: ClientCase,
    flags: list[RiskFlag],
    branding: BrandingConfig | None = None,
) -> tuple[Path, dict[str, str]]:
    """Generate an editable DOCX Support & Verification Packet for Word / Google Docs."""
    fields = client_field_map(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = GENERATED_DIR / f"{client.case_id}_Support_Packet_{ts}.docx"
    agency = branding.agency_name if branding else "Jahtaria Travel Services"

    doc = DocxDocument()
    heading = doc.add_heading(f"{agency} — Visa Case Support & Verification Packet", level=1)
    for run in heading.runs:
        run.font.color.rgb = RGBColor(0x1A, 0x47, 0x2A)

    meta = doc.add_paragraph()
    meta.add_run(f"Case ID: {fields['case_id']}  |  Visa Class: {fields['visa_class']}  |  Standing Score: {fields['standing_score']}  |  Date: {fields['generated_date']}").bold = True

    doc.add_heading("1. Applicant Summary & Truthful Consistency Sheet", level=2)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = "Table Grid"
    hdr = tbl.rows[0].cells
    hdr[0].text = "Field"
    hdr[1].text = "Verified Value"
    for key in (
        "full_name", "nationality", "parish", "passport_number", "passport_expiry",
        "ds160_confirmation_id", "ais_appointment_barcode", "purpose_of_trip",
        "us_destination", "intended_travel_date", "intended_return_date",
        "occupation", "employer_name", "monthly_gross_jmd", "monthly_net_jmd",
        "marital_status", "children_count", "prior_us_refusals", "us_relatives_details",
    ):
        row = tbl.add_row().cells
        row[0].text = key.replace("_", " ").title()
        row[1].text = fields[key]

    doc.add_heading("2. Draft Employer / Purpose Verification Cover Note (Editable)", level=2)
    p = doc.add_paragraph(
        f"To the Consular Officer,\n"
        f"Embassy of the United States of America, 142 Old Hope Road, Kingston, Jamaica.\n\n"
        f"Re: Temporary {fields['visa_class']} Visa Application — {fields['full_name']} (Passport: {fields['passport_number']})\n\n"
        f"This note summarizes the verified travel itinerary and Jamaican ties of {fields['full_name']}, "
        f"employed as {fields['occupation']} with {fields['employer_name']} (Monthly Gross: {fields['monthly_gross_jmd']}). "
        f"The applicant intends to travel to {fields['us_destination']} from {fields['intended_travel_date']} to {fields['intended_return_date']} "
        f"for the purpose of: {fields['purpose_of_trip']}. Following the temporary visit, the applicant will resume regular duties and family responsibilities in Jamaica."
    )
    p.paragraph_format.space_after = Pt(8)

    doc.add_heading("3. Open Verification & Action Items", level=2)
    for fl in flags:
        if fl.severity in ("red", "amber"):
            bp = doc.add_paragraph(style="List Bullet")
            bp.add_run(f"[{fl.severity.upper()}] {fl.title}: ").bold = True
            bp.add_run(fl.suggested_fix or fl.detail)

    doc.add_paragraph(
        "\nCompliance Reminder: Verify all figures directly against original payslips, RGD certificates (92% copy scale), "
        "and CEAC DS-160 before client signature. Truthful answers only."
    )
    doc.save(str(out_path))
    return out_path, fields


def generate_visual_roadmap_png(
    client: ClientCase,
    flags: list[RiskFlag],
    branding: BrandingConfig | None = None,
) -> tuple[Path, dict[str, str]]:
    """Generate a high-resolution Jamaican-themed Client Step-by-Step Visual Roadmap PNG."""
    fields = client_field_map(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = GENERATED_DIR / f"{client.case_id}_Visual_Roadmap_{ts}.png"
    agency = branding.agency_name if branding else "Jahtaria Travel Services"

    w, h = 1400, 900
    img = Image.new("RGB", (w, h), "#f4f8f5")
    draw = ImageDraw.Draw(img)

    def load_font(size: int, bold: bool = False):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for c in candidates:
            if Path(c).exists():
                return ImageFont.truetype(c, size)
        return ImageFont.load_default()

    f_title = load_font(36, bold=True)
    f_h2 = load_font(22, bold=True)
    f_body = load_font(17, bold=False)
    f_bold = load_font(17, bold=True)
    f_small = load_font(14, bold=False)

    # Top Header Banner (Deep Jamaican Green)
    draw.rectangle([0, 0, w, 150], fill="#1a472a")
    # Tricolor Accent Bar
    draw.rectangle([0, 150, 470, 162], fill="#1a472a")
    draw.rectangle([470, 150, 940, 162], fill="#ffd700")
    draw.rectangle([940, 150, w, 162], fill="#0b3c68")

    # Paste Jahtaria Logo if available
    if LOGO_PATH.exists():
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA").resize((112, 112))
            img.paste(logo, (36, 19), logo)
        except Exception:
            pass

    draw.text((170, 32), agency.upper(), fill="#ffd700", font=f_h2)
    draw.text((170, 64), "U.S. Visa Client Action Roadmap (Kingston Embassy)", fill="#ffffff", font=f_title)
    draw.text((170, 112), f"Applicant: {fields['full_name']}   |   Case: {fields['case_id']}   |   Visa: {fields['visa_class']}   |   Date: {fields['generated_date']}", fill="#d1fae5", font=f_body)

    # Good Standing Score Card
    draw.rounded_rectangle([40, 190, 1360, 295], radius=18, fill="#ffffff", outline="#cbd5e1", width=2)
    score = client.standing_score
    bar_color = "#16a34a" if score >= 80 else ("#d97706" if score >= 60 else "#ce1126")
    draw.text((70, 208), f"CASE GOOD STANDING READINESS: {score}%", fill="#0f172a", font=f_h2)
    draw.text((70, 240), f"DS-160 Barcode: {fields['ds160_confirmation_id']}   •   Passport Expiry: {fields['passport_expiry']}   •   Interview: {fields['embassy_interview_date']}", fill="#475569", font=f_body)

    # Progress bar track & fill
    draw.rounded_rectangle([920, 218, 1320, 256], radius=14, fill="#e2e8f0")
    fill_w = max(24, int(400 * (score / 100.0)))
    draw.rounded_rectangle([920, 218, 920 + fill_w, 256], radius=14, fill=bar_color)
    draw.text((1095, 227), f"{score}%", fill="#ffffff", font=f_bold)

    # 5 Step Cards
    steps = [
        ("STEP 1", "Passport & PICA", f"Verify 6+ mo validity\nExpiry: {fields['passport_expiry']}"),
        ("STEP 2", "DS-160 Accuracy", f"Verify gross JMD &\nAA barcode match"),
        ("STEP 3", "AIS & MRV Fee", "Pay MRV fee & sync\nbarcode on AIS portal"),
        ("STEP 4", "Mock Interview", "Practice truthful,\nconcise 2-min answers"),
        ("STEP 5", "Embassy Day", "142 Old Hope Rd, Kgn\nNo phones; 92% RGD"),
    ]
    card_w = 246
    gap = 22
    start_x = 40
    for i, (num, title, desc) in enumerate(steps):
        x0 = start_x + i * (card_w + gap)
        x1 = x0 + card_w
        draw.rounded_rectangle([x0, 325, x1, 515], radius=16, fill="#ffffff", outline="#1a472a", width=2)
        draw.rounded_rectangle([x0, 325, x1, 368], radius=14, fill="#1a472a")
        draw.text((x0 + 18, 336), f"{num}  •  {title}", fill="#ffd700", font=f_bold)
        draw.multiline_text((x0 + 18, 392), desc, fill="#1e293b", font=f_body, spacing=8)

    # Priority Action Alerts Box
    draw.rounded_rectangle([40, 545, 1360, 810], radius=18, fill="#ffffff", outline="#cbd5e1", width=2)
    draw.text((70, 565), "PRIORITY VERIFICATION & ACTION ITEMS FOR THIS CLIENT", fill="#0b3c68", font=f_h2)
    y = 608
    action_flags = [f for f in flags if f.severity in ("red", "amber")][:4]
    if not action_flags:
        draw.text((70, y), "ALL DETERMINISTIC READINESS CHECKS PASSED — Ready for final staff review and mock interview!", fill="#15803d", font=f_bold)
    else:
        for fl in action_flags:
            pill_bg = "#ce1126" if fl.severity == "red" else "#d97706"
            draw.rounded_rectangle([70, y, 155, y + 28], radius=8, fill=pill_bg)
            draw.text((84, y + 5), fl.severity.upper(), fill="#ffffff", font=f_small)
            line = f"{fl.title}: {(fl.suggested_fix or fl.detail)[:95]}"
            draw.text((170, y + 4), line, fill="#0f172a", font=f_body)
            y += 46

    # Footer Compliance Disclaimer
    draw.text(
        (40, 840),
        "Truthful Visa Preparation Only — This roadmap supports accurate DS-160 verification & interview readiness. Visa issuance is solely decided by U.S. Consular Officers.",
        fill="#475569",
        font=f_small,
    )

    img.save(str(out_path))
    return out_path, fields


def fill_custom_blueprint(blueprint_path: Path, client: ClientCase) -> tuple[Path, dict[str, str]]:
    """Auto-fill a user-uploaded .docx ({{placeholder}}) or AcroForm .pdf blueprint."""
    fields = client_field_map(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = blueprint_path.suffix.lower()
    out_path = GENERATED_DIR / f"{client.case_id}_{blueprint_path.stem}_filled_{ts}{ext}"

    if ext == ".docx":
        doc = DocxDocument(str(blueprint_path))
        for p in doc.paragraphs:
            for k, v in fields.items():
                token = f"{{{{{k}}}}}"
                if token in p.text:
                    p.text = p.text.replace(token, v)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for k, v in fields.items():
                        token = f"{{{{{k}}}}}"
                        if token in cell.text:
                            cell.text = cell.text.replace(token, v)
        doc.save(str(out_path))
        return out_path, fields

    if ext == ".pdf":
        reader = PdfReader(str(blueprint_path))
        writer = PdfWriter()
        writer.append(reader)
        acro = reader.get_fields() or {}
        if acro:
            mapped: dict[str, str] = {}
            for pdf_key in acro.keys():
                lk = pdf_key.lower()
                if "surname" in lk or "last" in lk:
                    mapped[pdf_key] = fields["full_name"].split()[-1]
                elif "given" in lk or "first" in lk or "name" in lk:
                    mapped[pdf_key] = fields["full_name"]
                elif "passport" in lk:
                    mapped[pdf_key] = fields["passport_number"]
                elif "birth" in lk or "dob" in lk:
                    mapped[pdf_key] = fields["dob"]
                elif "email" in lk:
                    mapped[pdf_key] = fields["email"]
                elif "phone" in lk or "tel" in lk:
                    mapped[pdf_key] = fields["phone"]
                elif "nationality" in lk or "country" in lk:
                    mapped[pdf_key] = fields["nationality"]
                elif "occupation" in lk or "employer" in lk:
                    mapped[pdf_key] = fields["occupation"]
            for page in writer.pages:
                try:
                    writer.update_page_form_field_values(page, mapped)
                except Exception:
                    pass
        with out_path.open("wb") as f:
            writer.write(f)
        return out_path, fields

    raise ValueError(f"Unsupported blueprint format: {ext}")
