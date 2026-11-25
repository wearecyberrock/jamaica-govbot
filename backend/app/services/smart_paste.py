"""Smart Paste Auto-Setup (API Keys, MCP, ClawLink, CSV), Natural-Language Client CRUD & Dynamic Data Table Generator."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import mask_secret
from app.models import ClientCase, ClientDocument, GovSource, PendingAction, User
from app.services.connectors import get_mcp_servers, get_setting, save_mcp_servers, set_setting, test_mcp_server_url
from app.services.hermes_engine import call_llm_detailed
from app.services.scraper import scrape_single_source


# ── 1. Smart Paste Auto-Setup (Auto-applies low-risk setup with Undo + Secret Redaction!) ──

_KEY_PATTERNS: list[tuple[str, str, str, str]] = [
    # (provider_id, setting_key, label, regex)
    ("anthropic", "anthropic_api_key", "Anthropic Claude API", r"\b(sk-ant-[A-Za-z0-9_-]{20,})\b"),
    ("openrouter", "openrouter_api_key", "OpenRouter API", r"\b(sk-or-v1-[A-Za-z0-9_-]{20,})\b"),
    ("xai_grok", "xai_api_key", "xAI Grok API", r"\b(xai-[A-Za-z0-9_-]{20,})\b"),
    ("gemini", "gemini_api_key", "Google Gemini API", r"\b(AIza[0-9A-Za-z_-]{30,})\b"),
    ("openai", "openai_api_key", "OpenAI API", r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b"),
]


def detect_and_apply_smart_paste(db: Session, user: User, msg: str) -> dict[str, Any] | None:
    """Auto-detect pasted API keys, MCP URLs/JSON, ClawLink creds, or pasted CSV customer data."""
    if user.role not in ("ceo", "staff"):
        return None
    text = msg.strip()
    low = text.lower()

    # A. ClawLink URL / Token paste
    if "clawlink" in low:
        url_m = re.search(r"(https?://[^\s\"'<>]+)", text)
        tok_m = re.search(r"(?:token|key|secret|bearer)[\s:=]+([A-Za-z0-9._-]{12,})", text, re.I)
        if url_m or tok_m:
            old_url = get_setting(db, "clawlink_base_url", "")
            old_tok = get_setting(db, "clawlink_token", "")
            new_url = url_m.group(1).rstrip("/") if url_m else old_url
            new_tok = tok_m.group(1) if tok_m else old_tok
            if new_url:
                set_setting(db, "clawlink_base_url", new_url, is_secret=False, category="clawlink")
            if new_tok:
                set_setting(db, "clawlink_token", new_tok, is_secret=True, category="clawlink")
            redacted = text.replace(new_tok, mask_secret(new_tok)) if new_tok and new_tok in text else text
            act = PendingAction(
                user_id=user.id,
                action_type="update_setting",
                target_ref="clawlink",
                summary=f"Auto-configured ClawLink ({new_url or 'token saved'})",
                before_json=json.dumps({"clawlink_base_url": old_url, "clawlink_token": old_tok}),
                after_json=json.dumps({"clawlink_base_url": new_url, "clawlink_token": new_tok}),
                status="applied",
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            return {
                "kind": "clawlink",
                "redacted_message": redacted,
                "pending_action": act,
                "ui_panel": {"panel": "settings", "title": "Connections & AI Setup"},
                "reply": (
                    f"**ClawLink connected automatically!**\n\n"
                    f"- **Endpoint:** `{new_url or '(keep existing)'}`\n"
                    f"- **Token:** `{mask_secret(new_tok) if new_tok else 'Not provided'}` (encrypted at rest & masked from chat history)\n\n"
                    "Click **Undo Change** below anytime to revert."
                ),
            }

    # B. Composio API key paste
    if "composio" in low:
        comp_m = re.search(r"(?:ak_[A-Za-z0-9_-]{12,}|(?:key|token)[\s:=]+([A-Za-z0-9_-]{16,}))", text, re.I)
        if comp_m:
            raw_key = comp_m.group(1) if comp_m.lastindex else comp_m.group(0)
            old_key = get_setting(db, "composio_api_key", "")
            set_setting(db, "composio_api_key", raw_key, is_secret=True, category="composio")
            redacted = text.replace(raw_key, mask_secret(raw_key))
            act = PendingAction(
                user_id=user.id,
                action_type="update_setting",
                target_ref="composio",
                summary=f"Auto-configured Composio API Key ({mask_secret(raw_key)})",
                before_json=json.dumps({"composio_api_key": old_key}),
                after_json=json.dumps({"composio_api_key": raw_key}),
                status="applied",
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            return {
                "kind": "composio_key",
                "redacted_message": redacted,
                "pending_action": act,
                "ui_panel": {"panel": "settings", "title": "Connections & AI Setup"},
                "reply": (
                    f"**Composio API key saved & encrypted!** (`{mask_secret(raw_key)}`)\n\n"
                    "You can now toggle **Gmail**, **Google Sheets**, **Google Docs**, and **Microsoft 365 / OneDrive** right in the side panel. "
                    "Your secret was masked in chat history — click **Undo Change** below to revert."
                ),
            }

    # C. Cloud AI API Key paste (auto-detects OpenAI, Anthropic, Gemini, xAI Grok, OpenRouter)
    for prov_id, setting_key, label, pattern in _KEY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            raw_key = m.group(1)
            old_key = get_setting(db, setting_key, "")
            old_prov = get_setting(db, "ai_provider", "auto")
            set_setting(db, setting_key, raw_key, is_secret=True, category="ai")
            set_setting(db, "ai_provider", prov_id, is_secret=False, category="ai")
            redacted = text.replace(raw_key, mask_secret(raw_key))
            act = PendingAction(
                user_id=user.id,
                action_type="update_setting",
                target_ref=prov_id,
                summary=f"Auto-connected {label} ({mask_secret(raw_key)}) & activated provider",
                before_json=json.dumps({setting_key: old_key, "ai_provider": old_prov}),
                after_json=json.dumps({setting_key: raw_key, "ai_provider": prov_id}),
                status="applied",
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            return {
                "kind": "api_key",
                "redacted_message": redacted,
                "pending_action": act,
                "ui_panel": {"panel": "settings", "title": "Connections & AI Setup"},
                "reply": (
                    f"**{label} connected automatically!** (`{mask_secret(raw_key)}`)\n\n"
                    f"- Saved encrypted at rest and set `{prov_id}` as active AI provider.\n"
                    "- Secret key was automatically masked from your chat history.\n\n"
                    "Click **Undo Change** below if you'd like to revert."
                ),
            }

    # D. MCP Server JSON (`{"mcpServers": {...}}`) or direct MCP URL (`http(s)://.../mcp` or `/sse`)
    mcp_entries: list[dict[str, Any]] = []
    if "mcpservers" in low and "{" in text:
        try:
            jm = re.search(r"\{[\s\S]*\}", text)
            if jm:
                parsed = json.loads(jm.group(0))
                servers_map = parsed.get("mcpServers") or {}
                if isinstance(servers_map, dict):
                    for sname, cfg in servers_map.items():
                        if isinstance(cfg, dict):
                            u = str(cfg.get("url") or cfg.get("serverUrl") or "").strip()
                            if u:
                                tr = "sse" if ("sse" in str(cfg.get("transport", "")).lower() or u.endswith("/sse")) else "streamable_http"
                                mcp_entries.append({"name": str(sname), "url": u, "transport": tr, "enabled": True})
        except Exception:
            pass
    elif "mcp" in low or re.search(r"https?://[^\s\"'<>]+/(?:mcp|sse)\b", text, re.I):
        url_m = re.search(r"(https?://[^\s\"'<>]+)", text)
        if url_m:
            u = url_m.group(1).rstrip(".,);")
            if "/mcp" in u.lower() or "/sse" in u.lower() or "mcp" in low:
                host = re.sub(r"^https?://", "", u).split("/")[0].replace(":", "-")
                tr = "sse" if u.lower().endswith("/sse") else "streamable_http"
                mcp_entries.append({"name": f"mcp-{host}", "url": u, "transport": tr, "enabled": True})

    if mcp_entries:
        old_servers = get_mcp_servers(db)
        new_servers = list(old_servers)
        probe_notes: list[str] = []
        for entry in mcp_entries:
            new_servers = [s for s in new_servers if s.get("url") != entry["url"]]
            new_servers.append(entry)
            probe = test_mcp_server_url(entry["url"], entry["transport"])
            if probe.get("ok"):
                probe_notes.append(f"- **{entry['name']}** (`{entry['url']}`): Online — discovered **{probe.get('tool_count', 0)}** tool(s)")
            else:
                probe_notes.append(f"- **{entry['name']}** (`{entry['url']}`): Saved (probe note: `{probe.get('error', 'unreachable right now')}`)")
        save_mcp_servers(db, new_servers)
        act = PendingAction(
            user_id=user.id,
            action_type="update_mcp_servers",
            target_ref="mcp_servers",
            summary=f"Auto-registered {len(mcp_entries)} MCP server(s): {', '.join(e['name'] for e in mcp_entries)}",
            before_json=json.dumps({"servers": old_servers}),
            after_json=json.dumps({"servers": new_servers}),
            status="applied",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return {
            "kind": "mcp_server",
            "redacted_message": text,
            "pending_action": act,
            "ui_panel": {"panel": "settings", "title": "Connections & AI Setup"},
            "reply": (
                f"**Registered {len(mcp_entries)} MCP server(s) automatically!**\n\n"
                + "\n".join(probe_notes)
                + "\n\nClick **Undo Change** below anytime to remove."
            ),
        }

    # D2. Official Government / Agency Website URL paste -> ACTUALLY add to GovSource & scrape live!
    any_url_m = re.search(r"(https?://[^\s\"'<>]+)", text)
    if any_url_m:
        raw_url = any_url_m.group(1).rstrip(".,);")
        is_add_resource_intent = any(
            k in low
            for k in ("add ", "save ", "resource", "source", "official", "bookmark", "track ", "scrape ", "monitor ")
        ) or text.strip() == raw_url or any(dom in raw_url.lower() for dom in (".gov", ".gov.jm", "usembassy.gov", "state.gov"))
        # Skip if it's purely a question like "was https://jis.gov.jm/ added"
        is_just_checking = any(low.startswith(p) for p in ("was ", "is ", "did ", "has ", "check if "))
        if is_add_resource_intent and not is_just_checking:
            parsed_u = urlparse(raw_url)
            host = (parsed_u.netloc or raw_url).replace("www.", "")
            existing_src = db.query(GovSource).filter(GovSource.url == raw_url).first()
            if not existing_src:
                existing_src = db.query(GovSource).filter(GovSource.url == raw_url.rstrip("/")).first()
            if existing_src:
                scrape_res = scrape_single_source(db, existing_src)
                return {
                    "kind": "gov_source",
                    "redacted_message": text,
                    "pending_action": None,
                    "ui_panel": {"panel": "gov_sources", "title": "Official Scraped Gov Sources"},
                    "reply": (
                        f"**{existing_src.name}** (`{existing_src.url}`) is already in your Official Resources — "
                        f"I refreshed it live (`status: {scrape_res.get('status')}`) and opened **Official Scraped Gov Sources** in the side panel."
                    ),
                }

            # Fetch page title cleanly if reachable
            page_title = ""
            try:
                with httpx.Client(timeout=8.0, follow_redirects=True, headers={"User-Agent": "JahtariaVisaBot/2.1"}) as client:
                    rr = client.get(raw_url)
                    if rr.status_code < 400:
                        soup = BeautifulSoup(rr.text[:25000], "html.parser")
                        if soup.title and soup.title.string:
                            page_title = re.sub(r"\s+", " ", soup.title.string).strip()[:120]
            except Exception:
                pass

            name = page_title or host
            agency = host.upper() if ".gov" in host.lower() else host
            if "jis.gov.jm" in host.lower():
                agency = "Jamaica Information Service (JIS)"
            elif ".gov.jm" in host.lower():
                agency = f"Government of Jamaica ({host})"
            elif ".gov" in host.lower():
                agency = f"U.S. Government ({host})"

            category = "jamaica_civil" if ".jm" in host.lower() else "us_dos"
            src_key = re.sub(r"[^a-z0-9_]+", "_", host.lower()).strip("_")[:50]
            if db.query(GovSource).filter(GovSource.source_key == src_key).first():
                src_key = f"{src_key}_{int(datetime.now(timezone.utc).timestamp())}"

            src = GovSource(
                source_key=src_key,
                name=name,
                agency=agency,
                category=category,
                url=raw_url,
                verified_summary=f"Official resource added by {user.full_name}: {name} ({raw_url}).",
                content_hash=hashlib.sha256(raw_url.encode("utf-8")).hexdigest(),
                scrape_status="pending_scrape",
                enabled=True,
            )
            db.add(src)
            db.commit()
            scrape_res = scrape_single_source(db, src)
            db.refresh(src)

            act = PendingAction(
                user_id=user.id,
                action_type="add_gov_source",
                target_ref=src.source_key,
                summary=f"Added Official Resource: {src.name} ({src.url})",
                before_json=json.dumps({"source_key": src.source_key}),
                after_json=json.dumps({"source_key": src.source_key, "url": src.url, "name": src.name}),
                status="applied",
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            return {
                "kind": "gov_source",
                "redacted_message": text,
                "pending_action": act,
                "ui_panel": {"panel": "gov_sources", "title": "Official Scraped Gov Sources"},
                "reply": (
                    f"**Added to Official Resources & Scraped Live!**\n\n"
                    f"- **Name:** {src.name}\n"
                    f"- **Agency:** {src.agency}\n"
                    f"- **URL:** {src.url}\n"
                    f"- **Live Scrape Status:** `{scrape_res.get('status')}`\n\n"
                    "It is now saved in your database and visible in the **Official Scraped Gov Sources** panel on the right (click **Undo Change** below anytime to remove it)."
                ),
            }

    # E. Pasted multi-line CSV customer data
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2 and "," in lines[0]:
        hdr = [c.strip().lower().replace(" ", "_") for c in lines[0].split(",")]
        if any(k in hdr for k in ("full_name", "name", "client_name")) and len(hdr) >= 2:
            reader = csv.DictReader(io.StringIO("\n".join(lines)))
            parsed_rows = []
            for row in reader:
                norm = {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}
                nm = norm.get("full_name") or norm.get("name") or norm.get("client_name")
                if nm:
                    parsed_rows.append(
                        {
                            "full_name": nm,
                            "email": norm.get("email", ""),
                            "phone": norm.get("phone", ""),
                            "parish": norm.get("parish", "Kingston & St. Andrew"),
                            "visa_class": norm.get("visa_class", "B1/B2") or "B1/B2",
                            "occupation": norm.get("occupation", ""),
                            "employer_name": norm.get("employer") or norm.get("employer_name", ""),
                            "us_destination": norm.get("us_destination") or norm.get("destination", ""),
                            "purpose_of_trip": norm.get("purpose_of_trip") or norm.get("purpose", ""),
                        }
                    )
            if parsed_rows:
                names_preview = ", ".join(r["full_name"] for r in parsed_rows[:5])
                if len(parsed_rows) > 5:
                    names_preview += f" (+{len(parsed_rows) - 5} more)"
                act = PendingAction(
                    user_id=user.id,
                    action_type="bulk_create_clients",
                    target_ref="clients",
                    summary=f"Import {len(parsed_rows)} new client(s) from pasted CSV: {names_preview}",
                    before_json=json.dumps({}),
                    after_json=json.dumps({"clients": parsed_rows}),
                    status="pending",
                )
                db.add(act)
                db.commit()
                db.refresh(act)
                return {
                    "kind": "csv_import",
                    "redacted_message": text,
                    "pending_action": act,
                    "ui_panel": {"panel": "spreadsheet", "title": "Client Spreadsheet"},
                    "reply": (
                        f"Detected **{len(parsed_rows)} new customer row(s)** from your pasted CSV (`{names_preview}`).\n\n"
                        "Review and click **Confirm & Apply** below to import them into your Client Spreadsheet (with full Undo)."
                    ),
                }

    return None


# ── 2. AI Natural-Language Client Creation & ANY-Field Editing ───────────────

ALLOWED_CLIENT_FIELDS = {
    "full_name", "email", "phone", "parish", "visa_class", "pipeline_stage",
    "passport_number", "passport_expiry", "dob", "ds160_confirmation_id",
    "ais_appointment_barcode", "intended_travel_date", "intended_return_date",
    "purpose_of_trip", "us_destination", "us_host_contact", "occupation",
    "employer_name", "monthly_gross_jmd", "monthly_net_jmd", "marital_status",
    "children_count", "prior_us_refusals", "has_us_relatives",
    "us_relatives_details", "embassy_interview_date", "open_verification_items",
    "assigned_staff", "service_package_usd",
}


def detect_natural_client_crud(
    db: Session,
    user: User,
    msg: str,
    target_cid: str | None,
) -> PendingAction | None:
    """Use AI structured extraction to propose creating a new client or editing ANY client field (with Confirm & Undo)."""
    if user.role not in ("ceo", "staff"):
        return None
    low = msg.lower()

    is_create_intent = any(
        k in low
        for k in (
            "add new client", "new client", "create client", "add customer",
            "new customer", "create customer", "register client", "onboard client",
            "add client ",
        )
    )
    is_edit_intent = bool(target_cid) and any(
        k in low
        for k in (
            "update ", "change ", "set ", "edit ", "rename ", "fix ",
            "put ", "mark ", "move ", "record ",
        )
    ) and not any(k in low for k in ("question", "pdf", "roadmap", "checklist", "worksheet", "agency name"))

    if not is_create_intent and not is_edit_intent:
        return None

    res = call_llm_detailed(
        db,
        (
            "Extract client visa case fields from the user's instruction. Return ONLY valid JSON with keys:\n"
            "- 'action': 'create_client' or 'update_client' or 'none'\n"
            "- 'fields': object using ONLY allowed keys: "
            + ", ".join(sorted(ALLOWED_CLIENT_FIELDS))
            + "\nNumeric fields (monthly_gross_jmd, monthly_net_jmd, service_package_usd) must be numbers; "
            "integer fields (children_count, prior_us_refusals) integers; has_us_relatives boolean; dates YYYY-MM-DD. "
            "If the user is just asking a question rather than requesting a data creation/update, return {'action':'none','fields':{}}."
        ),
        f"Current Selected Case: {target_cid or 'None'}\nUser Message: {msg}",
    )
    raw = res.get("text") or ""
    parsed: dict[str, Any] = {}
    if raw:
        try:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                parsed = json.loads(m.group(0))
        except Exception:
            parsed = {}

    action = str(parsed.get("action") or "none")
    fields_raw = parsed.get("fields") if isinstance(parsed.get("fields"), dict) else {}

    # Deterministic fallback for simple "add new client Name..." if LLM isn't configured
    if action == "none" and is_create_intent:
        nm_m = re.search(r"(?:new\s+(?:client|customer)|add\s+(?:new\s+)?(?:client|customer)|create\s+(?:client|customer))[:\s-]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})", msg, re.I)
        if nm_m:
            action = "create_client"
            fields_raw = {"full_name": nm_m.group(1).strip().title()}

    clean: dict[str, Any] = {}
    for k, v in fields_raw.items():
        if k not in ALLOWED_CLIENT_FIELDS or v is None or v == "":
            continue
        if k in ("monthly_gross_jmd", "monthly_net_jmd", "service_package_usd"):
            try:
                clean[k] = float(str(v).replace(",", "").replace("$", "").replace("JMD", "").strip())
            except Exception:
                continue
        elif k in ("children_count", "prior_us_refusals"):
            try:
                clean[k] = int(v)
            except Exception:
                continue
        elif k == "has_us_relatives":
            clean[k] = bool(v)
        else:
            clean[k] = str(v).strip()

    if not clean:
        return None

    if action == "create_client" or (is_create_intent and clean.get("full_name")):
        if not clean.get("full_name"):
            return None
        diff_str = ", ".join(f"{k}: {v!r}" for k, v in list(clean.items())[:6])
        act = PendingAction(
            user_id=user.id,
            action_type="create_client",
            target_ref="new_client",
            summary=f"Create new client '{clean['full_name']}' ({diff_str})",
            before_json=json.dumps({}),
            after_json=json.dumps(clean),
            status="pending",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    if action == "update_client" and target_cid:
        client = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first()
        if not client:
            return None
        before: dict[str, Any] = {}
        for k in clean:
            if k in ("passport_number", "dob"):
                before[k] = "(encrypted)"
            elif hasattr(client, k):
                before[k] = getattr(client, k)
        diff_str = ", ".join(f"{k}: {before.get(k)!r} → {v!r}" for k, v in clean.items())
        act = PendingAction(
            user_id=user.id,
            action_type="update_client",
            target_ref=client.case_id,
            summary=f"Update {client.case_id} ({diff_str})",
            before_json=json.dumps(before, default=str),
            after_json=json.dumps(clean, default=str),
            status="pending",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    return None


# ── 3. Dynamic In-Chat Data Tables & Charts (Query/Filter/Sort/Group Clients) ─

def query_clients_structured(
    db: Session,
    search: str = "",
    stage: str = "",
    visa_class: str = "",
    parish: str = "",
    risk: str = "",
    outcome: str = "",
    min_standing: int | None = None,
    max_standing: int | None = None,
    only_prior_refusals: bool = False,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = db.query(ClientCase)
    if stage:
        q = q.filter(ClientCase.pipeline_stage == stage)
    if visa_class:
        q = q.filter(ClientCase.visa_class.ilike(f"%{visa_class}%"))
    if parish:
        q = q.filter(ClientCase.parish.ilike(f"%{parish}%"))
    if risk:
        q = q.filter(ClientCase.denial_risk_level == risk.lower())
    if outcome:
        q = q.filter(ClientCase.outcome == outcome.lower())
    if min_standing is not None:
        q = q.filter(ClientCase.standing_score >= min_standing)
    if max_standing is not None:
        q = q.filter(ClientCase.standing_score <= max_standing)
    if only_prior_refusals:
        q = q.filter(ClientCase.prior_us_refusals > 0)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (ClientCase.case_id.ilike(like))
            | (ClientCase.full_name.ilike(like))
            | (ClientCase.pseudonym.ilike(like))
            | (ClientCase.parish.ilike(like))
            | (ClientCase.occupation.ilike(like))
        )

    rows = q.all()

    risk_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    def sort_key(c: ClientCase):
        if sort_by == "standing_score":
            return c.standing_score
        if sort_by == "denial_risk_level":
            return risk_rank.get((c.denial_risk_level or "").lower(), 0)
        if sort_by == "monthly_gross_jmd":
            return c.monthly_gross_jmd or 0.0
        if sort_by == "full_name":
            return (c.full_name or c.pseudonym or "").lower()
        if sort_by == "embassy_interview_date":
            return c.embassy_interview_date or "9999-12-31"
        if sort_by == "case_id":
            return c.case_id
        if sort_by == "pipeline_stage":
            return c.pipeline_stage or ""
        return c.updated_at.timestamp() if c.updated_at else 0.0

    rows.sort(key=sort_key, reverse=(sort_dir.lower() == "desc"))

    # Pre-count vault docs per client
    doc_counts: dict[str, int] = {}
    for d in db.query(ClientDocument.case_id).all():
        if d[0]:
            doc_counts[d[0]] = doc_counts.get(d[0], 0) + 1

    out = []
    for c in rows[:limit]:
        out.append(
            {
                "case_id": c.case_id,
                "full_name": c.full_name or c.pseudonym,
                "visa_class": c.visa_class,
                "parish": c.parish or "—",
                "pipeline_stage": c.pipeline_stage,
                "standing_score": c.standing_score,
                "denial_risk_level": c.denial_risk_level,
                "outcome": c.outcome,
                "monthly_gross_jmd": c.monthly_gross_jmd,
                "monthly_net_jmd": c.monthly_net_jmd,
                "prior_us_refusals": c.prior_us_refusals,
                "embassy_interview_date": c.embassy_interview_date or "—",
                "ds160_confirmation_id": c.ds160_confirmation_id or "Pending",
                "passport_expiry": c.passport_expiry or "Pending",
                "document_count": doc_counts.get(c.case_id, 0) + len(c.assets),
            }
        )
    return out


def build_dynamic_data_table(db: Session, msg: str) -> dict[str, Any] | None:
    """Detect when a user asks to view, filter, sort, compare, or chart client data and return an interactive table+chart."""
    low = msg.lower()
    triggers = (
        "table", "spreadsheet", "sort client", "sort case", "sort by", "filter client",
        "show all client", "list client", "list case", "compare", "group by", "by parish",
        "by risk", "by stage", "by visa", "high risk", "high-risk", "low standing",
        "standing under", "standing below", "standing above", "prior refusal",
        "refused case", "approved case", "salary", "income", "chart", "breakdown",
    )
    if not any(t in low for t in triggers):
        return None
    # Don't hijack single-client specific questions like "what is C034 salary?"
    if re.search(r"\bc[0o]?\d{2,3}\b", low) and not any(k in low for k in ("all", "table", "spreadsheet", "compare", "sort")):
        return None

    # Parse criteria
    sort_by = "standing_score"
    sort_dir = "desc"
    risk = ""
    visa_class = ""
    parish = ""
    outcome = ""
    min_standing = None
    max_standing = None
    only_prior_refusals = False
    group_field = ""

    if "risk" in low:
        sort_by, sort_dir = "denial_risk_level", "desc"
        if "high risk" in low or "high-risk" in low:
            risk = "high"
        elif "critical" in low:
            risk = "critical"
        elif "low risk" in low:
            risk = "low"
    if "salary" in low or "income" in low or "gross" in low:
        sort_by, sort_dir = "monthly_gross_jmd", "desc"
    elif "interview" in low or "date" in low:
        sort_by, sort_dir = "embassy_interview_date", "asc"
    elif "name" in low or "alphabet" in low:
        sort_by, sort_dir = "full_name", "asc"
    elif "standing" in low:
        sort_by = "standing_score"
        sort_dir = "asc" if any(k in low for k in ("low", "worst", "under", "below", "asc")) else "desc"

    m_under = re.search(r"(?:under|below|<)\s*(\d{1,3})%?", low)
    if m_under:
        max_standing = int(m_under.group(1))
    m_above = re.search(r"(?:above|over|>)\s*(\d{1,3})%?", low)
    if m_above:
        min_standing = int(m_above.group(1))

    for vc in ("b1/b2", "b1", "b2", "f1", "f-1", "h2b", "h-2b", "j1", "j-1"):
        if vc in low:
            visa_class = vc.upper().replace("-", "")
            break
    for pr in ("kingston", "st. andrew", "st andrew", "st. catherine", "montego bay", "st. james", "manchester", "clarendon", "st. ann", "portland", "westmoreland"):
        if pr in low:
            parish = pr
            break
    if "refused" in low:
        outcome = "refused"
    elif "approved" in low:
        outcome = "approved"
    if "prior refusal" in low or "214" in low:
        only_prior_refusals = True

    if "by parish" in low:
        group_field = "parish"
    elif "by risk" in low:
        group_field = "denial_risk_level"
    elif "by stage" in low:
        group_field = "pipeline_stage"
    elif "by visa" in low:
        group_field = "visa_class"

    rows = query_clients_structured(
        db,
        visa_class=visa_class,
        parish=parish,
        risk=risk,
        outcome=outcome,
        min_standing=min_standing,
        max_standing=max_standing,
        only_prior_refusals=only_prior_refusals,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=60,
    )

    # Build chart summary
    chart_items: list[dict[str, Any]] = []
    if group_field:
        counts: dict[str, int] = {}
        for r in rows:
            k = str(r.get(group_field) or "Unspecified")
            counts[k] = counts.get(k, 0) + 1
        palette = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
        for i, (lbl, val) in enumerate(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]):
            chart_items.append({"label": lbl.replace("_", " ").title(), "value": val, "color": palette[i % len(palette)]})
    else:
        risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for r in rows:
            rk = str(r.get("denial_risk_level", "medium")).lower()
            risk_counts[rk] = risk_counts.get(rk, 0) + 1
        colors_map = {"low": "#10b981", "medium": "#f59e0b", "high": "#f97316", "critical": "#ef4444"}
        for rk, cnt in risk_counts.items():
            if cnt > 0:
                chart_items.append({"label": f"{rk.title()} Risk", "value": cnt, "color": colors_map.get(rk, "#3b82f6")})

    columns = [
        {"key": "case_id", "label": "Case"},
        {"key": "full_name", "label": "Client"},
        {"key": "visa_class", "label": "Visa"},
        {"key": "standing_score", "label": "Standing %"},
        {"key": "denial_risk_level", "label": "Risk"},
        {"key": "pipeline_stage", "label": "Stage"},
        {"key": "monthly_gross_jmd", "label": "Gross JMD"},
        {"key": "document_count", "label": "Docs"},
    ]

    return {
        "title": f"Client Data View ({len(rows)} matching case{'s' if len(rows) != 1 else ''})",
        "subtitle": f"Sorted by {sort_by.replace('_', ' ')} ({sort_dir.upper()})",
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "columns": columns,
        "rows": rows,
        "chart": {
            "title": f"Breakdown by {group_field.replace('_', ' ').title()}" if group_field else "Denial Risk Distribution",
            "items": chart_items,
        },
    }


# ── 4. Safe Chat Delete / Bulk Wipe (Always Preview/Confirm + Snapshot Undo!) ──

def _snapshot_client(c: ClientCase) -> dict[str, Any]:
    return {
        "case_id": c.case_id,
        "access_code": c.access_code,
        "pseudonym": c.pseudonym,
        "full_name": c.full_name,
        "email": c.email,
        "phone": c.phone,
        "nationality": c.nationality,
        "parish": c.parish,
        "visa_class": c.visa_class,
        "pipeline_stage": c.pipeline_stage,
        "standing_score": c.standing_score,
        "denial_risk_level": c.denial_risk_level,
        "outcome": c.outcome,
        "outcome_evidence": c.outcome_evidence,
        "passport_number_enc": c.passport_number_enc,
        "dob_enc": c.dob_enc,
        "passport_expiry": c.passport_expiry,
        "ds160_confirmation_id": c.ds160_confirmation_id,
        "ais_appointment_barcode": c.ais_appointment_barcode,
        "intended_travel_date": c.intended_travel_date,
        "intended_return_date": c.intended_return_date,
        "purpose_of_trip": c.purpose_of_trip,
        "us_destination": c.us_destination,
        "us_host_contact": c.us_host_contact,
        "occupation": c.occupation,
        "employer_name": c.employer_name,
        "monthly_gross_jmd": c.monthly_gross_jmd,
        "monthly_net_jmd": c.monthly_net_jmd,
        "marital_status": c.marital_status,
        "children_count": c.children_count,
        "prior_us_refusals": c.prior_us_refusals,
        "has_us_relatives": c.has_us_relatives,
        "us_relatives_details": c.us_relatives_details,
        "travel_history_summary": c.travel_history_summary,
        "embassy_interview_date": c.embassy_interview_date,
        "open_verification_items": c.open_verification_items,
        "assigned_staff": c.assigned_staff,
        "service_package_usd": c.service_package_usd,
        "email_muted": bool(getattr(c, "email_muted", False)),
    }


def detect_chat_delete_or_reset(
    db: Session,
    user: User,
    msg: str,
    target_cid: str | None,
) -> PendingAction | None:
    """Detect destructive chat commands (delete client, delete all clients/reference cases, wipe/reset data) behind Confirm + Undo."""
    if user.role not in ("ceo", "staff") and not bool(getattr(user, "all_tiers", False)):
        return None
    low = msg.lower().strip()
    has_del = any(k in low for k in ("delete ", "remove ", "wipe ", "purge ", "clear all", "erase ", "reset all", "reset seed", "restore seed", "restore pristine"))
    if not has_del:
        return None

    # A. Restore pristine unchanged seed data (CEO only)
    if any(k in low for k in ("reset seed", "restore seed", "restore pristine", "unchanged data")):
        if user.role != "ceo" and not bool(getattr(user, "all_tiers", False)):
            return None
        act = PendingAction(
            user_id=user.id,
            action_type="reset_seed_data",
            target_ref="clients",
            summary="Restore all 34 pristine unchanged seed clients (C001–C034) while keeping your API keys & Gov Sources",
            before_json=json.dumps({"snapshot_count": db.query(ClientCase).count()}),
            after_json=json.dumps({"action": "reset_seed_data"}),
            status="pending",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    # B. Delete ALL clients / wipe all data (CEO only!)
    if any(k in low for k in ("delete all data", "wipe all", "clear all data", "delete all client", "delete all case", "remove all client", "erase all")):
        if user.role != "ceo" and not bool(getattr(user, "all_tiers", False)):
            return None
        all_clients = db.query(ClientCase).all()
        if not all_clients:
            return None
        doc_count = db.query(ClientDocument).count()
        snaps = [_snapshot_client(c) for c in all_clients]
        act = PendingAction(
            user_id=user.id,
            action_type="wipe_all_clients",
            target_ref="all_clients",
            summary=f"⚠️ PERMANENT WIPE PREVIEW: Delete ALL {len(all_clients)} client case(s) and {doc_count} vault document(s) (1-click Undo snapshot saved)",
            before_json=json.dumps({"clients": snaps}),
            after_json=json.dumps({"deleted_count": len(all_clients), "doc_count": doc_count}),
            status="pending",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    # C. Delete all Reference Cases
    if "reference" in low and any(k in low for k in ("delete", "remove", "clear")):
        refs = [c for c in db.query(ClientCase).all() if (c.full_name or "").startswith("Reference Case")]
        if not refs:
            return None
        act = PendingAction(
            user_id=user.id,
            action_type="bulk_delete_clients",
            target_ref="reference_cases",
            summary=f"Delete {len(refs)} historical Reference Case(s) (keeps all active clients; Undo available)",
            before_json=json.dumps({"clients": [_snapshot_client(c) for c in refs]}),
            after_json=json.dumps({"case_ids": [c.case_id for c in refs]}),
            status="pending",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    # D. Delete a specific client case (e.g., "delete C034", "remove Marcus Campbell")
    if target_cid and any(k in low for k in ("delete", "remove", "erase")):
        c = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first()
        if not c:
            return None
        act = PendingAction(
            user_id=user.id,
            action_type="delete_client",
            target_ref=c.case_id,
            summary=f"Delete client {c.case_id} ({c.full_name or c.pseudonym}) — Undo snapshot saved",
            before_json=json.dumps({"client": _snapshot_client(c)}),
            after_json=json.dumps({"case_id": c.case_id}),
            status="pending",
        )
        db.add(act)
        db.commit()
        db.refresh(act)
        return act

    return None


# ── 5. Chat-Triggered Gmail Drafting, Cron Execution & Inbox Sync ────────────

def detect_chat_gmail_command(
    db: Session,
    user: User,
    msg: str,
    target_cid: str | None,
) -> dict[str, Any] | None:
    """Handle natural-language Gmail automation commands in chat (draft/queue email, run cron, poll inbox)."""
    if user.role not in ("ceo", "staff") and not bool(getattr(user, "all_tiers", False)):
        return None
    low = msg.lower().strip()

    from app.models import EmailMessageLog
    from app.services.gmail_service import (
        draft_email_for_client,
        get_gmail_config,
        poll_gmail_inbox,
        run_email_automation_cycle,
        sync_rules_to_hermes_cron,
    )

    if any(k in low for k in ("poll inbox", "check inbox", "sync inbox", "check gmail", "poll gmail")):
        res = poll_gmail_inbox(db, limit=25)
        if res.get("ok"):
            reply = (
                f"**Gmail Inbox Synced!** Checked **{res['checked']}** recent email(s), matched **{res['matched_messages']}** client message(s), "
                f"and auto-saved **{res['saved_attachments']}** attachment(s) into Client Vaults."
            )
        else:
            reply = f"**Gmail Inbox Sync Note:** {res.get('error', 'Configure Gmail App Password in the Gmail > Connection tab first.')}"
        return {"reply": reply, "ui_panel": {"panel": "gmail", "title": "Gmail Automation & Cron"}}

    if any(k in low for k in ("run email cron", "run gmail cron", "run gmail automation", "run email rules", "trigger email cron")):
        res = run_email_automation_cycle(db, force=True)
        return {
            "reply": (
                f"**Gmail Automation Cycle Complete!**\n\n"
                f"- **Rules Evaluated:** {res['rules_evaluated']}\n"
                f"- **Sent Live:** {res['messages_sent']}\n"
                f"- **Queued for Approval:** {res['messages_queued']}\n"
                f"- **Dry-Run Previews:** {res['messages_dry_run']}\n"
                f"- **Skipped (Anti-Spam Cooldown):** {res['skipped_cooldown']}\n\n"
                "Opened the **Gmail Automation** panel on the right to review, approve, or copy for WhatsApp."
            ),
            "ui_panel": {"panel": "gmail", "title": "Gmail Automation & Cron"},
        }

    if "hermes cron" in low and any(k in low for k in ("sync", "export", "setup", "configure")):
        res = sync_rules_to_hermes_cron(db)
        return {
            "reply": f"**Hermes Cron Synced ({res['job_count']} active rule(s))!**\n\n{res['note']}",
            "ui_panel": {"panel": "gmail", "title": "Gmail Automation & Cron"},
        }

    if target_cid and any(k in low for k in ("email ", "send email", "draft email", "mail ", "notify ", "remind ")) and any(k in low for k in ("email", "mail", "gmail", "remind", "notify", "passport", "interview")):
        client = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first()
        if client:
            draft = draft_email_for_client(db, client, custom_topic=msg)
            cfg = get_gmail_config(db)
            log = EmailMessageLog(
                case_id=client.case_id,
                direction="outbound",
                status="queued_approval",
                to_email=client.email or "",
                from_email=cfg["gmail_address"] or "pending-gmail-setup",
                subject=draft["subject"],
                body_text=draft["body_text"],
                whatsapp_text=draft["whatsapp_text"],
                ai_reason=draft["ai_reason"],
                delivery_backend="gmail_smtp" if cfg["smtp_ready"] else ("composio" if cfg["composio_gmail_ready"] else "dry_run"),
            )
            db.add(log)
            db.commit()
            return {
                "reply": (
                    f"**Drafted & Queued Personalized Email for {client.case_id} ({client.full_name or client.pseudonym})!**\n\n"
                    f"- **To:** `{client.email or 'No email on file yet'}`\n"
                    f"- **Subject:** {draft['subject']}\n\n"
                    "Review, edit, click **Approve & Send**, or **Copy for WhatsApp** in the **Gmail Automation** panel on the right."
                ),
                "ui_panel": {"panel": "gmail", "title": "Gmail Automation & Cron"},
            }

    return None
