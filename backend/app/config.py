"""Application configuration, directory paths, and Fernet encryption helpers."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data"))).resolve()
SEED_PACKAGE_DIR = DATA_DIR / "seed_package"
OFFICIAL_PDFS_DIR = DATA_DIR / "official_pdfs"
BLUEPRINTS_DIR = DATA_DIR / "blueprints"
GENERATED_DIR = DATA_DIR / "generated"
OBSIDIAN_VAULT_DIR = DATA_DIR / "obsidian-vault"
LOGO_PATH = DATA_DIR / "jahtaria-logo.png"

for _d in (DATA_DIR, OFFICIAL_PDFS_DIR, BLUEPRINTS_DIR, GENERATED_DIR, OBSIDIAN_VAULT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_or_create_secret() -> str:
    env_secret = os.getenv("SECRET_KEY", "").strip()
    if env_secret and env_secret != "change-this-to-a-long-random-secret-key-in-production":
        return env_secret
    secret_file = DATA_DIR / ".secret_key"
    if secret_file.exists():
        val = secret_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    val = secrets.token_urlsafe(48)
    secret_file.write_text(val, encoding="utf-8")
    try:
        os.chmod(secret_file, 0o600)
    except OSError:
        pass
    return val


SECRET_KEY: str = _load_or_create_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{(DATA_DIR / 'jamaica_govbot.db').as_posix()}",
)
if DATABASE_URL.startswith("sqlite:///../"):
    rel = DATABASE_URL.replace("sqlite:///../", "")
    DATABASE_URL = f"sqlite:///{(ROOT_DIR / rel).as_posix()}"

APP_NAME = os.getenv("APP_NAME", "Jahtaria Travel Services")
APP_TAGLINE = os.getenv("APP_TAGLINE", "U.S. Visa Preparation & Consular Intelligence")
APP_ENV = os.getenv("APP_ENV", "desktop")

SEED_CEO_EMAIL = os.getenv("SEED_CEO_EMAIL", "ceo@jahtariatravel.com")
SEED_CEO_PASSWORD = os.getenv("SEED_CEO_PASSWORD", "JahtariaCEO2026!")
SEED_STAFF_EMAIL = os.getenv("SEED_STAFF_EMAIL", "staff@jahtariatravel.com")
SEED_STAFF_PASSWORD = os.getenv("SEED_STAFF_PASSWORD", "JahtariaStaff2026!")
SEED_CLIENT_EMAIL = os.getenv("SEED_CLIENT_EMAIL", "client@jahtariatravel.com")
SEED_CLIENT_PASSWORD = os.getenv("SEED_CLIENT_PASSWORD", "JahtariaClient2026!")


def _get_fernet() -> Fernet:
    raw_key = os.getenv("ENCRYPTION_KEY", "").strip()
    if raw_key:
        try:
            return Fernet(raw_key.encode("utf-8"))
        except Exception:
            pass
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


_FERNET = _get_fernet()


def encrypt_value(plaintext: str | None) -> str:
    if not plaintext:
        return ""
    return _FERNET.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str | None) -> str:
    if not ciphertext:
        return ""
    try:
        return _FERNET.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ciphertext


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}••••{value[-4:]}"
