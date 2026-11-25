"""Universal File & ZIP Client Synthesizer: extracts multiple new clients + matched vault files from ZIP, TXT, MD, JSON, DOCX, PDF, CSV & XLSX."""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
import zipfile
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.config import CLIENT_VAULT_DIR
from app.services.hermes_engine import call_llm_detailed


ALLOWED_SYNTH_FIELDS = {
    "full_name",
    "email",
    "phone",
    "parish",
    "visa_class",
    "passport_number",
    "passport_expiry",
    "dob",
    "ds160_confirmation_id",
    "ais_appointment_barcode",
    "intended_travel_date",
    "intended_return_date",
    "purpose_of_trip",
    "us_destination",
    "us_host_contact",
    "occupation",
    "employer_name",
    "monthly_gross_jmd",
    "monthly_net_jmd",
    "marital_status",
    "children_count",
    "prior_us_refusals",
    "has_us_relatives",
    "us_relatives_details",
    "embassy_interview_date",
    "open_verification_items",
    "service_package_usd",
}


def _extract_text_from_bytes(filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower()
    try:
        if ext in (".txt", ".md", ".csv", ".json", ".tsv"):
            return raw.decode("utf-8", errors="replace")
        if ext == ".xlsx":
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            lines = []
            for r in ws.iter_rows(values_only=True):
                vals = ["" if v is None else str(v) for v in r]
                if any(vals):
                    lines.append(",".join(vals))
            return "\n".join(lines)
        if ext == ".docx":
            doc = DocxDocument(io.BytesIO(raw))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for tbl in doc.tables:
                for row in tbl.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            return "\n".join(parts)
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(raw))
            parts = []
            for p in reader.pages[:20]:
                parts.append(p.extract_text() or "")
            return "\n".join(parts)
    except Exception:
        return ""
    return ""


def _parse_structured_clients(filename: str, raw: bytes) -> list[dict[str, Any]]:
    """Fast deterministic parser for CSV, XLSX, and JSON client lists."""
    ext = Path(filename).suffix.lower()
    rows: list[dict[str, Any]] = []

    if ext == ".json":
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                data = data.get("clients") or data.get("customers") or data.get("records") or [data]
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        norm = {str(k).strip().lower().replace(" ", "_"): v for k, v in item.items()}
                        nm = str(norm.get("full_name") or norm.get("name") or norm.get("client_name") or "").strip()
                        if nm:
                            clean = _sanitize_client_dict({**norm, "full_name": nm})
                            rows.append(clean)
        except Exception:
            pass
        return rows

    if ext in (".csv", ".xlsx"):
        text = _extract_text_from_bytes(filename, raw)
        if not text.strip():
            return []
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                norm = {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}
                nm = norm.get("full_name") or norm.get("name") or norm.get("client_name")
                if nm:
                    rows.append(_sanitize_client_dict({**norm, "full_name": nm}))
        except Exception:
            pass
    return rows


def _sanitize_client_dict(d: dict[str, Any]) -> dict[str, Any]:
    alias_map = {
        "name": "full_name",
        "client_name": "full_name",
        "employer": "employer_name",
        "destination": "us_destination",
        "purpose": "purpose_of_trip",
        "salary": "monthly_gross_jmd",
        "gross_salary": "monthly_gross_jmd",
        "net_salary": "monthly_net_jmd",
        "interview_date": "embassy_interview_date",
        "ds160": "ds160_confirmation_id",
    }
    clean: dict[str, Any] = {}
    for raw_k, v in d.items():
        if v is None or v == "":
            continue
        k = alias_map.get(raw_k, raw_k)
        if k not in ALLOWED_SYNTH_FIELDS:
            continue
        if k in ("monthly_gross_jmd", "monthly_net_jmd", "service_package_usd"):
            try:
                clean[k] = float(str(v).replace(",", "").replace("$", "").replace("JMD", "").strip())
            except Exception:
                pass
        elif k in ("children_count", "prior_us_refusals"):
            try:
                clean[k] = int(float(str(v).strip()))
            except Exception:
                pass
        elif k == "has_us_relatives":
            clean[k] = str(v).strip().lower() in ("true", "yes", "1")
        else:
            clean[k] = str(v).strip()
    if clean.get("full_name") and not clean.get("visa_class"):
        clean["visa_class"] = "B1/B2"
    if clean.get("full_name") and not clean.get("parish"):
        clean["parish"] = "Kingston & St. Andrew"
    return clean


def _fallback_parse_txt_clients(text: str) -> list[dict[str, Any]]:
    """Deterministic parser for plain TXT / MD files containing structured blocks or lines of client info."""
    clients: list[dict[str, Any]] = []
    # Split by blank lines or '---' separators
    blocks = re.split(r"\n\s*(?:---+|\*\*\*+|===+)\s*\n|\n{2,}", text.strip())
    for blk in blocks:
        if not blk.strip():
            continue
        rec: dict[str, Any] = {}
        for line in blk.splitlines():
            m = re.match(r"^\s*[-*•]?\s*([A-Za-z0-9 _/-]{2,32})\s*[:=]\s*(.+)$", line.strip())
            if m:
                key = m.group(1).strip().lower().replace(" ", "_").replace("-", "_")
                val = m.group(2).strip()
                rec[key] = val
        clean = _sanitize_client_dict(rec)
        if clean.get("full_name"):
            clients.append(clean)
    return clients


def synthesize_clients_from_text(db: Session, text: str, source_label: str = "uploaded file") -> list[dict[str, Any]]:
    """Use live LLM (with deterministic fallback) to synthesize 1..N client records from unstructured TXT/MD/DOCX/PDF text."""
    snippet = text.strip()[:16000]
    if not snippet:
        return []

    sys_prompt = (
        "You are a precision data synthesizer for Jahtaria Travel Services (Jamaican U.S. Visa Intelligence).\n"
        "Extract ALL distinct prospective or existing visa clients mentioned in the provided document(s).\n"
        "Return ONLY valid JSON of the form: {\"clients\": [ { ... }, ... ]}.\n"
        "Each client object may ONLY use these keys: "
        + ", ".join(sorted(ALLOWED_SYNTH_FIELDS))
        + "\nRules:\n"
        "- Every client MUST have a real 'full_name'.\n"
        "- Normalize dates to YYYY-MM-DD when possible, numbers as pure numbers (no JMD/$).\n"
        "- If the document is NOT a client list / intake profile (e.g., it is just a blank form or embassy notice with no client names), return {\"clients\": []}.\n"
    )
    res = call_llm_detailed(db, sys_prompt, f"Source: {source_label}\n\nCONTENT:\n{snippet}")
    raw = res.get("text") or ""
    if raw:
        try:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                parsed = json.loads(m.group(0))
                arr = parsed.get("clients")
                if isinstance(arr, list):
                    out = []
                    seen_names: set[str] = set()
                    for item in arr:
                        if isinstance(item, dict):
                            c = _sanitize_client_dict(item)
                            nm_key = (c.get("full_name") or "").lower()
                            if nm_key and nm_key not in seen_names:
                                seen_names.add(nm_key)
                                out.append(c)
                    if out:
                        return out
        except Exception:
            pass

    return _fallback_parse_txt_clients(snippet)


def synthesize_zip_archive(db: Session, zip_bytes: bytes, zip_filename: str) -> dict[str, Any]:
    """Unpack a ZIP archive safely, synthesize all client records, and stage matching documents for Vault attachment."""
    batch_id = f"zip_{secrets.token_hex(6)}"
    staging_dir = CLIENT_VAULT_DIR / "_staging" / batch_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    synthesized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    staged_files: list[dict[str, Any]] = []
    combined_text_parts: list[str] = []
    file_count = 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Zip-slip protection + macOS junk filter
            inner_path = Path(info.filename)
            if "__MACOSX" in inner_path.parts or inner_path.name.startswith("."):
                continue
            if info.file_size > 25 * 1024 * 1024:
                continue
            file_count += 1
            if file_count > 100:
                break

            raw = zf.read(info)
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", inner_path.name)
            ext = inner_path.suffix.lower()

            # Stage binary/document files so they can be attached to matching clients on Confirm
            if ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".txt"):
                staged_path = staging_dir / f"{file_count:03d}_{safe_name}"
                staged_path.write_bytes(raw)
                staged_files.append(
                    {
                        "filename": safe_name,
                        "rel_path": info.filename,
                        "staged_path": str(staged_path),
                        "ext": ext,
                        "size_bytes": len(raw),
                    }
                )

            # Parse structured CSV/XLSX/JSON immediately
            if ext in (".csv", ".xlsx", ".json"):
                for c in _parse_structured_clients(safe_name, raw):
                    nm_key = c["full_name"].lower()
                    if nm_key not in seen_names:
                        seen_names.add(nm_key)
                        synthesized.append(c)
            elif ext in (".txt", ".md", ".docx", ".pdf"):
                txt = _extract_text_from_bytes(safe_name, raw)
                if txt.strip():
                    combined_text_parts.append(f"=== FILE: {info.filename} ===\n{txt[:4000]}")

    if combined_text_parts:
        ai_clients = synthesize_clients_from_text(db, "\n\n".join(combined_text_parts), source_label=zip_filename)
        for c in ai_clients:
            nm_key = c["full_name"].lower()
            if nm_key not in seen_names:
                seen_names.add(nm_key)
                synthesized.append(c)

    # Match staged documents to synthesized clients by filename / folder name overlap
    for c in synthesized:
        parts = [p.lower() for p in re.split(r"[\s_-]+", c["full_name"]) if len(p) >= 3]
        matched_paths = []
        for sf in staged_files:
            hay = sf["rel_path"].lower()
            if any(p in hay for p in parts):
                matched_paths.append({"filename": sf["filename"], "staged_path": sf["staged_path"]})
        if matched_paths:
            c["_matched_files"] = matched_paths

    return {
        "batch_id": batch_id,
        "staging_dir": str(staging_dir),
        "files_scanned": file_count,
        "staged_files_count": len(staged_files),
        "clients": synthesized,
    }
