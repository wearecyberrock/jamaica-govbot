"""Hermes-Powered Multi-Provider AI Engine & Autonomous Tool-Calling Loop ("Hands").

Supports:
1. ChatGPT / OpenAI Codex Subscription OAuth (SSE streaming + chatgpt-account-id JWT claim + auto-refresh)
2. Claude Pro / Max Subscription OAuth Token
3. Antigravity (`agy.exe` / `agy.cmd` / `agy` CLI on Windows/macOS/Linux + Google OAuth endpoint fallback)
4. Local Ollama (configurable base URL & model — 100% private PII mode)
5. Cloud API Keys via HTTP (OpenAI, Anthropic, Google Gemini, xAI Grok, OpenRouter, Qwen, MiniMax)
6. Transparent error surfacing + conversational setup prompt when no AI provider is connected
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models import (
    BrandingConfig,
    ChatMessage,
    ClientCase,
    GeneratedAsset,
    GovSource,
    OfficialDocument,
    PipelineJournal,
)
from app.services.connectors import get_setting, set_setting
from app.services.doc_generator import (
    generate_ds160_worksheet_pdf,
    generate_kingston_checklist_pdf,
    generate_support_letter_docx,
    generate_visual_roadmap_png,
)
from app.services.obsidian import sync_client_to_obsidian
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions
from app.services.scraper import scrape_single_source

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_USER_AGENT = "codex_cli_rs/0.0.0 (Jahtaria Desktop)"

COMPLIANCE_SYSTEM_PROMPT = """You are the Jahtaria Visa Intelligence AI Specialist for Jamaican applicants preparing for U.S. Visa interviews at the U.S. Embassy in Kingston (142 Old Hope Road, Kingston).

CONVERSATIONAL BEHAVIOR:
- Respond naturally, warmly, and directly to greetings, follow-ups, and general questions, using the full conversation history to remember context.
- When the user asks about U.S. visas, Kingston Embassy rules, DS-160, PICA Jamaican passports, RGD civil documents, or client cases, ground your answer in the Verified Official Reference Knowledge and cite the relevant official URL(s).
- Do not dump unsolicited boilerplate checklists when the user simply says hello or asks a general question.

STRICT COMPLIANCE RULES (NON-NEGOTIABLE):
1. Assist ONLY with truthful application verification, factual document readiness, and accurate, spontaneous interview answers.
2. NEVER coach concealment, NEVER invent ties, NEVER advise omitting U.S. relatives or prior refusals, and NEVER guarantee visa approval.
3. Clearly distinguish Gross vs. Net JMD monthly salary (DS-160 requires accurate monthly gross; net take-home is a normal distinction, not automatically false).
4. Always cite official verified sources (jm.usembassy.gov, travel.state.gov, ais.usvisa-info.com/en-jm/niv, pica.gov.jm) when referencing fees, passport rules, the April 1, 2025 DS-160 AA-barcode matching rule, or the 92% RGD civil document photocopy rule.
5. Keep answers practical, warm, clear, and concise."""


def find_antigravity_bin() -> str | None:
    """Locate the Antigravity CLI binary across Windows (.exe/.cmd/.bat), macOS, and Linux."""
    names = ("agy.exe", "agy.cmd", "agy.bat", "agy") if os.name == "nt" else ("agy",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    candidates: list[Path] = []
    if os.name == "nt":
        local_appdata = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        roaming_appdata = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        program_files = Path(os.getenv("ProgramFiles", r"C:\Program Files"))
        candidates.extend(
            [
                local_appdata / "agy" / "bin" / "agy.exe",
                local_appdata / "agy" / "bin" / "agy.cmd",
                local_appdata / "Programs" / "agy" / "agy.exe",
                local_appdata / "Programs" / "antigravity" / "bin" / "agy.exe",
                roaming_appdata / "npm" / "agy.cmd",
                roaming_appdata / "npm" / "agy.exe",
                Path.home() / ".gemini" / "bin" / "agy.exe",
                Path.home() / ".gemini" / "antigravity" / "bin" / "agy.exe",
                Path.home() / ".gemini" / "antigravity-cli" / "bin" / "agy.exe",
                Path.home() / ".local" / "bin" / "agy.exe",
                program_files / "Antigravity" / "bin" / "agy.exe",
            ]
        )
    else:
        candidates.extend(
            [
                Path("/usr/local/bin/agy"),
                Path.home() / ".local" / "bin" / "agy",
                Path("/opt/antigravity/bin/agy"),
                Path.home() / ".gemini" / "bin" / "agy",
                Path.home() / ".gemini" / "antigravity" / "bin" / "agy",
            ]
        )

    for cand in candidates:
        if cand.is_file() and (os.name == "nt" or os.access(cand, os.X_OK)):
            return str(cand)
    return None


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Safely decode the payload segment of a JWT without external verification."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        pad = "=" * (-len(parts[1]) % 4)
        raw = base64.urlsafe_b64decode(parts[1] + pad)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_chatgpt_account_id(token: str) -> str | None:
    """Extract the chatgpt-account-id claim required by chatgpt.com/backend-api/codex/responses."""
    payload = _decode_jwt_payload(token)
    auth_claim = payload.get("https://api.openai.com/auth")
    if isinstance(auth_claim, dict) and auth_claim.get("chatgpt_account_id"):
        return str(auth_claim["chatgpt_account_id"])
    if payload.get("chatgpt_account_id"):
        return str(payload["chatgpt_account_id"])
    return None


def _is_jwt_expired(token: str, leeway_seconds: int = 60) -> bool:
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return False
    return time.time() >= (float(exp) - leeway_seconds)


def _refresh_codex_access_token(db: Session) -> str | None:
    """Refresh an expired ChatGPT Codex OAuth access token using the stored refresh token."""
    refresh_tok = get_setting(db, "codex_refresh_token", "").strip()
    if not refresh_tok:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                CODEX_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                data={
                    "grant_type": "refresh_token",
                    "client_id": CODEX_CLIENT_ID,
                    "refresh_token": refresh_tok,
                },
            )
            if r.status_code == 200:
                data = r.json()
                new_access = str(data.get("access_token") or "").strip()
                new_refresh = str(data.get("refresh_token") or "").strip()
                if new_access:
                    set_setting(db, "codex_access_token", new_access, is_secret=True, category="oauth")
                    if new_refresh:
                        set_setting(db, "codex_refresh_token", new_refresh, is_secret=True, category="oauth")
                    return new_access
    except Exception:
        pass
    return None


def _extract_error_detail(raw_text: str) -> str:
    """Extract a concise human-readable error message from a JSON or plain-text HTTP body."""
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return "Empty error response"
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("detail") or err.get("code")
                if msg:
                    return str(msg)[:300]
            elif isinstance(err, str) and err:
                return err[:300]
            if parsed.get("detail"):
                return str(parsed["detail"])[:300]
            if parsed.get("message"):
                return str(parsed["message"])[:300]
    except Exception:
        pass
    return re.sub(r"\s+", " ", cleaned)[:300]


def _extract_output_text_from_response_obj(resp_obj: dict[str, Any]) -> str:
    """Extract assistant text from a Responses API `response` object."""
    if not isinstance(resp_obj, dict):
        return ""
    direct = resp_obj.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in resp_obj.get("output") or []:
        if not isinstance(item, dict):
            continue
        for c in item.get("content") or []:
            if isinstance(c, dict) and c.get("text"):
                parts.append(str(c["text"]))
    return "".join(parts).strip()


def _call_openai_codex_sse(
    token: str,
    codex_model: str,
    system_prompt: str,
    history: list[dict[str, str]],
    user_prompt: str,
) -> tuple[str | None, int | None, str | None]:
    """Call ChatGPT Codex Responses API with SSE streaming and chatgpt-account-id header."""
    account_id = _extract_chatgpt_account_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": CODEX_USER_AGENT,
        "originator": "codex_cli_rs",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id

    input_items: list[dict[str, Any]] = []
    for turn in history:
        role = turn["role"]
        content_type = "output_text" if role == "assistant" else "input_text"
        input_items.append({"role": role, "content": [{"type": content_type, "text": turn["content"]}]})
    input_items.append({"role": "user", "content": [{"type": "input_text", "text": user_prompt}]})

    payload = {
        "model": codex_model,
        "instructions": system_prompt,
        "input": input_items,
        "store": False,
        "stream": True,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", CODEX_RESPONSES_URL, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = r.read().decode("utf-8", errors="replace")
                    return None, r.status_code, _extract_error_detail(body)

                ctype = (r.headers.get("content-type") or "").lower()
                if "application/json" in ctype and "event-stream" not in ctype:
                    raw = r.read().decode("utf-8", errors="replace")
                    try:
                        data = json.loads(raw)
                        txt = _extract_output_text_from_response_obj(data)
                        if txt:
                            return txt, 200, None
                    except Exception:
                        pass
                    return None, 200, "Codex returned JSON without output text."

                deltas: list[str] = []
                done_text = ""
                completed_text = ""
                stream_error = ""

                for line in r.iter_lines():
                    if not line:
                        continue
                    s = line.strip()
                    if not s.startswith("data:"):
                        continue
                    data_str = s[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        ev = json.loads(data_str)
                    except Exception:
                        continue
                    if not isinstance(ev, dict):
                        continue

                    ev_type = str(ev.get("type") or "")
                    if ev_type == "response.output_text.delta":
                        delta = ev.get("delta")
                        if isinstance(delta, str):
                            deltas.append(delta)
                    elif ev_type == "response.output_text.done":
                        txt = ev.get("text")
                        if isinstance(txt, str) and txt.strip():
                            done_text = txt.strip()
                    elif ev_type == "response.completed":
                        completed_text = _extract_output_text_from_response_obj(ev.get("response") or {})
                    elif ev_type in ("response.failed", "error"):
                        err_obj = ev.get("error") or (ev.get("response") or {}).get("error") or ev
                        stream_error = _extract_error_detail(json.dumps(err_obj))

                final_txt = "".join(deltas).strip() or done_text or completed_text
                if final_txt:
                    return final_txt, 200, None
                if stream_error:
                    return None, 200, stream_error
                return None, 200, "Codex SSE stream completed without output text."
    except Exception as exc:
        return None, None, str(exc)[:300]


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Sanitize conversation history into clean user/assistant turns."""
    if not history:
        return []
    out: list[dict[str, str]] = []
    for item in history:
        role = str(item.get("role") or item.get("sender") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        out.append({"role": role, "content": content})
    return out


def _build_anthropic_messages(history: list[dict[str, str]], user_prompt: str) -> list[dict[str, str]]:
    """Build strictly alternating user/assistant messages starting with user for Anthropic APIs."""
    msgs: list[dict[str, str]] = []
    for turn in history:
        if not msgs and turn["role"] != "user":
            continue
        if msgs and msgs[-1]["role"] == turn["role"]:
            msgs[-1]["content"] = f"{msgs[-1]['content']}\n\n{turn['content']}"
        else:
            msgs.append({"role": turn["role"], "content": turn["content"]})
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] = f"{msgs[-1]['content']}\n\n{user_prompt}"
    else:
        msgs.append({"role": "user", "content": user_prompt})
    return msgs


def _build_gemini_contents(history: list[dict[str, str]], user_prompt: str) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for turn in history:
        g_role = "model" if turn["role"] == "assistant" else "user"
        contents.append({"role": g_role, "parts": [{"text": turn["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_prompt}]})
    return contents


def _get_antigravity_oauth_token(db: Session) -> str:
    """Read Antigravity OAuth token from encrypted DB or local ~/.gemini/antigravity-cli token file."""
    tok = get_setting(db, "antigravity_access_token", "").strip()
    if tok:
        return tok
    tok_path = Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    if tok_path.is_file():
        try:
            data = json.loads(tok_path.read_text(encoding="utf-8"))
            return str((data.get("token") or data).get("access_token") or "").strip()
        except Exception:
            pass
    gem_oauth = Path.home() / ".gemini" / "oauth_creds.json"
    if gem_oauth.is_file():
        try:
            data = json.loads(gem_oauth.read_text(encoding="utf-8"))
            return str(data.get("access_token") or "").strip()
        except Exception:
            pass
    return ""


def load_conversation_history(
    db: Session,
    session_id: str | None,
    max_turns: int = 10,
    exclude_last_user_msg: str | None = None,
) -> list[dict[str, str]]:
    """Load the last `max_turns` user/assistant exchanges (up to 2*max_turns messages) from ChatMessage."""
    if not session_id:
        return []
    limit = max(2, max_turns * 2 + 2)
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.sender.in_(("user", "assistant")))
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    turns = [{"role": r.sender, "content": (r.content or "").strip()} for r in rows if (r.content or "").strip()]
    if exclude_last_user_msg and turns and turns[-1]["role"] == "user" and turns[-1]["content"] == exclude_last_user_msg.strip():
        turns.pop()
    return turns[-(max_turns * 2) :]


def detect_available_providers(db: Session) -> dict[str, Any]:
    agy_bin = find_antigravity_bin()
    claude_cli = shutil.which("claude")
    codex_cli = shutil.which("codex")
    ollama_url = get_setting(db, "ollama_base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_models: list[str] = []
    ollama_ok = False
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{ollama_url.rstrip('/')}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                ollama_models = [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        pass

    return {
        "active_provider": get_setting(db, "ai_provider", "auto"),
        "active_model": get_setting(db, "ai_model", "gpt-4o-mini"),
        "subscriptions": {
            "antigravity_agy": {"installed": bool(agy_bin), "binary": agy_bin or "", "models": ["gemini-3.8-flash-medium", "claude-sonnet-5-5-medium", "gemini-4-argon-high"]},
            "claude_cli": {"installed": bool(claude_cli), "binary": claude_cli or ""},
            "codex_chatgpt_cli": {"installed": bool(codex_cli), "binary": codex_cli or ""},
        },
        "ollama": {"reachable": ollama_ok, "base_url": ollama_url, "models": ollama_models},
        "api_keys": {
            "openai": bool(get_setting(db, "openai_api_key", os.getenv("OPENAI_API_KEY", ""))),
            "anthropic": bool(get_setting(db, "anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", ""))),
            "gemini": bool(get_setting(db, "gemini_api_key", os.getenv("GEMINI_API_KEY", ""))),
            "xai_grok": bool(get_setting(db, "xai_api_key", os.getenv("XAI_API_KEY", ""))),
            "openrouter": bool(get_setting(db, "openrouter_api_key", os.getenv("OPENROUTER_API_KEY", ""))),
        },
    }


def call_llm_detailed(
    db: Session,
    system_prompt: str,
    user_prompt: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Route completion across Subscriptions, Ollama, and Cloud API Keys with full history & transparent errors."""
    provider = get_setting(db, "ai_provider", "auto").strip().lower() or "auto"
    model = get_setting(db, "ai_model", "").strip()
    clean_history = _normalize_history(history)

    configured_providers: list[str] = []
    errors: list[str] = []
    last_failed_provider = ""

    # 1. ChatGPT / OpenAI Codex Subscription OAuth (SSE stream + chatgpt-account-id header)
    if provider in ("openai-codex", "auto"):
        codex_tok = get_setting(db, "codex_access_token", "").strip()
        if codex_tok:
            configured_providers.append("openai-codex")
            if _is_jwt_expired(codex_tok):
                refreshed = _refresh_codex_access_token(db)
                if refreshed:
                    codex_tok = refreshed
            codex_model = model if model and ("gpt-" in model or model.startswith("o")) else "gpt-5.3-codex"
            txt, status, err = _call_openai_codex_sse(codex_tok, codex_model, system_prompt, clean_history, user_prompt)
            if not txt and status == 401:
                refreshed = _refresh_codex_access_token(db)
                if refreshed:
                    txt, status, err = _call_openai_codex_sse(refreshed, codex_model, system_prompt, clean_history, user_prompt)
            if txt:
                return {"text": txt, "provider": f"chatgpt-codex:{codex_model}", "error": None, "configured_providers": configured_providers}
            last_failed_provider = "openai-codex"
            status_label = f"HTTP {status}" if status else "Network/Stream Error"
            errors.append(f"ChatGPT Codex ({codex_model}) [{status_label}]: {err}")
        elif provider == "openai-codex":
            return {
                "text": None,
                "provider": "openai-codex:unconfigured",
                "error": "ChatGPT / Codex is selected, but no OAuth session token is saved. Click Sign In with ChatGPT in Settings.",
                "configured_providers": [],
            }

    # 2. Claude Pro / Max Subscription OAuth Token
    if provider in ("claude-sub", "auto"):
        claude_tok = get_setting(db, "claude_oauth_token", os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "")).strip()
        if claude_tok:
            configured_providers.append("claude-sub")
            c_model = model if model.startswith("claude") else "claude-sonnet-4-5"
            try:
                with httpx.Client(timeout=40.0) as client:
                    r = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Authorization": f"Bearer {claude_tok}",
                            "anthropic-version": "2023-06-01",
                            "anthropic-beta": "oauth-2025-04-20",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": c_model,
                            "max_tokens": 1200,
                            "system": system_prompt,
                            "messages": _build_anthropic_messages(clean_history, user_prompt),
                        },
                    )
                    if r.status_code == 200:
                        blocks = r.json().get("content", [])
                        txt = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
                        if txt:
                            return {"text": txt, "provider": f"claude-subscription:{c_model}", "error": None, "configured_providers": configured_providers}
                        last_failed_provider = "claude-sub"
                        errors.append(f"Claude Subscription ({c_model}) [HTTP 200]: Empty response content.")
                    else:
                        last_failed_provider = "claude-sub"
                        errors.append(f"Claude Subscription ({c_model}) [HTTP {r.status_code}]: {_extract_error_detail(r.text)}")
            except Exception as exc:
                last_failed_provider = "claude-sub"
                errors.append(f"Claude Subscription ({c_model}) [Connection Error]: {str(exc)[:300]}")
        elif provider == "claude-sub":
            return {
                "text": None,
                "provider": "claude-sub:unconfigured",
                "error": "Claude Pro / Max is selected, but no Claude OAuth token is saved. Paste your token or click Auto-Detect in Settings.",
                "configured_providers": [],
            }

    # 3. Antigravity CLI (Windows agy.exe/agy.cmd + Unix) or Google OAuth Token Endpoint
    agy_tok = _get_antigravity_oauth_token(db)
    agy_bin = find_antigravity_bin()
    if provider == "antigravity" or (provider == "auto" and bool(agy_tok)):
        if agy_bin or agy_tok:
            configured_providers.append("antigravity")
        agy_errors: list[str] = []

        # 3a. Try local Antigravity CLI (`agy.exe` / `agy.cmd` / `agy`)
        if agy_bin:
            agy_model = model if (model and any(k in model for k in ("gemini-", "claude-", "gpt-oss", "orchestrator"))) else "gemini-3.8-flash-medium"
            history_block = ""
            if clean_history:
                transcript = "\n".join(
                    f"{'User' if t['role'] == 'user' else 'Assistant'}: {t['content']}"
                    for t in clean_history
                )
                history_block = f"\n\nConversation History:\n{transcript}"
            full_prompt = f"{system_prompt}{history_block}\n\nUser: {user_prompt}"
            cmd = [
                agy_bin,
                "-p",
                full_prompt,
                "--output-format",
                "text",
                "--disable-slash-commands",
                "--print-timeout",
                "60s",
                "--model",
                agy_model,
            ]
            run_kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 70, "encoding": "utf-8", "errors": "replace"}
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            try:
                res = subprocess.run(cmd, **run_kwargs)
                stdout_txt = (res.stdout or "").strip()
                stderr_txt = (res.stderr or "").strip()
                if res.returncode == 0 and stdout_txt and "AGY_ERROR:" not in stdout_txt:
                    return {"text": stdout_txt, "provider": f"antigravity:{agy_model}", "error": None, "configured_providers": configured_providers}
                err_msg = _extract_error_detail(stderr_txt or stdout_txt or f"Exit code {res.returncode}")
                agy_errors.append(f"Antigravity CLI ({agy_model}) [exit {res.returncode}]: {err_msg}")
            except Exception as exc:
                agy_errors.append(f"Antigravity CLI ({agy_model}) [Execution Error]: {str(exc)[:300]}")

        # 3b. Fallback: call Google Generative Language endpoint with stored Antigravity OAuth Bearer token
        if agy_tok:
            gem_model = model.replace("gemini/", "") if (model and model.startswith("gemini-")) else "gemini-3.1-flash-lite"
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent",
                        headers={"Authorization": f"Bearer {agy_tok}", "Content-Type": "application/json"},
                        json={
                            "systemInstruction": {"parts": [{"text": system_prompt}]},
                            "contents": _build_gemini_contents(clean_history, user_prompt),
                        },
                    )
                    if r.status_code == 200:
                        cands = r.json().get("candidates", [])
                        if cands:
                            txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
                            if txt:
                                return {"text": txt, "provider": f"antigravity-oauth:{gem_model}", "error": None, "configured_providers": configured_providers}
                        agy_errors.append(f"Antigravity OAuth ({gem_model}) [HTTP 200]: Empty response candidates.")
                    else:
                        agy_errors.append(f"Antigravity OAuth ({gem_model}) [HTTP {r.status_code}]: {_extract_error_detail(r.text)}")
            except Exception as exc:
                agy_errors.append(f"Antigravity OAuth ({gem_model}) [Connection Error]: {str(exc)[:300]}")

        if agy_errors:
            last_failed_provider = "antigravity"
            errors.extend(agy_errors)
        elif provider == "antigravity":
            return {
                "text": None,
                "provider": "antigravity:unconfigured",
                "error": "Antigravity is selected, but neither `agy.exe`/`agy.cmd` nor a Google OAuth token was found on this PC.",
                "configured_providers": [],
            }

    # 4. Local Ollama
    if provider in ("ollama", "auto"):
        ollama_url = get_setting(db, "ollama_base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        ollama_model = (model if (provider == "ollama" and model and model != "consular-auto") else "") or get_setting(
            db, "ollama_model", os.getenv("OLLAMA_MODEL", "llama3.2")
        )
        ollama_messages = [{"role": "system", "content": system_prompt}, *clean_history, {"role": "user", "content": user_prompt}]
        try:
            timeout_s = 30.0 if provider == "ollama" else 2.5
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(
                    f"{ollama_url}/api/chat",
                    json={"model": ollama_model, "stream": False, "messages": ollama_messages},
                )
                if r.status_code == 200:
                    configured_providers.append("ollama")
                    content = r.json().get("message", {}).get("content", "").strip()
                    if content:
                        return {"text": content, "provider": f"ollama:{ollama_model}", "error": None, "configured_providers": configured_providers}
                    last_failed_provider = "ollama"
                    errors.append(f"Ollama ({ollama_model}) [HTTP 200]: Empty message content.")
                elif provider == "ollama":
                    configured_providers.append("ollama")
                    last_failed_provider = "ollama"
                    errors.append(f"Ollama ({ollama_model}) [HTTP {r.status_code}]: {_extract_error_detail(r.text)}")
        except Exception as exc:
            if provider == "ollama":
                configured_providers.append("ollama")
                last_failed_provider = "ollama"
                errors.append(f"Ollama ({ollama_url}) [Unreachable]: {str(exc)[:300]}")

    # 5. Cloud API Keys (OpenAI, xAI Grok, OpenRouter, Qwen, MiniMax)
    openai_compat = [
        ("openai", "openai_api_key", "OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
        ("xai_grok", "xai_api_key", "XAI_API_KEY", "https://api.x.ai/v1/chat/completions", "grok-2-latest"),
        ("openrouter", "openrouter_api_key", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4o-mini"),
        ("qwen", "qwen_api_key", "QWEN_API_KEY", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus"),
        ("minimax", "minimax_api_key", "MINIMAX_API_KEY", "https://api.minimaxi.chat/v1/text/chatcompletion_v2", "MiniMax-Text-01"),
    ]
    for prov_id, setting_key, env_key, endpoint, fallback_model in openai_compat:
        if provider not in ("auto", prov_id):
            continue
        api_key = get_setting(db, setting_key, os.getenv(env_key, "")).strip()
        if not api_key:
            if provider == prov_id:
                return {
                    "text": None,
                    "provider": f"{prov_id}:unconfigured",
                    "error": f"Provider `{prov_id}` is selected, but no API key is configured. Add it in Settings.",
                    "configured_providers": [],
                }
            continue
        configured_providers.append(prov_id)
        use_model = model if (provider == prov_id and model and model != "consular-auto") else fallback_model
        msgs = [{"role": "system", "content": system_prompt}, *clean_history, {"role": "user", "content": user_prompt}]
        try:
            with httpx.Client(timeout=35.0) as client:
                r = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": use_model, "messages": msgs},
                )
                if r.status_code == 200:
                    txt = (r.json().get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                    if txt:
                        return {"text": txt, "provider": f"{prov_id}:{use_model}", "error": None, "configured_providers": configured_providers}
                    last_failed_provider = prov_id
                    errors.append(f"{prov_id} ({use_model}) [HTTP 200]: Empty completion text.")
                else:
                    last_failed_provider = prov_id
                    errors.append(f"{prov_id} ({use_model}) [HTTP {r.status_code}]: {_extract_error_detail(r.text)}")
        except Exception as exc:
            last_failed_provider = prov_id
            errors.append(f"{prov_id} ({use_model}) [Connection Error]: {str(exc)[:300]}")

    # 6. Anthropic Claude API Key
    if provider in ("auto", "anthropic"):
        anth_key = get_setting(db, "anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if anth_key:
            configured_providers.append("anthropic")
            anth_model = model if model.startswith("claude") else "claude-3-5-sonnet-latest"
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": anth_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": anth_model,
                            "max_tokens": 1200,
                            "system": system_prompt,
                            "messages": _build_anthropic_messages(clean_history, user_prompt),
                        },
                    )
                    if r.status_code == 200:
                        blocks = r.json().get("content", [])
                        txt = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
                        if txt:
                            return {"text": txt, "provider": f"anthropic:{anth_model}", "error": None, "configured_providers": configured_providers}
                        last_failed_provider = "anthropic"
                        errors.append(f"Anthropic ({anth_model}) [HTTP 200]: Empty response content.")
                    else:
                        last_failed_provider = "anthropic"
                        errors.append(f"Anthropic ({anth_model}) [HTTP {r.status_code}]: {_extract_error_detail(r.text)}")
            except Exception as exc:
                last_failed_provider = "anthropic"
                errors.append(f"Anthropic ({anth_model}) [Connection Error]: {str(exc)[:300]}")
        elif provider == "anthropic":
            return {
                "text": None,
                "provider": "anthropic:unconfigured",
                "error": "Anthropic API is selected, but no Anthropic API key is configured. Add it in Settings.",
                "configured_providers": [],
            }

    # 7. Google Gemini API Key
    if provider in ("auto", "gemini"):
        gem_key = get_setting(db, "gemini_api_key", os.getenv("GEMINI_API_KEY", "")).strip()
        if gem_key:
            configured_providers.append("gemini")
            gem_model = model.replace("gemini/", "") if "gemini" in model else "gemini-3.1-flash-lite"
            if gem_model in ("gemini-2.0-flash", "gemini-2.5-flash"):
                gem_model = "gemini-3.1-flash-lite"
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={gem_key}",
                        json={
                            "systemInstruction": {"parts": [{"text": system_prompt}]},
                            "contents": _build_gemini_contents(clean_history, user_prompt),
                        },
                    )
                    if r.status_code == 200:
                        cands = r.json().get("candidates", [])
                        if cands:
                            txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
                            if txt:
                                return {"text": txt, "provider": f"gemini:{gem_model}", "error": None, "configured_providers": configured_providers}
                        last_failed_provider = "gemini"
                        errors.append(f"Gemini ({gem_model}) [HTTP 200]: Empty response candidates.")
                    else:
                        last_failed_provider = "gemini"
                        errors.append(f"Gemini ({gem_model}) [HTTP {r.status_code}]: {_extract_error_detail(r.text)}")
            except Exception as exc:
                last_failed_provider = "gemini"
                errors.append(f"Gemini ({gem_model}) [Connection Error]: {str(exc)[:300]}")
        elif provider == "gemini":
            return {
                "text": None,
                "provider": "gemini:unconfigured",
                "error": "Google Gemini API is selected, but no Gemini API key is configured. Add it in Settings.",
                "configured_providers": [],
            }

    if errors:
        return {
            "text": None,
            "provider": f"error:{last_failed_provider or provider}",
            "error": " | ".join(errors),
            "configured_providers": configured_providers,
        }

    return {
        "text": None,
        "provider": "none-configured",
        "error": None,
        "configured_providers": [],
    }


def call_llm(
    db: Session,
    system_prompt: str,
    user_prompt: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str | None, str]:
    """Backward-compatible wrapper returning `(reply_text_or_none, provider_label)`."""
    res = call_llm_detailed(db, system_prompt, user_prompt, history=history)
    return res["text"], res["provider"]


def _gather_gov_context(db: Session, query: str) -> tuple[list[GovSource], bool]:
    """Return `(sources, had_keyword_match)` so general greetings aren't mislabeled as embassy queries."""
    q_tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    sources = db.query(GovSource).filter(GovSource.enabled == True).all()  # noqa: E712
    scored: list[tuple[int, GovSource]] = []
    for s in sources:
        blob = f"{s.name} {s.agency} {s.category} {s.verified_summary} {s.key_rules_json} {s.scraped_excerpt}".lower()
        hits = sum(2 if tok in s.name.lower() else (1 if tok in blob else 0) for tok in q_tokens)
        scored.append((hits, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    matched = [s for hits, s in scored[:4] if hits > 0]
    if matched:
        return matched, True
    return sources[:3], False


def answer_customer_question(
    db: Session,
    message: str,
    client: ClientCase | None = None,
    conversation_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Live AI Assistant grounded in verified U.S./Jamaica sources with full multi-turn memory and honest error reporting."""
    relevant_sources, had_match = _gather_gov_context(db, message)
    context_lines = [f"- [{s.name} ({s.agency})]({s.url}): {s.verified_summary}" for s in relevant_sources]

    case_ctx = ""
    if client:
        case_ctx = (
            f"\n\nActive Client Case Context:\n"
            f"- Case ID: {client.case_id} ({client.full_name or client.pseudonym}), Visa Class: {client.visa_class}\n"
            f"- Stage: {client.pipeline_stage}, Good Standing: {client.standing_score}%, "
            f"DS-160: {client.ds160_confirmation_id or 'Pending'}, Passport Expiry: {client.passport_expiry or 'Pending'}."
        )

    effective_history = (
        _normalize_history(history)
        if history is not None
        else load_conversation_history(db, conversation_id, max_turns=10, exclude_last_user_msg=message)
    )

    system_prompt = (
        f"{COMPLIANCE_SYSTEM_PROMPT}\n\n"
        f"Verified Official Reference Knowledge (use and cite when relevant to the user's question):\n"
        f"{chr(10).join(context_lines)}{case_ctx}"
    )

    llm_res = call_llm_detailed(db, system_prompt, message, history=effective_history)
    if llm_res["text"]:
        return {
            "reply": llm_res["text"],
            "provider_used": llm_res["provider"],
            "citations": [{"name": s.name, "agency": s.agency, "url": s.url} for s in relevant_sources] if had_match else [],
        }

    # Never silently swallow a connected provider's HTTP / CLI error!
    if llm_res["error"]:
        return {
            "reply": (
                f"**AI Provider Error (`{llm_res['provider']}`)**\n\n"
                f"Your connected AI subscription/provider failed to respond:\n\n"
                f"> `{llm_res['error']}`\n\n"
                "Open **Settings → AI Subscriptions & Setup** to reconnect your account, refresh your session, or switch to another model/provider, then try again."
            ),
            "provider_used": llm_res["provider"],
            "error": llm_res["error"],
            "citations": [],
        }

    # No AI provider connected yet: answer targeted visa rule queries accurately, or reply conversationally!
    ql = message.lower()
    bullets: list[str] = []
    if any(k in ql for k in ("fee", "cost", "price", "mrv", "185", "pay")):
        bullets.append("**U.S. Visa MRV Application Fees (2026):** B-1/B-2 Visitor, F-1 Student, and J-1 Exchange visas are **$185 USD** (non-refundable). Petition-based work visas (H-2B, L, O, P) are **$205 USD**. Payment & Kingston scheduling are handled at `ais.usvisa-info.com/en-jm/niv`.")
    if any(k in ql for k in ("barcode", "ds-160", "ds160", "ceac", "appointment")):
        bullets.append("**Critical Kingston Embassy Rule (Effective April 1, 2025):** Your printed Form DS-160 confirmation barcode (starting with `AA`) **must exactly match** the barcode entered in your `ais.usvisa-info.com/en-jm/niv` appointment profile — otherwise you will NOT be admitted to interview.")
    if any(k in ql for k in ("passport", "pica", "renew", "expire", "6 month")):
        bullets.append("**Jamaican Passport Requirements (PICA & Kingston Embassy):** Your Jamaican passport must be valid for **at least 6 months beyond your intended U.S. entry/stay**. If renewing an undamaged adult 10-year passport with no name/marital change, you can use the **PICA Simplified Adult Renewal Form 1** (available right in our Official Documents library!).")
    if any(k in ql for k in ("birth", "rgd", "marriage", "certificate", "92%", "copy")):
        bullets.append("**Jamaican RGD Civil Document 92% Rule:** Because Jamaican RGD birth/marriage certificates are slightly longer than standard U.S. Letter paper, photocopies MUST be reduced to **92% scale** so the top and bottom serial numbers are never cut off.")
    if any(k in ql for k in ("bring", "document", "checklist", "embassy", "phone", "old hope")):
        bullets.append("**What to Bring to U.S. Embassy Kingston (142 Old Hope Road):** Valid passport (+ expired passports with prior U.S. visas), printed DS-160 confirmation page (`AA...`), AIS appointment letter, one 2×2 inch white-background photo (no glasses), employment letter + 3 months pay slips, bank statements, and 92%-scaled RGD certificates. **No cellphones, smartwatches, or large bags** — there is no storage at the Embassy.")
    if any(k in ql for k in ("salary", "income", "gross", "net", "money", "bank")):
        bullets.append("**Gross vs. Net JMD Salary Tip:** Form DS-160 asks for your **monthly gross income** (before NIS/NHT/PAYE). If an officer asks what you earn, state clearly whether the amount is gross or net take-home so it matches your payslips truthfully.")
    if any(k in ql for k in ("refus", "denied", "214", "221", "5535", "admin")):
        bullets.append("**Prior Refusals & Administrative Processing:** Always disclose prior visa refusals truthfully on DS-160. Most tourist refusals fall under INA 214(b) (ties to Jamaica). Only submit Form **DS-5535** if specifically requested by the Consular Officer (email PDF to `KingstonNIV@state.gov` with subject `V11 – DS-5535 – [SURNAME, GIVEN NAME]`).")

    if bullets:
        if client:
            bullets.append(
                f"**Your Current Case ({client.case_id}):** Good Standing is **{client.standing_score}%** "
                f"(Stage: `{client.pipeline_stage.replace('_', ' ').title()}`)."
            )
        reply = (
            "\n\n".join(bullets)
            + "\n\n*Tip: Connect **ChatGPT / Codex**, **Claude Pro/Max**, **Antigravity**, **Local Ollama**, or an **API key** in **Settings → AI Subscriptions & Setup** to enable full live AI reasoning.*"
        )
        return {
            "reply": reply,
            "provider_used": "offline-visa-rules",
            "citations": [{"name": s.name, "agency": s.agency, "url": s.url} for s in relevant_sources],
        }

    # Conversational greeting / prompt when no AI provider is connected yet (NO canned 3-source Embassy dump!)
    case_note = (
        f" I have your case **{client.case_id}** loaded (Good Standing: **{client.standing_score}%**)."
        if client
        else ""
    )
    reply = (
        f"Hello! I'm your **Jahtaria Visa Intelligence** assistant.{case_note}\n\n"
        "Right now, no live AI model is connected yet — so I can only run built-in case actions, document tools, and quick Kingston Embassy rule lookups.\n\n"
        "To unlock full conversational AI with memory, open **Settings → AI Subscriptions & Setup** (or say *\"open settings\"*) and connect any of:\n"
        "- **ChatGPT / Codex Subscription** (1-click sign-in)\n"
        "- **Claude Pro / Max Subscription** (OAuth token or local auto-detect)\n"
        "- **Antigravity** (`agy` CLI / Google OAuth)\n"
        "- **Local Ollama** (free & private on this PC)\n"
        "- **Cloud API Key** (OpenAI, Anthropic, Gemini, xAI Grok, OpenRouter)"
    )
    return {
        "reply": reply,
        "provider_used": "none-configured",
        "citations": [],
    }


def run_staff_agent_loop(
    db: Session,
    instruction: str,
    case_id: str | None = None,
    actor: str = "Hermes Agent",
    conversation_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Autonomous Staff Hermes Tool-Calling & Self-Correction Loop ("Hands").

    Executes multi-step inspection, audit, scraping, self-correction, Obsidian sync,
    and draft asset generation — always pausing at the Human Approval Gate for final outputs.
    """
    tool_trace: list[dict[str, Any]] = []
    low = instruction.lower()

    # Resolve target case_id from parameter or instruction text (e.g. C001)
    if not case_id:
        m = re.search(r"\b(C\d{3})\b", instruction.upper())
        if m:
            case_id = m.group(1)

    client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first() if case_id else None
    branding = db.query(BrandingConfig).first()

    # Step 1: Inspect Client Profile if target case exists
    if client:
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "get_client_case",
                "status": "ok",
                "detail": f"Loaded {client.case_id} ({client.full_name or client.pseudonym}) — {client.visa_class}, stage={client.pipeline_stage}, standing={client.standing_score}%.",
            }
        )

    # Step 2: Check if instruction requests scraping / checking official sources
    if any(k in low for k in ("scrape", "refresh", "check official", "update rules", "pica", "embassy", "source")):
        target_sources, _ = _gather_gov_context(db, instruction)
        for src in target_sources[:2]:
            res = scrape_single_source(db, src, use_browser_fallback=False)
            tool_trace.append(
                {
                    "step": len(tool_trace) + 1,
                    "tool": "scrape_official_source",
                    "status": "ok",
                    "detail": f"Checked {src.name} ({src.url}) -> {res['status']} (changed={res['changed']}).",
                }
            )

    # Step 3: Check if instruction asks to search PDFs / forms
    if any(k in low for k in ("pdf", "form", "passport", "ds-5535", "ds-157", "blueprint")):
        docs = db.query(OfficialDocument).all()
        matched_docs = [d.title for d in docs if any(w in (d.title + d.description).lower() for w in low.split() if len(w) > 3)] or [d.title for d in docs[:5]]
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "search_official_pdfs",
                "status": "ok",
                "detail": f"Located {len(matched_docs)} official PDF/blueprint documents: {', '.join(matched_docs[:4])}.",
            }
        )

    # Step 4: Run Good Standing Audit & Self-Correction check
    audit_res = None
    if client and any(k in low for k in ("audit", "check", "risk", "standing", "fix", "correct", "review", "prepare", "packet", "generate", "interview")):
        audit_res = evaluate_client_standing(db, client)
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "run_good_standing_audit",
                "status": "ok",
                "detail": f"Evaluated {client.case_id}: Good Standing={audit_res['standing_score']}% ({audit_res['denial_risk_level']} risk) — {audit_res['red_count']} Red, {audit_res['amber_count']} Amber, {audit_res['green_count']} Green.",
            }
        )
        # Self-correction step: align pipeline stage if still new_intake
        if client.pipeline_stage == "new_intake":
            client.pipeline_stage = "risk_audit"
            db.commit()
            tool_trace.append(
                {
                    "step": len(tool_trace) + 1,
                    "tool": "self_correct_pipeline_stage",
                    "status": "ok",
                    "detail": f"Advanced {client.case_id} from 'new_intake' -> 'risk_audit' after automated rule check.",
                }
            )

    # Step 5: Generate interview predictions if asked
    if client and any(k in low for k in ("predict", "interview", "question", "mock", "prepare")):
        preds = generate_ranked_predictions(db, client, author="hermes_agent")
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "generate_ranked_predictions",
                "status": "ok",
                "detail": f"Prepared {len(preds)} interview questions ({sum(1 for p in preds if p.question_type=='profile_driven')} profile-driven + {sum(1 for p in preds if p.question_type=='policy_mandatory')} mandatory policy).",
            }
        )

    # Step 6: Generate draft documents / visual roadmap if requested (ALWAYS pauses for Human Approval!)
    created_assets: list[str] = []
    if client and any(k in low for k in ("generate", "draft", "worksheet", "checklist", "letter", "docx", "roadmap", "image", "visual", "packet")):
        if any(k in low for k in ("ds-160", "ds160", "worksheet", "packet", "all")):
            p, flds = generate_ds160_worksheet_pdf(client, client.risk_flags, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="ds160_worksheet_pdf", title="DS-160 Preparation Worksheet (Draft)", filename=p.name, file_path=str(p), mime_type="application/pdf", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if any(k in low for k in ("checklist", "packet", "all")):
            p, flds = generate_kingston_checklist_pdf(client, client.predictions, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="checklist_pdf", title="Kingston Embassy Checklist (Draft)", filename=p.name, file_path=str(p), mime_type="application/pdf", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if any(k in low for k in ("letter", "docx", "word", "packet", "all")):
            p, flds = generate_support_letter_docx(client, client.risk_flags, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="cover_letter_docx", title="Support & Verification Packet DOCX (Draft)", filename=p.name, file_path=str(p), mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if any(k in low for k in ("roadmap", "image", "visual", "step", "packet", "all")):
            p, flds = generate_visual_roadmap_png(client, client.risk_flags, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="visual_roadmap_png", title="Client Visual Action Roadmap PNG (Draft)", filename=p.name, file_path=str(p), mime_type="image/png", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if created_assets:
            db.commit()
            tool_trace.append(
                {
                    "step": len(tool_trace) + 1,
                    "tool": "generate_draft_assets_approval_gate",
                    "status": "paused_for_approval",
                    "detail": f"Generated {len(created_assets)} draft file(s) ({', '.join(created_assets)}) — PAUSED at Human Approval Gate before client release.",
                }
            )

    # Step 7: Sync to Obsidian Vault if requested or after audit
    if client and (any(k in low for k in ("obsidian", "vault", "note", "sync")) or audit_res):
        note = sync_client_to_obsidian(client, client.risk_flags, client.journal_entries)
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "sync_obsidian_dossier",
                "status": "ok",
                "detail": f"Synced live dossier & journal to Obsidian Vault: {note['path']}.",
            }
        )

    # Log to Pipeline Journal if bound to a client
    if client:
        db.add(
            PipelineJournal(
                case_id=client.case_id,
                event_type="hermes_agent_run",
                actor=actor,
                summary=f"Hermes executed {len(tool_trace)} tool steps for instruction: '{instruction[:120]}'",
                metadata_json=json.dumps({"tools": [t["tool"] for t in tool_trace], "created_assets": created_assets}),
            )
        )
        db.commit()

    effective_history = (
        _normalize_history(history)
        if history is not None
        else load_conversation_history(db, conversation_id, max_turns=10, exclude_last_user_msg=instruction)
    )

    if not tool_trace:
        fallback = answer_customer_question(db, instruction, client, conversation_id=conversation_id, history=effective_history)
        return {
            "reply": fallback["reply"],
            "provider_used": fallback["provider_used"],
            "case_id": client.case_id if client else None,
            "tool_trace": tool_trace,
            "created_assets": created_assets,
        }

    # Synthesize final executive summary (LLM if configured, otherwise crisp structured summary + transparent error if LLM failed)
    trace_text = "\n".join(f"{t['step']}. [{t['tool']}] ({t['status']}) {t['detail']}" for t in tool_trace)
    llm_res = call_llm_detailed(
        db,
        COMPLIANCE_SYSTEM_PROMPT,
        f"Staff instruction: {instruction}\n\nTool Execution Trace:\n{trace_text}\n\n"
        "Summarize what was verified, any red/amber flags needing human review, and the exact next recommended step.",
        history=effective_history,
    )
    llm_reply = llm_res["text"]
    provider = llm_res["provider"]

    if not llm_reply:
        err_note = f"\n\n> **AI Summary Notice (`{provider}`):** `{llm_res['error']}`" if llm_res["error"] else ""
        llm_reply = (
            f"**AI Consular Agent Complete** ({len(tool_trace)} actions executed):\n\n"
            + "\n".join(f"- **Step {t['step']} (`{t['tool']}`):** {t['detail']}" for t in tool_trace)
            + (
                "\n\n**Human Approval Gate:** Draft documents are ready in the side panel for review before releasing to the client."
                if created_assets
                else ""
            )
            + err_note
        )

    return {
        "reply": llm_reply,
        "provider_used": provider,
        "case_id": client.case_id if client else None,
        "tool_trace": tool_trace,
        "created_assets": created_assets,
    }
