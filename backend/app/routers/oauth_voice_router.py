"""Subscription OAuth, Grouped Model Picker & Voice Mode API Router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import User
from app.services.connectors import set_setting
from app.services.oauth_hub import (
    exchange_antigravity_code,
    get_grouped_model_catalog,
    import_local_subscription_tokens,
    poll_oauth_status,
    start_antigravity_oauth_flow,
    start_codex_oauth_flow,
)
from app.services.voice_engine import get_voice_config, save_voice_config, synthesize_speech

router = APIRouter(prefix="/api", tags=["oauth_and_voice"])


class OAuthStartRequest(BaseModel):
    provider: str  # openai-codex | antigravity


class OAuthExchangeRequest(BaseModel):
    flow_id: str
    code_or_url: str


class ClaudeTokenRequest(BaseModel):
    token: str


class SelectModelRequest(BaseModel):
    provider: str
    model: str


class DisconnectProviderRequest(BaseModel):
    provider: str


class VoiceConfigRequest(BaseModel):
    engine: str | None = None
    default_persona: str | None = None
    auto_speak: bool | None = None
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    fish_api_key: str | None = None
    fish_voice_id: str | None = None


class SpeakRequest(BaseModel):
    text: str
    persona: str | None = None
    engine: str | None = None


# ── Grouped Model Picker & Subscription OAuth ────────────────────────────────

@router.get("/models/catalog")
def list_model_catalog(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_grouped_model_catalog(db)


@router.post("/models/select")
def select_active_model(
    req: SelectModelRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    set_setting(db, "ai_provider", req.provider.strip(), is_secret=False, category="ai")
    set_setting(db, "ai_model", req.model.strip(), is_secret=False, category="ai")
    return get_grouped_model_catalog(db)


@router.post("/oauth/start")
def oauth_start(
    req: OAuthStartRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
) -> dict[str, Any]:
    prov = req.provider.strip().lower()
    if prov in ("openai-codex", "codex", "chatgpt"):
        return start_codex_oauth_flow()
    if prov in ("antigravity", "agy"):
        return start_antigravity_oauth_flow()
    raise HTTPException(status_code=400, detail=f"Unsupported OAuth flow provider: {req.provider}")


@router.get("/oauth/poll/{flow_id}")
def oauth_poll(
    flow_id: str,
    _user: User = Depends(require_roles("ceo", "staff")),
) -> dict[str, Any]:
    return poll_oauth_status(flow_id)


@router.post("/oauth/exchange")
def oauth_exchange(
    req: OAuthExchangeRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return exchange_antigravity_code(db, req.flow_id, req.code_or_url)


@router.post("/oauth/claude-token")
def save_claude_subscription_token(
    req: ClaudeTokenRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    tok = req.token.strip()
    if not tok:
        raise HTTPException(status_code=400, detail="Paste your Claude setup-token or OAuth token.")
    set_setting(db, "claude_oauth_token", tok, is_secret=True, category="oauth")
    set_setting(db, "ai_provider", "claude-sub", is_secret=False, category="ai")
    set_setting(db, "ai_model", "claude-sonnet-4-5", is_secret=False, category="ai")
    return {"ok": True, "provider": "claude-sub", "status": "connected"}


@router.post("/oauth/import-local")
def import_local_tokens(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    res = import_local_subscription_tokens(db)
    return {**res, "catalog": get_grouped_model_catalog(db)}


@router.post("/oauth/disconnect")
def disconnect_provider(
    req: DisconnectProviderRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    p = req.provider.strip().lower()
    if p == "openai-codex":
        set_setting(db, "codex_access_token", "", is_secret=True, category="oauth")
        set_setting(db, "codex_refresh_token", "", is_secret=True, category="oauth")
    elif p == "claude-sub":
        set_setting(db, "claude_oauth_token", "", is_secret=True, category="oauth")
    elif p == "antigravity":
        set_setting(db, "antigravity_access_token", "", is_secret=True, category="oauth")
        set_setting(db, "antigravity_refresh_token", "", is_secret=True, category="oauth")
    return {"ok": True, "catalog": get_grouped_model_catalog(db)}


# ── Voice Engine Endpoints (Available to CEO, Staff & Customers!) ────────────

@router.get("/voice/config")
def voice_config_get(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_voice_config(db)


@router.post("/voice/config")
def voice_config_update(
    req: VoiceConfigRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return save_voice_config(db, req.model_dump(exclude_none=True))


@router.post("/voice/speak")
async def voice_speak(
    req: SpeakRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        audio, engine_used = await synthesize_speech(db, req.text, persona=req.persona, engine_override=req.engine)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Voice synthesis failed: {exc}") from exc
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"X-Voice-Engine": engine_used},
    )
