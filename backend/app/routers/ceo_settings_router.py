"""CEO Executive Intelligence, White-Label Branding, 4-Card Easy Setup Hub & Built-in /mcp Server."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import LOGO_PATH
from app.database import get_db
from app.models import (
    BrandingConfig,
    ClientCase,
    GeneratedAsset,
    GovSource,
    InterviewEvent,
    OfficialDocument,
    PipelineJournal,
    RiskFlag,
    SourceManifestItem,
    User,
)
from app.services.connectors import (
    get_composio_status,
    get_mcp_servers,
    get_setting,
    list_settings_safe,
    save_mcp_servers,
    set_setting,
    test_company_db,
    test_mcp_server_url,
    toggle_composio_app,
)
from app.services.hermes_engine import call_llm, call_llm_detailed, detect_available_providers
from app.services.mcp_server import handle_mcp_jsonrpc

router = APIRouter(tags=["ceo_and_settings"])


class BrandingUpdateRequest(BaseModel):
    agency_name: str | None = None
    tagline: str | None = None
    primary_color: str | None = None
    gold_color: str | None = None
    navy_color: str | None = None
    accent_red: str | None = None
    contact_email: str | None = None
    whatsapp_number: str | None = None
    website_url: str | None = None
    compliance_notice: str | None = None


class AiProviderConfigRequest(BaseModel):
    ai_provider: str = "auto"  # auto | antigravity | ollama | openai | anthropic | gemini | xai_grok | openrouter | qwen | minimax
    ai_model: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    xai_api_key: str | None = None
    openrouter_api_key: str | None = None
    qwen_api_key: str | None = None
    minimax_api_key: str | None = None


class ComposioConfigRequest(BaseModel):
    api_key: str | None = None
    toggle_app_id: str | None = None
    connected: bool | None = None
    account_label: str = ""


class ClawLinkConfigRequest(BaseModel):
    base_url: str = ""
    token: str | None = None
    channel: str = ""
    enabled: bool = True


class CompanyDbRequest(BaseModel):
    company_db_url: str


class McpServerItem(BaseModel):
    name: str
    url: str
    transport: str = "streamable_http"  # streamable_http | sse
    enabled: bool = True


class McpTestRequest(BaseModel):
    url: str
    transport: str = "streamable_http"


@router.get("/api/ceo/overview")
def get_ceo_overview(
    _ceo: User = Depends(require_roles("ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    clients = db.query(ClientCase).all()
    total = len(clients)
    approved = sum(1 for c in clients if c.outcome == "approved")
    refused = sum(1 for c in clients if c.outcome == "refused")
    pending = sum(1 for c in clients if c.outcome in ("pending", "unknown"))
    decided = approved + refused
    approval_rate = round((approved / decided) * 100, 1) if decided else 0.0
    avg_standing = round(sum(c.standing_score for c in clients) / total, 1) if total else 0.0
    pipeline_value = round(sum(c.service_package_usd for c in clients), 2)

    stage_counts = dict(Counter(c.pipeline_stage for c in clients))
    risk_counts = dict(Counter(c.denial_risk_level for c in clients))
    visa_counts = dict(Counter(c.visa_class for c in clients))

    # Top active red/amber risk flags across portfolio
    all_flags = db.query(RiskFlag).filter(RiskFlag.severity.in_(("red", "amber")), RiskFlag.resolved == False).all()  # noqa: E712
    top_risks = [{"code": code, "count": cnt} for code, cnt in Counter(f.title for f in all_flags).most_common(6)]

    # Compliant Prediction Evaluation (separating profile-driven vs universal policy question!)
    embassy_events = db.query(InterviewEvent).filter(InterviewEvent.event_mode == "embassy_reported").all()
    profile_events = [e for e in embassy_events if e.theme != "home_country_safety"]
    policy_events = [e for e in embassy_events if e.theme == "home_country_safety"]
    profile_hits = sum(1 for e in profile_events if e.pre_interview_predicted_theme)
    profile_recall = round((profile_hits / len(profile_events)) * 100, 1) if profile_events else 0.0
    frozen_cases = sum(1 for c in clients if c.predictions_frozen)

    pending_approvals = db.query(GeneratedAsset).filter(GeneratedAsset.approval_status == "pending_approval").count()
    approved_assets = db.query(GeneratedAsset).filter(GeneratedAsset.approval_status == "approved").count()
    sources = db.query(GovSource).all()
    diff_alerts = sum(1 for s in sources if s.diff_alert)
    recent_journal = db.query(PipelineJournal).order_by(PipelineJournal.id.desc()).limit(12).all()

    return {
        "kpis": {
            "total_cases": total,
            "approved_cases": approved,
            "refused_cases": refused,
            "active_pending_cases": pending,
            "reported_approval_rate_pct": approval_rate,
            "avg_good_standing_pct": avg_standing,
            "pending_document_approvals": pending_approvals,
            "approved_deliverables": approved_assets,
            "estimated_pipeline_usd": pipeline_value,
            "official_sources_count": len(sources),
            "official_pdfs_count": db.query(OfficialDocument).count(),
            "source_manifest_count": db.query(SourceManifestItem).count(),
            "source_diff_alerts": diff_alerts,
        },
        "stage_distribution": stage_counts,
        "risk_distribution": risk_counts,
        "visa_distribution": visa_counts,
        "top_risk_flags": top_risks,
        "prediction_evaluation": {
            "frozen_cases_count": frozen_cases,
            "profile_questions_observed": len(profile_events),
            "profile_thematic_hits": profile_hits,
            "profile_thematic_recall_pct": profile_recall,
            "policy_questions_tracked_separately": len(policy_events),
            "compliance_note": "Universal policy questions (e.g. home_country_safety) are tracked separately from profile recall per JAHTARIA engineering handoff rules. User-reported outcomes require independent verification.",
        },
        "recent_activity": [
            {
                "id": j.id,
                "case_id": j.case_id,
                "event_type": j.event_type,
                "actor": j.actor,
                "summary": j.summary,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in recent_journal
        ],
    }


@router.put("/api/ceo/branding")
def update_branding(
    req: BrandingUpdateRequest,
    _ceo: User = Depends(require_roles("ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    b = db.query(BrandingConfig).first()
    if not b:
        b = BrandingConfig()
        db.add(b)
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is not None and hasattr(b, k):
            setattr(b, k, v.strip())
    db.commit()
    db.refresh(b)
    return {
        "agency_name": b.agency_name,
        "tagline": b.tagline,
        "logo_url": b.logo_url,
        "primary_color": b.primary_color,
        "gold_color": b.gold_color,
        "navy_color": b.navy_color,
        "accent_red": b.accent_red,
        "contact_email": b.contact_email,
        "whatsapp_number": b.whatsapp_number,
        "website_url": b.website_url,
        "compliance_notice": b.compliance_notice,
    }


@router.post("/api/ceo/branding/logo")
async def upload_agency_logo(
    file: UploadFile = File(...),
    _ceo: User = Depends(require_roles("ceo")),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo must be under 5 MB.")
    LOGO_PATH.write_bytes(data)
    b = db.query(BrandingConfig).first()
    if b:
        b.logo_url = "/api/branding/logo"
        db.commit()
    return {"logo_url": "/api/branding/logo"}


@router.get("/api/settings/setup-hub")
def get_setup_hub(
    request: Request,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    from app.config import mask_secret

    claw_url = get_setting(db, "clawlink_base_url", "")
    claw_tok = get_setting(db, "clawlink_token", "")
    claw_chan = get_setting(db, "clawlink_channel", "")
    return {
        "ai_providers": detect_available_providers(db),
        "settings": list_settings_safe(db),
        "composio": get_composio_status(db),
        "clawlink": {
            "configured": bool(claw_url or claw_tok),
            "base_url": claw_url,
            "token_masked": mask_secret(claw_tok),
            "channel": claw_chan,
        },
        "company_db_url": get_setting(db, "company_db_url", ""),
        "mcp_servers": get_mcp_servers(db),
        "inbound_mcp_endpoint": f"{base_url}/mcp",
        "claude_desktop_snippet": json.dumps(
            {
                "mcpServers": {
                    "jahtaria-jamaica-govbot": {
                        "url": f"{base_url}/mcp",
                        "transport": "streamable-http",
                    }
                }
            },
            indent=2,
        ),
    }


@router.post("/api/settings/ai-provider")
def save_ai_provider(
    req: AiProviderConfigRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.oauth_hub import clear_model_catalog_cache, get_grouped_model_catalog

    prev_provider = (get_setting(db, "ai_provider", "auto") or "auto").strip().lower() or "auto"
    new_provider = (req.ai_provider or "auto").strip().lower() or "auto"

    set_setting(db, "ai_provider", new_provider, is_secret=False, category="ai")
    if new_provider == "antigravity":
        set_setting(db, "antigravity_disabled", "", is_secret=False, category="oauth")

    if req.ai_model is not None and req.ai_model.strip():
        set_setting(db, "ai_model", req.ai_model.strip(), is_secret=False, category="ai")
    elif new_provider == "auto":
        set_setting(db, "ai_model", "auto-flagship", is_secret=False, category="ai")
    elif new_provider != prev_provider:
        # Reset stale model ID from previous provider so catalog selects the new provider's flagship
        set_setting(db, "ai_model", "", is_secret=False, category="ai")

    set_setting(db, "ollama_base_url", req.ollama_base_url, is_secret=False, category="ai")
    set_setting(db, "ollama_model", req.ollama_model, is_secret=False, category="ai")

    for field_name in (
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
        "xai_api_key",
        "openrouter_api_key",
        "qwen_api_key",
        "minimax_api_key",
    ):
        val = getattr(req, field_name)
        if val is not None and val.strip() and "•" not in val:
            set_setting(db, field_name, val.strip(), is_secret=True, category="ai")

    clear_model_catalog_cache()
    return {
        "saved": True,
        "providers": detect_available_providers(db),
        "catalog": get_grouped_model_catalog(db),
    }


@router.post("/api/settings/test-ai")
def test_ai_provider(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    res = call_llm_detailed(db, "Reply with a single short sentence confirming connection.", "Confirm Jahtaria Visa Intelligence connection.")
    if res["text"]:
        return {
            "ok": True,
            "provider_used": res["provider"],
            "reply": res["text"],
        }
    if res["error"]:
        return {
            "ok": False,
            "provider_used": res["provider"],
            "error": res["error"],
            "reply": f"Provider error ({res['provider']}): {res['error']}",
        }
    return {
        "ok": False,
        "provider_used": res["provider"],
        "reply": "No AI provider connected yet. Connect ChatGPT/Codex, Claude Pro/Max, Antigravity, Local Ollama, or an API key.",
    }


@router.post("/api/settings/composio")
def update_composio(
    req: ComposioConfigRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if req.api_key is not None and req.api_key.strip() and "•" not in req.api_key:
        set_setting(db, "composio_api_key", req.api_key.strip(), is_secret=True, category="composio")
    if req.toggle_app_id is not None and req.connected is not None:
        return toggle_composio_app(db, req.toggle_app_id, req.connected, req.account_label)
    return get_composio_status(db)


@router.post("/api/settings/clawlink")
def update_clawlink(
    req: ClawLinkConfigRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    import httpx
    from app.config import mask_secret

    if req.base_url.strip():
        set_setting(db, "clawlink_base_url", req.base_url.strip().rstrip("/"), is_secret=False, category="clawlink")
    if req.token is not None and req.token.strip() and "•" not in req.token:
        set_setting(db, "clawlink_token", req.token.strip(), is_secret=True, category="clawlink")
    if req.channel.strip():
        set_setting(db, "clawlink_channel", req.channel.strip(), is_secret=False, category="clawlink")

    url = get_setting(db, "clawlink_base_url", "")
    tok = get_setting(db, "clawlink_token", "")
    probe_ok = False
    probe_note = "Saved locally"
    if url:
        try:
            headers = {"Authorization": f"Bearer {tok}"} if tok else {}
            with httpx.Client(timeout=5.0) as client:
                r = client.get(url, headers=headers)
                probe_ok = r.status_code < 500
                probe_note = f"Reachable (HTTP {r.status_code})"
        except Exception as exc:
            probe_note = f"Saved (endpoint check: {str(exc)[:120]})"
    return {
        "ok": True,
        "configured": bool(url or tok),
        "base_url": url,
        "token_masked": mask_secret(tok),
        "channel": get_setting(db, "clawlink_channel", ""),
        "reachable": probe_ok,
        "note": probe_note,
    }


@router.post("/api/settings/company-db/test")
def test_and_save_company_db(
    req: CompanyDbRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    res = test_company_db(req.company_db_url)
    if res.get("ok"):
        set_setting(db, "company_db_url", req.company_db_url.strip(), is_secret=True, category="database")
    return res


@router.post("/api/settings/mcp-servers")
def update_mcp_servers(
    servers: list[McpServerItem],
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return save_mcp_servers(db, [s.model_dump() for s in servers])


@router.post("/api/settings/mcp-servers/test")
def probe_mcp_server(
    req: McpTestRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
) -> dict[str, Any]:
    return test_mcp_server_url(req.url, req.transport)


@router.post("/mcp")
async def inbound_mcp_endpoint(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Exposed Streamable HTTP / JSON-RPC 2.0 MCP endpoint for Claude Desktop, ChatGPT, Antigravity & Assimilis."""
    body = await request.json()
    return handle_mcp_jsonrpc(db, body)
