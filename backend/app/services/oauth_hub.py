"""Subscription OAuth Hub & Grouped Model Picker (ChatGPT Codex, Claude Pro/Max, Antigravity, Grok, Ollama & API Keys).

Ported from Elevedenbot/server/api/oauth.py with all internal engine names hidden from end users.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.connectors import get_setting, set_setting

# ── OpenAI / ChatGPT Codex Subscription OAuth (Device Code + PKCE) ───────────
CODEX_ISSUER = "https://auth.openai.com"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_VERIFICATION_URI = f"{CODEX_ISSUER}/codex/device"
CODEX_USER_CODE_URL = f"{CODEX_ISSUER}/api/accounts/deviceauth/usercode"
CODEX_DEVICE_TOKEN_URL = f"{CODEX_ISSUER}/api/accounts/deviceauth/token"
CODEX_TOKEN_URL = f"{CODEX_ISSUER}/oauth/token"
CODEX_REDIRECT_URI = f"{CODEX_ISSUER}/deviceauth/callback"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_USER_AGENT = "codex_cli_rs/0.0.0 (Jahtaria Desktop)"

# ── Antigravity Google OAuth (PKCE — reads optional client creds from env) ───
ANTIGRAVITY_CLIENT_ID = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", "").strip()
ANTIGRAVITY_CLIENT_SECRET = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "").strip()
ANTIGRAVITY_REDIRECT_URI = os.getenv("ANTIGRAVITY_OAUTH_REDIRECT_URI", "https://antigravity.google/oauth-callback").strip()
ANTIGRAVITY_TOKEN_URL = "https://oauth2.googleapis.com/token"
ANTIGRAVITY_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
ANTIGRAVITY_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "openid"
)

_FLOWS: dict[str, dict[str, Any]] = {}
_FLOWS_LOCK = threading.Lock()


def _build_ssl_verify() -> Any:
    """Use OS native cert store (truststore) when available, else bundled certifi CA roots."""
    try:
        import ssl
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        pass
    try:
        import certifi

        return certifi.where()
    except Exception:
        return True


def _http_post(url: str, payload: dict[str, Any], form: bool = False) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": CODEX_USER_AGENT}
    with httpx.Client(timeout=15.0, verify=_build_ssl_verify(), follow_redirects=True) as client:
        if form:
            resp = client.post(url, data=payload, headers=headers)
        else:
            resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ── 1. ChatGPT / OpenAI Codex Device-Code Flow ───────────────────────────────

def start_codex_oauth_flow() -> dict[str, Any]:
    """Request an OpenAI Codex device code and start background polling."""
    try:
        resp = _http_post(CODEX_USER_CODE_URL, {"client_id": CODEX_CLIENT_ID})
    except Exception as exc:
        return {"ok": False, "provider": "openai-codex", "error": f"Could not reach OpenAI device auth: {exc}"}

    device_auth_id = str(resp.get("device_auth_id") or "")
    user_code = str(resp.get("user_code") or resp.get("usercode") or "")
    interval = int(resp.get("interval") or 5)
    flow_id = secrets.token_urlsafe(16)
    expires_at = time.time() + 900

    flow = {
        "flow_id": flow_id,
        "provider": "openai-codex",
        "status": "pending",
        "device_auth_id": device_auth_id,
        "user_code": user_code,
        "verification_uri": CODEX_VERIFICATION_URI,
        "interval": max(3, interval),
        "expires_at": expires_at,
        "error": "",
    }
    with _FLOWS_LOCK:
        _FLOWS[flow_id] = flow

    t = threading.Thread(target=_codex_poll_worker, args=(flow_id,), daemon=True)
    t.start()

    return {
        "ok": True,
        "flow_id": flow_id,
        "provider": "openai-codex",
        "status": "pending",
        "verification_uri": CODEX_VERIFICATION_URI,
        "user_code": user_code,
        "poll_interval_seconds": flow["interval"],
        "instructions": f"1. Open {CODEX_VERIFICATION_URI}\n2. Sign in with your ChatGPT Plus/Pro account\n3. Enter code: {user_code}",
    }


def _codex_poll_worker(flow_id: str) -> None:
    while True:
        with _FLOWS_LOCK:
            flow = _FLOWS.get(flow_id)
            if not flow or flow.get("status") != "pending":
                return
            if time.time() > flow["expires_at"]:
                flow["status"] = "expired"
                flow["error"] = "Device code expired. Click Connect again."
                return
            device_auth_id = flow["device_auth_id"]
            user_code = flow["user_code"]
            interval = flow["interval"]

        time.sleep(interval)
        try:
            poll_resp = _http_post(
                CODEX_DEVICE_TOKEN_URL,
                {"device_auth_id": device_auth_id, "user_code": user_code},
            )
            auth_code = poll_resp.get("authorization_code")
            code_verifier = poll_resp.get("code_verifier")
            if auth_code and code_verifier:
                token_data = _http_post(
                    CODEX_TOKEN_URL,
                    {
                        "grant_type": "authorization_code",
                        "code": auth_code,
                        "redirect_uri": CODEX_REDIRECT_URI,
                        "client_id": CODEX_CLIENT_ID,
                        "code_verifier": code_verifier,
                    },
                    form=True,
                )
                access_tok = str(token_data.get("access_token") or "")
                refresh_tok = str(token_data.get("refresh_token") or "")
                if access_tok:
                    db = SessionLocal()
                    try:
                        set_setting(db, "codex_access_token", access_tok, is_secret=True, category="oauth")
                        if refresh_tok:
                            set_setting(db, "codex_refresh_token", refresh_tok, is_secret=True, category="oauth")
                        set_setting(db, "ai_provider", "openai-codex", is_secret=False, category="ai")
                        set_setting(db, "ai_model", "gpt-5.3-codex", is_secret=False, category="ai")
                    finally:
                        db.close()
                    with _FLOWS_LOCK:
                        if flow_id in _FLOWS:
                            _FLOWS[flow_id]["status"] = "connected"
                    return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (403, 404):
                continue
            with _FLOWS_LOCK:
                if flow_id in _FLOWS:
                    _FLOWS[flow_id]["status"] = "error"
                    _FLOWS[flow_id]["error"] = f"OpenAI auth error (HTTP {exc.response.status_code})"
            return
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                continue
            with _FLOWS_LOCK:
                if flow_id in _FLOWS:
                    _FLOWS[flow_id]["status"] = "error"
                    _FLOWS[flow_id]["error"] = f"OpenAI auth error (HTTP {exc.code})"
            return
        except Exception:
            continue


# ── 2. Antigravity Google OAuth (PKCE) Flow ──────────────────────────────────

def start_antigravity_oauth_flow() -> dict[str, Any]:
    flow_id = secrets.token_urlsafe(16)
    client_id = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", ANTIGRAVITY_CLIENT_ID).strip()
    code_verifier = secrets.token_urlsafe(32)
    auth_url = ""
    if client_id:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        state = secrets.token_urlsafe(16)
        params = {
            "access_type": "offline",
            "client_id": client_id,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "consent",
            "redirect_uri": ANTIGRAVITY_REDIRECT_URI,
            "response_type": "code",
            "scope": ANTIGRAVITY_SCOPES,
            "state": state,
        }
        auth_url = f"{ANTIGRAVITY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    else:
        auth_url = "https://antigravity.google"

    with _FLOWS_LOCK:
        _FLOWS[flow_id] = {
            "flow_id": flow_id,
            "provider": "antigravity",
            "status": "pending",
            "code_verifier": code_verifier,
            "auth_url": auth_url,
            "has_client_id": bool(client_id),
            "expires_at": time.time() + 900,
        }

    return {
        "ok": True,
        "flow_id": flow_id,
        "provider": "antigravity",
        "status": "pending",
        "auth_url": auth_url,
        "instructions": (
            "Click 'Auto-Detect Local Sign-In' if Antigravity is signed in on this PC, "
            "or paste an Antigravity OAuth token / redirect code below."
        ),
    }


def exchange_antigravity_code(db: Session, flow_id: str, raw_code_or_url: str) -> dict[str, Any]:
    with _FLOWS_LOCK:
        flow = _FLOWS.get(flow_id)
    if not flow:
        return {"ok": False, "error": "OAuth session expired. Click Sign In again."}

    raw = raw_code_or_url.strip()
    if not raw:
        return {"ok": False, "error": "Please paste an authorization URL, code, or access token."}

    access_tok = ""
    refresh_tok = ""
    token_data: dict[str, Any] = {}

    # Support direct paste of an existing OAuth access token or token JSON
    if raw.startswith("{"):
        try:
            parsed_json = json.loads(raw)
            tok_obj = parsed_json.get("token", parsed_json)
            access_tok = str(tok_obj.get("access_token") or "")
            refresh_tok = str(tok_obj.get("refresh_token") or "")
        except Exception:
            pass
    elif raw.startswith("ya29.") or not flow.get("has_client_id"):
        access_tok = raw

    if not access_tok:
        code = raw
        if "code=" in code:
            parsed = urllib.parse.urlparse(code)
            qs = urllib.parse.parse_qs(parsed.query)
            code = (qs.get("code") or [""])[0]
        if not code:
            return {"ok": False, "error": "Could not find authorization code in pasted text."}

        client_id = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", ANTIGRAVITY_CLIENT_ID).strip()
        client_secret = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", ANTIGRAVITY_CLIENT_SECRET).strip()
        try:
            token_data = _http_post(
                ANTIGRAVITY_TOKEN_URL,
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "code_verifier": flow["code_verifier"],
                    "grant_type": "authorization_code",
                    "redirect_uri": ANTIGRAVITY_REDIRECT_URI,
                },
                form=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"Token exchange failed: {exc}"}

        access_tok = str(token_data.get("access_token") or "")
        refresh_tok = str(token_data.get("refresh_token") or "")
        if not access_tok:
            return {"ok": False, "error": "No access token returned by Google."}

    # Persist both in encrypted DB and in standard ~/.gemini/antigravity-cli path for `agy`
    set_setting(db, "antigravity_access_token", access_tok, is_secret=True, category="oauth")
    if refresh_tok:
        set_setting(db, "antigravity_refresh_token", refresh_tok, is_secret=True, category="oauth")
    set_setting(db, "ai_provider", "antigravity", is_secret=False, category="ai")
    set_setting(db, "ai_model", "gemini-3.8-flash-medium", is_secret=False, category="ai")

    try:
        tok_path = Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
        tok_path.parent.mkdir(parents=True, exist_ok=True)
        expires_in = int(token_data.get("expires_in") or 3599)
        expiry_iso = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")
        tok_path.write_text(
            json.dumps(
                {
                    "token": {
                        "access_token": access_tok,
                        "token_type": "Bearer",
                        "refresh_token": refresh_tok,
                        "expiry": expiry_iso,
                        "expires_in": expires_in,
                    },
                    "auth_method": "consumer",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    with _FLOWS_LOCK:
        if flow_id in _FLOWS:
            _FLOWS[flow_id]["status"] = "connected"

    return {"ok": True, "provider": "antigravity", "status": "connected"}


def poll_oauth_status(flow_id: str) -> dict[str, Any]:
    with _FLOWS_LOCK:
        flow = _FLOWS.get(flow_id)
    if not flow:
        return {"ok": False, "status": "not_found"}
    return {
        "ok": True,
        "flow_id": flow_id,
        "provider": flow["provider"],
        "status": flow["status"],
        "error": flow.get("error", ""),
    }


# ── 3. Auto-Detect Local CLI Subscription Sign-Ins (Claude, Codex, Antigravity)

def import_local_subscription_tokens(db: Session) -> dict[str, Any]:
    """Detect existing local Claude Code, Codex CLI, or Antigravity sign-ins on this PC."""
    imported: list[str] = []

    # Claude Code credentials (~/.claude/.credentials.json)
    claude_cred = Path.home() / ".claude" / ".credentials.json"
    if claude_cred.exists():
        try:
            data = json.loads(claude_cred.read_text(encoding="utf-8"))
            tok = (data.get("claudeAiOauth") or {}).get("accessToken") or data.get("accessToken") or ""
            if tok:
                set_setting(db, "claude_oauth_token", tok, is_secret=True, category="oauth")
                imported.append("claude-sub")
        except Exception:
            pass

    # Codex CLI (~/.codex/auth.json)
    codex_cred = Path.home() / ".codex" / "auth.json"
    if codex_cred.exists():
        try:
            data = json.loads(codex_cred.read_text(encoding="utf-8"))
            tokens = data.get("tokens") or data
            tok = tokens.get("access_token") or ""
            ref = tokens.get("refresh_token") or ""
            if tok:
                set_setting(db, "codex_access_token", tok, is_secret=True, category="oauth")
                if ref:
                    set_setting(db, "codex_refresh_token", ref, is_secret=True, category="oauth")
                imported.append("openai-codex")
        except Exception:
            pass

    # Antigravity CLI (~/.gemini/antigravity-cli/antigravity-oauth-token, ~/.gemini/oauth_creds.json, or local agy binary)
    from app.services.hermes_engine import find_antigravity_bin

    agy_imported = False
    for agy_cred in (
        Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token",
        Path.home() / ".gemini" / "oauth_creds.json",
    ):
        if agy_cred.exists():
            try:
                data = json.loads(agy_cred.read_text(encoding="utf-8"))
                tok_obj = data.get("token") if isinstance(data.get("token"), dict) else data
                tok = (tok_obj.get("access_token") or "").strip()
                ref = (tok_obj.get("refresh_token") or "").strip()
                if tok:
                    set_setting(db, "antigravity_access_token", tok, is_secret=True, category="oauth")
                    if ref:
                        set_setting(db, "antigravity_refresh_token", ref, is_secret=True, category="oauth")
                    imported.append("antigravity")
                    agy_imported = True
                    break
            except Exception:
                pass
    if not agy_imported and find_antigravity_bin():
        imported.append("antigravity")

    return {"imported": imported, "count": len(imported)}


# ── 4. Live Auto-Discovery & Flagship-First Grouped Model Picker ─────────────

_MODEL_CACHE: dict[str, tuple[float, list[str]]] = {}
_MODEL_CACHE_TTL_SEC = 300.0


def clear_model_catalog_cache() -> None:
    _MODEL_CACHE.clear()


def _cache_get(key: str) -> list[str] | None:
    entry = _MODEL_CACHE.get(key)
    if entry and (time.time() - entry[0]) < _MODEL_CACHE_TTL_SEC:
        return list(entry[1])
    return None


def _cache_set(key: str, models: list[str]) -> list[str]:
    _MODEL_CACHE[key] = (time.time(), list(models))
    return list(models)


def _rank_models_flagship_first(models: list[str], priority_prefixes: list[str]) -> list[str]:
    """Deduplicate and sort models with flagship models strictly on top."""
    seen: set[str] = set()
    uniq: list[str] = []
    for m in models:
        clean = (m or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            uniq.append(clean)

    def score(m: str) -> tuple[int, str]:
        low = m.lower()
        for idx, pref in enumerate(priority_prefixes):
            if low == pref or low.startswith(pref):
                return (idx, low)
        return (len(priority_prefixes) + 10, low)

    return sorted(uniq, key=score)


def _discover_agy_models(agy_bin: str) -> list[str]:
    cached = _cache_get("agy")
    if cached is not None:
        return cached
    import subprocess

    fallback = [
        "gemini-4-neon-high",
        "gemini-4-neon-xhigh",
        "gemini-4-neon-medium",
        "gemini-4-hydrogen-high",
        "gemini-4-carbon-high",
        "gemini-4-argon-high",
        "claude-opus-5-5-high",
        "claude-sonnet-5-5-high",
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
        "gpt-oss-120b-medium",
    ]
    if not agy_bin:
        return fallback
    try:
        kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 8, "encoding": "utf-8", "errors": "replace"}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run([agy_bin, "models"], **kwargs)
        found: list[str] = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line or line.lower().startswith("fetching"):
                continue
            mid = line.split("\t")[0].split()[0].strip()
            if mid and any(k in mid.lower() for k in ("gemini", "claude", "gpt", "orchestrator", "neon", "astra", "sol")):
                found.append(mid)
        if found:
            ranked = _rank_models_flagship_first(
                found,
                [
                    "gemini-4-neon-xhigh",
                    "gemini-4-neon-high",
                    "gemini-4-neon-medium",
                    "gemini-4-hydrogen-xhigh",
                    "gemini-4-hydrogen-high",
                    "gemini-4-carbon-high",
                    "gemini-4-argon-high",
                    "claude-opus-5-5-high",
                    "claude-opus-5-5-medium",
                    "claude-sonnet-5-5-high",
                    "claude-sonnet-5-5-medium",
                    "gemini-pro-orchestrator-neon",
                    "gemini-3.8-flash-high",
                    "gemini-3.8-flash-medium",
                    "gpt-oss-120b-medium",
                ],
            )
            return _cache_set("agy", ranked[:18])
    except Exception:
        pass
    return _cache_set("agy", fallback)


def _discover_gemini_models(api_key: str) -> list[str]:
    fallback = [
        "gemini-4-neon",
        "gemini-4-hydrogen",
        "gemini-4-carbon",
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-flash-latest",
    ]
    if not api_key:
        return fallback
    ckey = f"gemini:{hashlib.sha256(api_key.encode()).hexdigest()[:8]}"
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    try:
        with httpx.Client(timeout=4.0) as client:
            r = client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}")
            if r.status_code == 200:
                skip_tokens = ("tts", "image", "lyria", "robotics", "transcribe", "nano-banana", "computer-use", "deep-research")
                found: list[str] = []
                for m in r.json().get("models", []):
                    methods = m.get("supportedGenerationMethods") or []
                    if "generateContent" not in methods:
                        continue
                    mid = str(m.get("name", "")).replace("models/", "").strip()
                    low = mid.lower()
                    if not mid or any(st in low for st in skip_tokens):
                        continue
                    if low.startswith(("gemini-", "antigravity-")):
                        found.append(mid)
                if found:
                    ranked = _rank_models_flagship_first(
                        found,
                        [
                            "gemini-4-neon",
                            "gemini-4-hydrogen",
                            "gemini-4-carbon",
                            "gemini-4-argon",
                            "gemini-3.8-flash",
                            "gemini-3.7-flash",
                            "gemini-3.6-flash",
                            "gemini-3.5-flash",
                            "gemini-3.1-pro-preview",
                            "gemini-3.1-flash-lite",
                            "gemini-2.5-pro",
                            "gemini-pro-latest",
                            "gemini-flash-latest",
                            "gemini-2.5-flash",
                        ],
                    )
                    return _cache_set(ckey, ranked[:16])
    except Exception:
        pass
    return _cache_set(ckey, fallback)


def _discover_openai_models(api_key: str) -> list[str]:
    fallback = ["gpt-5.4", "gpt-5.3", "gpt-5.2", "gpt-5", "o3", "o4-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini"]
    if not api_key:
        return fallback
    ckey = f"openai:{hashlib.sha256(api_key.encode()).hexdigest()[:8]}"
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    try:
        with httpx.Client(timeout=4.0) as client:
            r = client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"})
            if r.status_code == 200:
                skip = ("audio", "realtime", "tts", "whisper", "dall-e", "embedding", "moderation", "transcribe", "image", "sora")
                found = [
                    str(m.get("id", "")).strip()
                    for m in r.json().get("data", [])
                    if str(m.get("id", "")).startswith(("gpt-5", "gpt-4", "o3", "o4", "o1"))
                    and not any(s in str(m.get("id", "")).lower() for s in skip)
                ]
                if found:
                    ranked = _rank_models_flagship_first(found, ["gpt-5.4", "gpt-5.3", "gpt-5.2", "gpt-5", "o3", "o4-mini", "gpt-4.1", "gpt-4o"])
                    return _cache_set(ckey, ranked[:14])
    except Exception:
        pass
    return _cache_set(ckey, fallback)


def _discover_openrouter_models(api_key: str) -> list[str]:
    fallback = [
        "google/gemini-4-neon",
        "openai/gpt-5.4",
        "anthropic/claude-opus-4.6",
        "anthropic/claude-sonnet-4.6",
        "x-ai/grok-4",
        "openai/o3",
        "google/gemini-3.1-pro-preview",
    ]
    if not api_key:
        return fallback
    ckey = f"openrouter:{hashlib.sha256(api_key.encode()).hexdigest()[:8]}"
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    try:
        with httpx.Client(timeout=4.0) as client:
            r = client.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {api_key}"})
            if r.status_code == 200:
                ids = [str(m.get("id", "")).strip() for m in r.json().get("data", []) if m.get("id")]
                wanted = [
                    m for m in ids
                    if any(
                        p in m.lower()
                        for p in ("gemini-4", "gemini-3", "gpt-5", "claude-opus-5", "claude-sonnet-5", "claude-opus-4", "claude-sonnet-4", "grok-4", "grok-3", "o3")
                    )
                ]
                if wanted:
                    ranked = _rank_models_flagship_first(
                        wanted,
                        ["google/gemini-4-neon", "openai/gpt-5.4", "anthropic/claude-opus-5", "anthropic/claude-opus-4", "anthropic/claude-sonnet-5", "anthropic/claude-sonnet-4", "x-ai/grok-4", "openai/o3"],
                    )
                    return _cache_set(ckey, ranked[:14])
    except Exception:
        pass
    return _cache_set(ckey, fallback)


def get_grouped_model_catalog(db: Session) -> dict[str, Any]:
    from app.services.hermes_engine import find_antigravity_bin

    active_provider = get_setting(db, "ai_provider", "auto")
    active_model = get_setting(db, "ai_model", "auto-flagship")

    agy_bin = find_antigravity_bin()
    codex_connected = bool(get_setting(db, "codex_access_token", ""))
    claude_sub_connected = bool(get_setting(db, "claude_oauth_token", "")) or bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN"))
    agy_connected = (
        bool(get_setting(db, "antigravity_access_token", ""))
        or (Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").exists()
        or (Path.home() / ".gemini" / "oauth_creds.json").exists()
        or bool(agy_bin)
    )

    ollama_url = get_setting(db, "ollama_base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_models: list[str] = []
    try:
        with httpx.Client(timeout=1.5) as client:
            r = client.get(f"{ollama_url.rstrip('/')}/api/tags")
            if r.status_code == 200:
                ollama_models = [m["name"] for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        pass

    openai_key = get_setting(db, "openai_api_key", os.getenv("OPENAI_API_KEY", ""))
    anth_key = get_setting(db, "anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", ""))
    gem_key = get_setting(db, "gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    xai_key = get_setting(db, "xai_api_key", os.getenv("XAI_API_KEY", ""))
    or_key = get_setting(db, "openrouter_api_key", os.getenv("OPENROUTER_API_KEY", ""))
    qwen_key = get_setting(db, "qwen_api_key", "")
    minimax_key = get_setting(db, "minimax_api_key", "")

    agy_models = _discover_agy_models(agy_bin or "")
    gemini_models = _discover_gemini_models(gem_key)
    openai_models = _discover_openai_models(openai_key)
    openrouter_models = _discover_openrouter_models(or_key)

    groups = [
        {
            "group": "Auto Picker & Subscriptions (Flagships on Top)",
            "items": [
                {
                    "provider": "auto",
                    "label": "★ Auto (Best Flagship)",
                    "connected": True,
                    "auth_kind": "builtin",
                    "models": ["auto-flagship"],
                },
                {
                    "provider": "antigravity",
                    "label": "Antigravity (Live Catalog)",
                    "connected": agy_connected,
                    "auth_kind": "google_oauth",
                    "models": agy_models,
                },
                {
                    "provider": "openai-codex",
                    "label": "ChatGPT / Codex Subscription",
                    "connected": codex_connected,
                    "auth_kind": "oauth_device",
                    "models": ["gpt-5.4", "gpt-5.3-codex", "gpt-5.2", "gpt-5", "o3", "o4-mini"],
                },
                {
                    "provider": "claude-sub",
                    "label": "Claude Pro / Max Subscription",
                    "connected": claude_sub_connected,
                    "auth_kind": "claude_token",
                    "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-6", "claude-sonnet-4-6", "claude-opus-4-5", "claude-sonnet-4-5"],
                },
            ],
        },
        {
            "group": "Cloud API Keys (Auto-Discovered Flagships)",
            "items": [
                {"provider": "gemini", "label": "Google Gemini API", "connected": bool(gem_key), "auth_kind": "api_key", "models": gemini_models},
                {"provider": "openai", "label": "OpenAI API", "connected": bool(openai_key), "auth_kind": "api_key", "models": openai_models},
                {
                    "provider": "anthropic",
                    "label": "Anthropic Claude API",
                    "connected": bool(anth_key),
                    "auth_kind": "api_key",
                    "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
                },
                {"provider": "xai_grok", "label": "xAI Grok (SuperGrok / API)", "connected": bool(xai_key), "auth_kind": "api_key", "models": ["grok-4", "grok-3", "grok-3-mini", "grok-2-latest"]},
                {"provider": "openrouter", "label": "OpenRouter (All Flagships)", "connected": bool(or_key), "auth_kind": "api_key", "models": openrouter_models},
                {"provider": "qwen", "label": "Qwen (DashScope / OAuth)", "connected": bool(qwen_key), "auth_kind": "api_key", "models": ["qwen3-max", "qwen-max", "qwen-plus"]},
                {"provider": "minimax", "label": "MiniMax", "connected": bool(minimax_key), "auth_kind": "api_key", "models": ["MiniMax-M1", "MiniMax-Text-01"]},
            ],
        },
        {
            "group": "Local Private (Free on This PC)",
            "items": [
                {
                    "provider": "ollama",
                    "label": "Local Ollama",
                    "connected": len(ollama_models) > 0,
                    "auth_kind": "local_url",
                    "models": ollama_models or ["llama3.3", "qwen2.5:14b", "llama3.2", "mistral"],
                },
            ],
        },
    ]

    # Preserve custom model IDs if the user typed one manually, while normalizing legacy 'consular-auto'
    all_items = [it for grp in groups for it in grp["items"]]
    active_item = next((it for it in all_items if it["provider"] == active_provider), None)
    if active_item and active_item.get("models"):
        if not active_model or active_model == "consular-auto":
            active_model = active_item["models"][0]
        elif active_model not in active_item["models"]:
            # Keep user's custom model ID visible at the top of that provider's list
            active_item["models"] = [active_model] + active_item["models"]
    elif not active_model or active_model == "consular-auto":
        active_model = "auto-flagship"

    return {
        "active_provider": active_provider,
        "active_model": active_model,
        "agy_cli_installed": bool(agy_bin),
        "claude_cli_installed": bool(shutil.which("claude")),
        "groups": groups,
    }
