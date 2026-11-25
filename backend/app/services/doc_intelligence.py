"""Document Intelligence Engine: Vision OCR, PDF Page Rendering, Annotation/Signature Burn-In, 92% RGD Scaler & Embassy Packet Bundler."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from docx import Document as DocxDocument
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from sqlalchemy.orm import Session

from app.config import CLIENT_VAULT_DIR, GENERATED_DIR, decrypt_value
from app.models import ClientCase, ClientDocument, GeneratedAsset
from app.services.connectors import get_setting
from app.services.doc_generator import client_field_map, fill_custom_blueprint, sha256_file
from app.services.hermes_engine import call_llm_detailed

VALID_CATEGORIES = ("passport_id", "financial_payslips", "rgd_civil", "embassy_forms", "photos_other")


def guess_document_category(filename: str, text: str = "") -> str:
    blob = f"{filename} {text[:800]}".lower()
    if any(k in blob for k in ("passport", "pica", "trn", "driver", "national id", "electoral")):
        return "passport_id"
    if any(k in blob for k in ("payslip", "pay slip", "salary", "bank", "statement", "ncb", "scotiabank", "jn bank", "sagicor", "employment", "job letter", "income", "tcc")):
        return "financial_payslips"
    if any(k in blob for k in ("rgd", "birth", "marriage", "birreq", "civil", "registrar general")):
        return "rgd_civil"
    if any(k in blob for k in ("ds-160", "ds160", "ds-5535", "ds5535", "ds-157", "ds-156", "ais", "embassy", "appointment", "visa", "checklist", "worksheet")):
        return "embassy_forms"
    return "photos_other"


def get_pdf_page_count(path: Path) -> int:
    if path.suffix.lower() != ".pdf" or not path.exists():
        return 1
    try:
        return max(1, len(PdfReader(str(path)).pages))
    except Exception:
        return 1


def render_pdf_page_png(path: Path, page_index: int = 0, scale: float = 2.0) -> bytes:
    """Render a PDF page to crisp PNG bytes using pypdfium2 (cached by sha256 + page)."""
    import pypdfium2 as pdfium

    cache_dir = CLIENT_VAULT_DIR / "_page_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(path)[:16]
    cache_file = cache_dir / f"{digest}_p{page_index}_s{int(scale*10)}.png"
    if cache_file.exists():
        return cache_file.read_bytes()

    pdf = pdfium.PdfDocument(str(path))
    try:
        idx = max(0, min(page_index, len(pdf) - 1))
        page = pdf[idx]
        bitmap = page.render(scale=scale)
        pil_img = bitmap.to_pil()
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        try:
            cache_file.write_bytes(png_bytes)
        except Exception:
            pass
        return png_bytes
    finally:
        pdf.close()


def extract_text_from_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            reader = PdfReader(str(path))
            return "\n\n".join((p.extract_text() or "").strip() for p in reader.pages[:10]).strip()
        except Exception:
            return ""
    if ext == ".docx":
        try:
            doc = DocxDocument(str(path))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for t in doc.tables:
                for r in t.rows:
                    row_txt = " | ".join(c.text.strip() for c in r.cells if c.text.strip())
                    if row_txt:
                        parts.append(row_txt)
            return "\n".join(parts).strip()
        except Exception:
            return ""
    if ext in (".txt", ".csv", ".json", ".md"):
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:15000]
        except Exception:
            return ""
    return ""


def _call_vision_model(db: Session, image_bytes: bytes, mime_type: str, prompt: str) -> str | None:
    """Call Gemini, OpenAI, or Anthropic multimodal vision if configured to extract fields from scanned images."""
    b64 = base64.b64encode(image_bytes).decode("ascii")

    # 1. Try Gemini Vision (preferred if gemini key configured)
    gem_key = get_setting(db, "gemini_api_key", os.getenv("GEMINI_API_KEY", "")).strip()
    if gem_key:
        for model in ("gemini-3.1-flash-lite", "gemini-flash-latest"):
            try:
                with httpx.Client(timeout=40.0) as client:
                    r = client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gem_key}",
                        json={
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [
                                        {"text": prompt},
                                        {"inline_data": {"mime_type": mime_type, "data": b64}},
                                    ],
                                }
                            ]
                        },
                    )
                    if r.status_code == 200:
                        cands = r.json().get("candidates", [])
                        if cands:
                            txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
                            if txt:
                                return txt
            except Exception:
                continue

    # 2. Try OpenAI Vision
    oai_key = get_setting(db, "openai_api_key", os.getenv("OPENAI_API_KEY", "")).strip()
    if oai_key:
        try:
            with httpx.Client(timeout=40.0) as client:
                r = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {oai_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                                ],
                            }
                        ],
                    },
                )
                if r.status_code == 200:
                    return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            pass

    # 3. Try Anthropic Vision
    anth_key = get_setting(db, "anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", "")).strip()
    if anth_key:
        try:
            with httpx.Client(timeout=40.0) as client:
                r = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": anth_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={
                        "model": "claude-3-5-sonnet-latest",
                        "max_tokens": 1200,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ],
                    },
                )
                if r.status_code == 200:
                    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
        except Exception:
            pass

    return None


def _regex_extract_fields(text: str) -> dict[str, Any]:
    """Deterministic fallback extraction for common Jamaican visa document fields."""
    out: dict[str, Any] = {}
    if not text:
        return out
    m_ds = re.search(r"\b(AA[A-Z0-9]{6,12})\b", text)
    if m_ds:
        out["ds160_confirmation_id"] = m_ds.group(1)
    m_pp = re.search(r"\b([A-Z]\d{6,8})\b", text)
    if m_pp and "passport" in text.lower():
        out["passport_number"] = m_pp.group(1)
    m_email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m_email:
        out["email"] = m_email.group(0)
    m_phone = re.search(r"(?:\+?1[-.\s]?)?(?:\(?876\)?|\(?658\)?)[-.\s]?\d{3}[-.\s]?\d{4}", text)
    if m_phone:
        out["phone"] = m_phone.group(0)
    return out


def scan_document_with_ai(db: Session, path: Path, mime_type: str, filename: str) -> dict[str, Any]:
    """Run AI Vision/OCR + text extraction to classify a client document and pull structured profile fields."""
    ext = path.suffix.lower()
    raw_text = extract_text_from_file(path)
    is_image = mime_type.startswith("image/") or ext in (".png", ".jpg", ".jpeg", ".webp")

    prompt = (
        "You are scanning a Jamaican U.S. Visa applicant's uploaded document (passport, payslip, bank statement, "
        "RGD birth/marriage certificate, employment letter, or DS-160/AIS confirmation). "
        "Return ONLY valid JSON with keys:\n"
        "- 'category': one of ['passport_id','financial_payslips','rgd_civil','embassy_forms','photos_other']\n"
        "- 'document_type': short human name (e.g. 'Jamaican Passport Bio Page', 'Monthly Payslip', 'RGD Birth Certificate')\n"
        "- 'summary': concise 1-2 sentence summary of what the document shows\n"
        "- 'extracted_text': key readable text extracted\n"
        "- 'extracted_fields': object containing ONLY fields clearly visible from this allowed set: "
        "[full_name, dob (YYYY-MM-DD), passport_number, passport_expiry (YYYY-MM-DD), email, phone, parish, "
        "occupation, employer_name, monthly_gross_jmd (number), monthly_net_jmd (number), ds160_confirmation_id, "
        "ais_appointment_barcode, us_destination, purpose_of_trip, marital_status, intended_travel_date (YYYY-MM-DD), "
        "intended_return_date (YYYY-MM-DD), embassy_interview_date (YYYY-MM-DD)]. Omit any field not clearly present.\n"
        "- 'compliance_alerts': array of short strings if any Kingston Embassy risk is spotted (e.g. passport expires within 6 months, RGD needs 92% copy)."
    )

    ai_raw: str | None = None
    if is_image:
        ai_raw = _call_vision_model(db, path.read_bytes(), mime_type if mime_type.startswith("image/") else "image/png", prompt)
    elif ext == ".pdf" and len(raw_text) < 80:
        # Flat scanned PDF — render page 1 to PNG and run Vision OCR!
        try:
            page_png = render_pdf_page_png(path, 0, scale=1.8)
            ai_raw = _call_vision_model(db, page_png, "image/png", prompt)
        except Exception:
            pass
    elif raw_text:
        res = call_llm_detailed(db, prompt, f"Filename: {filename}\n\nDocument Text:\n{raw_text[:8000]}")
        ai_raw = res.get("text")

    parsed: dict[str, Any] = {}
    if ai_raw:
        try:
            m = re.search(r"\{[\s\S]*\}", ai_raw)
            if m:
                parsed = json.loads(m.group(0))
        except Exception:
            parsed = {}

    category = str(parsed.get("category") or "").strip()
    if category not in VALID_CATEGORIES:
        category = guess_document_category(filename, raw_text or str(parsed.get("extracted_text") or ""))

    extracted_fields = parsed.get("extracted_fields") if isinstance(parsed.get("extracted_fields"), dict) else {}
    # Clean null/empty fields
    clean_fields: dict[str, Any] = {}
    allowed_fields = {
        "full_name", "dob", "passport_number", "passport_expiry", "email", "phone", "parish",
        "occupation", "employer_name", "monthly_gross_jmd", "monthly_net_jmd", "ds160_confirmation_id",
        "ais_appointment_barcode", "us_destination", "purpose_of_trip", "marital_status",
        "intended_travel_date", "intended_return_date", "embassy_interview_date",
    }
    for k, v in extracted_fields.items():
        if k not in allowed_fields or v is None or v == "" or str(v).lower() in ("null", "none", "n/a", "unknown"):
            continue
        if k in ("monthly_gross_jmd", "monthly_net_jmd"):
            try:
                clean_fields[k] = float(str(v).replace(",", "").replace("JMD", "").replace("$", "").strip())
            except Exception:
                continue
        else:
            clean_fields[k] = str(v).strip()

    if not clean_fields and raw_text:
        clean_fields = _regex_extract_fields(raw_text)

    combined_text = raw_text or str(parsed.get("extracted_text") or "")
    summary = str(parsed.get("summary") or "").strip() or (
        f"Indexed {filename} ({category.replace('_', ' ')})"
        + (f" — detected {len(clean_fields)} field(s)." if clean_fields else ".")
    )
    alerts = parsed.get("compliance_alerts") if isinstance(parsed.get("compliance_alerts"), list) else []

    return {
        "category": category,
        "document_type": str(parsed.get("document_type") or filename),
        "summary": summary,
        "extracted_text": combined_text[:15000],
        "extracted_fields": clean_fields,
        "compliance_alerts": [str(a) for a in alerts if str(a).strip()],
    }


def _parse_hex_color(hex_str: str) -> tuple[float, float, float]:
    h = (hex_str or "#0f172a").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    except Exception:
        return 0.06, 0.09, 0.16


def _decode_data_url_png(data_url: str) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return None


def burn_annotations_to_new_version(
    src_path: Path,
    annotations: list[dict[str, Any]],
    out_dir: Path,
    base_name: str,
    docx_paragraphs: list[str] | None = None,
) -> tuple[Path, str]:
    """Burn text boxes, checkmarks, dates, and drawn/typed signatures into a brand-new versioned PDF, PNG, or DOCX."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = src_path.suffix.lower()

    # 1. DOCX text editing
    if ext == ".docx" and docx_paragraphs is not None:
        out_path = out_dir / f"{base_name}_edited_{ts}.docx"
        doc = DocxDocument(str(src_path))
        for idx, new_txt in enumerate(docx_paragraphs):
            if idx < len(doc.paragraphs):
                doc.paragraphs[idx].text = new_txt
            else:
                doc.add_paragraph(new_txt)
        doc.save(str(out_path))
        return out_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # 2. PDF overlay burn-in (keeps original vector PDF razor-sharp!)
    if ext == ".pdf":
        out_path = out_dir / f"{base_name}_edited_{ts}.pdf"
        reader = PdfReader(str(src_path))
        writer = PdfWriter()

        by_page: dict[int, list[dict[str, Any]]] = {}
        for ann in annotations:
            p_idx = int(ann.get("page", 0))
            by_page.setdefault(p_idx, []).append(ann)

        for p_idx, page in enumerate(reader.pages):
            writer.add_page(page)
            target_page = writer.pages[-1]
            page_anns = by_page.get(p_idx, [])
            if page_anns:
                pw = float(target_page.mediabox.width)
                ph = float(target_page.mediabox.height)
                buf = io.BytesIO()
                c = rl_canvas.Canvas(buf, pagesize=(pw, ph))
                for ann in page_anns:
                    atype = str(ann.get("type") or "text")
                    nx = max(0.0, min(1.0, float(ann.get("x", 0.1))))
                    ny = max(0.0, min(1.0, float(ann.get("y", 0.1))))
                    px = nx * pw
                    # PDF origin is bottom-left; canvas UI origin is top-left
                    py = ph - (ny * ph)

                    if atype == "signature" and ann.get("data_url"):
                        sig_bytes = _decode_data_url_png(str(ann["data_url"]))
                        if sig_bytes:
                            nw = float(ann.get("w", 0.24)) * pw
                            nh = float(ann.get("h", 0.08)) * ph
                            c.drawImage(ImageReader(io.BytesIO(sig_bytes)), px, py - nh, width=nw, height=nh, mask="auto")
                    else:
                        txt = str(ann.get("text") or ("✓" if atype == "check" else "")).strip()
                        if not txt:
                            continue
                        font_size = max(7, min(48, int(ann.get("font_size", 12))))
                        font_name = "Helvetica-Bold" if ann.get("bold") or atype == "check" else "Helvetica"
                        r, g, b = _parse_hex_color(str(ann.get("color", "#0f172a")))
                        c.setFillColorRGB(r, g, b)
                        c.setFont(font_name, font_size)
                        for line_i, line in enumerate(txt.splitlines()):
                            c.drawString(px, py - font_size - (line_i * (font_size + 3)), line)
                c.save()
                buf.seek(0)
                overlay_page = PdfReader(buf).pages[0]
                target_page.merge_page(overlay_page)

        with out_path.open("wb") as f:
            writer.write(f)
        return out_path, "application/pdf"

    # 3. Image overlay burn-in (PNG / JPG / WEBP -> versioned PNG)
    out_path = out_dir / f"{base_name}_edited_{ts}.png"
    img = Image.open(src_path).convert("RGBA")
    iw, ih = img.size
    draw = ImageDraw.Draw(img)

    for ann in annotations:
        atype = str(ann.get("type") or "text")
        px = int(max(0.0, min(1.0, float(ann.get("x", 0.1)))) * iw)
        py = int(max(0.0, min(1.0, float(ann.get("y", 0.1)))) * ih)
        if atype == "signature" and ann.get("data_url"):
            sig_bytes = _decode_data_url_png(str(ann["data_url"]))
            if sig_bytes:
                sig_img = Image.open(io.BytesIO(sig_bytes)).convert("RGBA")
                sw = max(40, int(float(ann.get("w", 0.25)) * iw))
                sh = max(20, int(float(ann.get("h", 0.09)) * ih))
                sig_img = sig_img.resize((sw, sh), Image.Resampling.LANCZOS)
                img.alpha_composite(sig_img, (px, py))
        else:
            txt = str(ann.get("text") or ("✓" if atype == "check" else "")).strip()
            if not txt:
                continue
            font_size = max(12, min(72, int(float(ann.get("font_size", 16)) * (iw / 700.0))))
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            color = str(ann.get("color", "#0f172a"))
            draw.multiline_text((px, py), txt, fill=color, font=font)

    img.convert("RGB").save(str(out_path), format="PNG")
    return out_path, "image/png"


def convert_to_rgd_92_pdf(src_path: Path, out_dir: Path, case_id: str) -> Path:
    """Scale any Jamaican RGD certificate (image or PDF) to exact 92% on U.S. Letter so serial numbers are never cut off."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{case_id}_RGD_92pct_{src_path.stem}_{ts}.pdf"
    letter_w, letter_h = letter  # 612 x 792 pt

    page_images: list[bytes] = []
    if src_path.suffix.lower() == ".pdf":
        n_pages = get_pdf_page_count(src_path)
        for i in range(min(n_pages, 6)):
            page_images.append(render_pdf_page_png(src_path, i, scale=2.2))
    else:
        im = Image.open(src_path).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        page_images.append(buf.getvalue())

    c = rl_canvas.Canvas(str(out_path), pagesize=letter)
    max_w = letter_w * 0.92
    max_h = letter_h * 0.92

    for png_bytes in page_images:
        im = Image.open(io.BytesIO(png_bytes))
        iw, ih = im.size
        ratio = min(max_w / max(1, iw), max_h / max(1, ih))
        draw_w = iw * ratio
        draw_h = ih * ratio
        x = (letter_w - draw_w) / 2.0
        y = (letter_h - draw_h) / 2.0
        c.drawImage(ImageReader(io.BytesIO(png_bytes)), x, y, width=draw_w, height=draw_h)
        c.setFillColor(colors.HexColor("#64748b"))
        c.setFont("Helvetica", 7)
        c.drawCentredString(letter_w / 2.0, 12, f"92% Scale Copy — Jamaican RGD Kingston Embassy Compliant ({case_id})")
        c.showPage()

    c.save()
    return out_path


def ai_autofill_official_pdf(src_path: Path, client: ClientCase, out_dir: Path) -> tuple[Path, dict[str, str]]:
    """Auto-fill an official government PDF/DOCX for a client; adds a pre-filled reference cover page for flat PDFs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    filled_path, fields = fill_custom_blueprint(src_path, client)
    if src_path.suffix.lower() != ".pdf":
        target = out_dir / filled_path.name
        target.write_bytes(filled_path.read_bytes())
        return target, fields

    reader = PdfReader(str(filled_path))
    has_acro = bool(reader.get_fields())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    final_path = out_dir / f"{client.case_id}_{src_path.stem}_autofilled_{ts}.pdf"

    if has_acro:
        final_path.write_bytes(filled_path.read_bytes())
        return final_path, fields

    # Flat government PDF: prepend a crisp Jahtaria Auto-Filled Summary Sheet so staff can copy/overlay in Document Studio
    cover_buf = io.BytesIO()
    c = rl_canvas.Canvas(cover_buf, pagesize=letter)
    w, h = letter
    c.setFillColor(colors.HexColor("#1a472a"))
    c.rect(0, h - 68, w, 68, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(36, h - 34, f"AI Pre-Filled Reference Sheet — {src_path.stem.replace('_', ' ')}")
    c.setFont("Helvetica", 9.5)
    c.drawString(36, h - 52, f"Case {client.case_id} | {fields['full_name']} | Visa: {fields['visa_class']} | Generated: {fields['generated_date']}")

    y = h - 102
    c.setFillColor(colors.HexColor("#0f172a"))
    for k in (
        "full_name", "dob", "nationality", "parish", "passport_number", "passport_expiry",
        "ds160_confirmation_id", "ais_appointment_barcode", "email", "phone",
        "occupation", "employer_name", "monthly_gross_jmd", "monthly_net_jmd",
        "purpose_of_trip", "us_destination", "intended_travel_date", "intended_return_date",
        "marital_status", "children_count", "prior_us_refusals", "us_relatives_details",
    ):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(36, y, f"{k.replace('_', ' ').title()}:")
        c.setFont("Helvetica", 9.5)
        c.drawString(210, y, str(fields.get(k, ""))[:75])
        y -= 24
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(36, 40, "Open this file in the Full-Screen Document Studio to place text, checkmarks & signatures directly onto the form pages below.")
    c.showPage()
    c.save()
    cover_buf.seek(0)

    writer = PdfWriter()
    writer.append(PdfReader(cover_buf))
    writer.append(reader)
    with final_path.open("wb") as f:
        writer.write(f)
    return final_path, fields


def export_client_embassy_packet(client: ClientCase, bundle_format: str = "pdf") -> tuple[Path, str, list[str]]:
    """Bundle a client's approved assets + vault documents into one printable merged PDF or ZIP package."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    files_to_include: list[tuple[str, Path]] = []

    for a in client.assets:
        p = Path(a.file_path)
        if p.exists() and a.approval_status != "rejected":
            files_to_include.append((a.filename, p))
    for d in client.documents:
        p = Path(d.file_path)
        if p.exists():
            files_to_include.append((f"{d.category}_{d.filename}", p))

    included_names = [name for name, _ in files_to_include]

    if bundle_format == "zip":
        out_path = GENERATED_DIR / f"{client.case_id}_Embassy_Packet_{ts}.zip"
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, p in files_to_include:
                zf.write(p, arcname=name)
        return out_path, "application/zip", included_names

    # Merged printable PDF
    out_path = GENERATED_DIR / f"{client.case_id}_Embassy_Packet_{ts}.pdf"
    writer = PdfWriter()

    # Cover sheet
    cover_buf = io.BytesIO()
    c = rl_canvas.Canvas(cover_buf, pagesize=letter)
    w, h = letter
    c.setFillColor(colors.HexColor("#1a472a"))
    c.rect(0, h - 90, w, 90, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#ffd700"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, h - 36, "JAHTARIA TRAVEL SERVICES — KINGSTON EMBASSY PACKET")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, h - 64, f"{client.case_id} — {client.full_name or client.pseudonym} ({client.visa_class})")
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica", 10.5)
    c.drawString(40, h - 125, f"Good Standing: {client.standing_score}%   |   DS-160: {client.ds160_confirmation_id or 'Pending'}   |   Passport Expiry: {client.passport_expiry or 'Pending'}")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, h - 165, f"Included Documents ({len(files_to_include)}):")
    y = h - 188
    c.setFont("Helvetica", 9.5)
    for idx, (name, _) in enumerate(files_to_include[:24], start=1):
        c.drawString(52, y, f"{idx}. {name}")
        y -= 18
    c.showPage()
    c.save()
    cover_buf.seek(0)
    writer.append(PdfReader(cover_buf))

    for _, p in files_to_include:
        ext = p.suffix.lower()
        if ext == ".pdf":
            try:
                writer.append(PdfReader(str(p)))
            except Exception:
                continue
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                img_buf = io.BytesIO()
                im = Image.open(p).convert("RGB")
                iw, ih = im.size
                c2 = rl_canvas.Canvas(img_buf, pagesize=letter)
                ratio = min((letter[0] - 56) / max(1, iw), (letter[1] - 56) / max(1, ih))
                dw, dh = iw * ratio, ih * ratio
                c2.drawImage(ImageReader(im), (letter[0] - dw) / 2.0, (letter[1] - dh) / 2.0, width=dw, height=dh)
                c2.showPage()
                c2.save()
                img_buf.seek(0)
                writer.append(PdfReader(img_buf))
            except Exception:
                continue

    with out_path.open("wb") as f:
        writer.write(f)
    return out_path, "application/pdf", included_names
