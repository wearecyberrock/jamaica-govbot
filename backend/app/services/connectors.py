"""Connectors: Encrypted Settings Store, Composio OAuth Hub, Company DB Adapter & Outbound MCP Client."""

from __future__ import annotations

import csv
import io
import json
import secrets
from typing import Any

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.config import decrypt_value, encrypt_value, mask_secret
from app.models import AppSetting, ClientCase, PipelineJournal


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row or not row.value_enc:
        return default
    return decrypt_value(row.value_enc)


def set_setting(db: Session, key: str, value: str, is_secret: bool = False, category: str = "general") -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    enc = encrypt_value(value) if value else ""
    if row:
        row.value_enc = enc
        row.is_secret = is_secret
        row.category = category
    else:
        db.add(AppSetting(key=key, value_enc=enc, is_secret=is_secret, category=category))
    db.commit()


def list_settings_safe(db: Session) -> dict[str, Any]:
    rows = db.query(AppSetting).all()
    out: dict[str, Any] = {}
    for r in rows:
        plain = decrypt_value(r.value_enc) if r.value_enc else ""
        out[r.key] = {
            "value": mask_secret(plain) if r.is_secret else plain,
            "configured": bool(plain),
            "is_secret": r.is_secret,
            "category": r.category,
        }
    return out


# ── Outbound MCP Servers ──────────────────────────────────────────────────────

def get_mcp_servers(db: Session) -> list[dict[str, Any]]:
    raw = get_setting(db, "mcp_servers_json", "[]")
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_mcp_servers(db: Session, servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    set_setting(db, "mcp_servers_json", json.dumps(servers), is_secret=False, category="mcp")
    return servers


def test_mcp_server_url(url: str, transport: str = "streamable_http") -> dict[str, Any]:
    """Send an MCP initialize + tools/list probe against an external MCP server URL."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            if transport == "sse":
                r = client.get(url, headers={"Accept": "text/event-stream"})
                return {"ok": r.status_code < 400, "status_code": r.status_code, "transport": transport, "tools": []}
            r = client.post(url, json=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
            if r.status_code < 400:
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                tools = body.get("result", {}).get("tools", []) if isinstance(body, dict) else []
                return {"ok": True, "status_code": r.status_code, "transport": transport, "tool_count": len(tools), "tools": [t.get("name") for t in tools[:15]]}
            return {"ok": False, "status_code": r.status_code, "error": r.text[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


# ── Composio OAuth Connectors (Gmail, Google Sheets, Google Docs, MS 365) ─────

COMPOSIO_APPS = [
    {"app_id": "gmail", "name": "Gmail", "description": "Import client passport scans, payslips & draft follow-up emails for staff approval."},
    {"app_id": "googlesheets", "name": "Google Sheets", "description": "Bidirectional sync with company client tracker & intake spreadsheets."},
    {"app_id": "googledocs", "name": "Google Docs", "description": "Push approved cover letters, DS-160 sheets & checklists to Google Drive."},
    {"app_id": "microsoft_teams_word", "name": "Microsoft 365 (Word / OneDrive)", "description": "Export editable DOCX visa packets to OneDrive / SharePoint."},
    {"app_id": "hubspot_crm", "name": "Company CRM / Contacts", "description": "Pull client contact profile and update visa pipeline stage automatically."},
]


def get_composio_status(db: Session) -> dict[str, Any]:
    api_key = get_setting(db, "composio_api_key", "")
    raw_states = get_setting(db, "composio_connections_json", "{}")
    try:
        states = json.loads(raw_states)
    except Exception:
        states = {}
    apps = []
    for item in COMPOSIO_APPS:
        st = states.get(item["app_id"], {})
        apps.append(
            {
                **item,
                "connected": bool(st.get("connected", False)),
                "account_label": st.get("account_label", ""),
                "last_sync": st.get("last_sync", ""),
            }
        )
    return {
        "api_key_configured": bool(api_key),
        "api_key_masked": mask_secret(api_key),
        "apps": apps,
    }


def toggle_composio_app(db: Session, app_id: str, connected: bool, account_label: str = "") -> dict[str, Any]:
    raw_states = get_setting(db, "composio_connections_json", "{}")
    try:
        states = json.loads(raw_states)
    except Exception:
        states = {}
    states[app_id] = {
        "connected": connected,
        "account_label": account_label or (f"Connected ({app_id})" if connected else ""),
        "last_sync": "Just connected" if connected else "",
    }
    set_setting(db, "composio_connections_json", json.dumps(states), is_secret=False, category="composio")
    return get_composio_status(db)


# ── Company External Database Connector + CSV / Spreadsheet Importer ──────────

def test_company_db(db_url: str) -> dict[str, Any]:
    if not db_url.strip():
        return {"ok": False, "error": "Provide a valid SQLAlchemy URL (e.g. sqlite:///path/to/company.db or postgresql://user:pass@host/db)."}
    try:
        eng = create_engine(db_url.strip(), pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        insp = inspect(eng)
        tables = insp.get_table_names()
        eng.dispose()
        return {"ok": True, "tables": tables[:40], "table_count": len(tables)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240]}


def import_clients_from_csv(db: Session, csv_text: str, actor: str = "Staff") -> dict[str, Any]:
    """Import customer rows from a Google Sheet / Excel CSV export straight into the pipeline."""
    reader = csv.DictReader(io.StringIO(csv_text))
    imported: list[str] = []
    skipped = 0
    existing_count = db.query(ClientCase).count()

    for idx, row in enumerate(reader, start=1):
        norm = {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}
        name = norm.get("full_name") or norm.get("name") or norm.get("client_name") or norm.get("pseudonym")
        if not name:
            skipped += 1
            continue
        case_id = norm.get("case_id") or f"C{existing_count + idx:03d}"
        if db.query(ClientCase).filter(ClientCase.case_id == case_id).first():
            case_id = f"C{existing_count + idx + 100:03d}"
        access_code = f"JAH-{case_id}-{secrets.token_hex(2).upper()}"
        client = ClientCase(
            case_id=case_id,
            access_code=access_code,
            pseudonym=name,
            full_name=name,
            email=norm.get("email", ""),
            phone=norm.get("phone", ""),
            nationality=norm.get("nationality", "Jamaica") or "Jamaica",
            parish=norm.get("parish", ""),
            visa_class=norm.get("visa_class", "B1/B2") or "B1/B2",
            purpose_of_trip=norm.get("purpose_of_trip") or norm.get("purpose", ""),
            us_destination=norm.get("us_destination") or norm.get("destination", ""),
            occupation=norm.get("occupation", ""),
            employer_name=norm.get("employer") or norm.get("employer_name", ""),
            pipeline_stage="data_synced",
            data_quality="imported_spreadsheet",
        )
        db.add(client)
        db.flush()
        db.add(
            PipelineJournal(
                case_id=case_id,
                event_type="spreadsheet_import",
                actor=actor,
                summary=f"Imported client {name} ({case_id}) from Company Spreadsheet/CSV.",
            )
        )
        imported.append(case_id)

    db.commit()
    return {"imported_count": len(imported), "skipped_count": skipped, "case_ids": imported}
