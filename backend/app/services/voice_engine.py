"""Assimilis-Derived Voice Engine: Free Edge Neural Voices + ElevenLabs Flash API + Fish Audio.

Pre-loaded personas for Jahtaria Travel Services:
- advisor_ja: Warm Caribbean / British-English Visa Advisor (default)
- officer_us: U.S. Embassy Kingston Consular Officer (for realistic Voice Mock Interviews)
- advisor_male: Calm British-English Advisor
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any

from sqlalchemy.orm import Session

from app.config import mask_secret
from app.services.connectors import get_setting, set_setting

ELEVEN_API = "https://api.elevenlabs.io/v1/text-to-speech/"
ELEVEN_DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # George
ELEVEN_DEFAULT_MODEL = "eleven_flash_v2_5"

FISH_API = "https://api.fish.audio/v1/tts"

PERSONAS = {
    "advisor_ja": {
        "id": "advisor_ja",
        "label": "Visa Advisor (Warm Caribbean / UK)",
        "edge_voice": "en-GB-SoniaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
    },
    "officer_us": {
        "id": "officer_us",
        "label": "U.S. Embassy Officer (Mock Interview)",
        "edge_voice": "en-US-AndrewMultilingualNeural",
        "rate": "+3%",
        "pitch": "-2Hz",
    },
    "advisor_male": {
        "id": "advisor_male",
        "label": "Senior Consular Specialist (Male)",
        "edge_voice": "en-GB-RyanNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
    },
    "officer_female": {
        "id": "officer_female",
        "label": "U.S. Consular Officer (Female)",
        "edge_voice": "en-US-JennyNeural",
        "rate": "+2%",
        "pitch": "+0Hz",
    },
}

_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{16,})")


def _clean_for_speech(text: str) -> str:
    clean = _SECRET_PATTERN.sub("[redacted]", text)
    clean = re.sub(r"```[\s\S]*?```", " ", clean)
    clean = re.sub(r"https?://\S+", "official website link", clean)
    clean = re.sub(r"[*_#`>\[\]]+", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:1200]


def get_voice_config(db: Session) -> dict[str, Any]:
    eleven_key = get_setting(db, "elevenlabs_api_key", "")
    fish_key = get_setting(db, "fish_api_key", "")
    return {
        "engine": get_setting(db, "voice_engine", "edge"),  # edge | elevenlabs | fish
        "default_persona": get_setting(db, "voice_persona", "advisor_ja"),
        "auto_speak": get_setting(db, "voice_auto_speak", "false") == "true",
        "elevenlabs_configured": bool(eleven_key),
        "elevenlabs_key_masked": mask_secret(eleven_key),
        "elevenlabs_voice_id": get_setting(db, "elevenlabs_voice_id", ELEVEN_DEFAULT_VOICE),
        "fish_configured": bool(fish_key),
        "fish_key_masked": mask_secret(fish_key),
        "fish_voice_id": get_setting(db, "fish_voice_id", ""),
        "personas": list(PERSONAS.values()),
    }


def save_voice_config(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if "engine" in payload and payload["engine"]:
        set_setting(db, "voice_engine", str(payload["engine"]), is_secret=False, category="voice")
    if "default_persona" in payload and payload["default_persona"]:
        set_setting(db, "voice_persona", str(payload["default_persona"]), is_secret=False, category="voice")
    if "auto_speak" in payload and payload["auto_speak"] is not None:
        set_setting(db, "voice_auto_speak", "true" if payload["auto_speak"] else "false", is_secret=False, category="voice")
    if payload.get("elevenlabs_api_key") and "•" not in str(payload["elevenlabs_api_key"]):
        set_setting(db, "elevenlabs_api_key", str(payload["elevenlabs_api_key"]).strip(), is_secret=True, category="voice")
    if payload.get("elevenlabs_voice_id"):
        set_setting(db, "elevenlabs_voice_id", str(payload["elevenlabs_voice_id"]).strip(), is_secret=False, category="voice")
    if payload.get("fish_api_key") and "•" not in str(payload["fish_api_key"]):
        set_setting(db, "fish_api_key", str(payload["fish_api_key"]).strip(), is_secret=True, category="voice")
    if payload.get("fish_voice_id"):
        set_setting(db, "fish_voice_id", str(payload["fish_voice_id"]).strip(), is_secret=False, category="voice")
    return get_voice_config(db)


def _voice_ssl_verify() -> object:
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


def _elevenlabs_tts(text: str, api_key: str, voice_id: str) -> bytes:
    import httpx

    vid = voice_id.strip() or ELEVEN_DEFAULT_VOICE
    with httpx.Client(timeout=30.0, verify=_voice_ssl_verify()) as client:
        resp = client.post(
            f"{ELEVEN_API}{vid}?output_format=mp3_44100_128",
            json={"text": text, "model_id": ELEVEN_DEFAULT_MODEL},
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
        )
        resp.raise_for_status()
        return resp.content


def _fish_tts(text: str, api_key: str, voice_id: str) -> bytes:
    import httpx

    body = {"text": text, "format": "mp3", "mp3_bitrate": 128}
    if voice_id.strip():
        body["reference_id"] = voice_id.strip()
    with httpx.Client(timeout=30.0, verify=_voice_ssl_verify()) as client:
        resp = client.post(
            FISH_API,
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "audio/mpeg"},
        )
        resp.raise_for_status()
        return resp.content


async def _edge_tts_bytes(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    import edge_tts

    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    chunks: list[bytes] = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def synthesize_speech(
    db: Session,
    text: str,
    persona: str | None = None,
    engine_override: str | None = None,
) -> tuple[bytes, str]:
    """Synthesize natural MP3 speech using configured engine (ElevenLabs / Fish / Free Edge Neural)."""
    safe_text = _clean_for_speech(text)
    if not safe_text:
        return b"", "empty"

    engine = (engine_override or get_setting(db, "voice_engine", "edge")).lower()
    p_key = persona or get_setting(db, "voice_persona", "advisor_ja")
    p_cfg = PERSONAS.get(p_key, PERSONAS["advisor_ja"])

    if engine == "elevenlabs":
        key = get_setting(db, "elevenlabs_api_key", "")
        vid = get_setting(db, "elevenlabs_voice_id", ELEVEN_DEFAULT_VOICE)
        if key:
            try:
                audio = await asyncio.to_thread(_elevenlabs_tts, safe_text, key, vid)
                if audio:
                    return audio, "elevenlabs"
            except Exception:
                pass

    if engine == "fish":
        key = get_setting(db, "fish_api_key", "")
        vid = get_setting(db, "fish_voice_id", "")
        if key:
            try:
                audio = await asyncio.to_thread(_fish_tts, safe_text, key, vid)
                if audio:
                    return audio, "fish_audio"
            except Exception:
                pass

    # Default / Free zero-key fallback: Microsoft Edge Neural Voices (from Assimilis VoiceStudio)
    audio = await _edge_tts_bytes(safe_text, p_cfg["edge_voice"], p_cfg["rate"], p_cfg["pitch"])
    return audio, f"edge:{p_cfg['edge_voice']}"
