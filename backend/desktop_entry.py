"""Standalone PyInstaller entry point for Jahtaria Visa Intelligence Desktop Backend."""

from __future__ import annotations

import multiprocessing
import os


def _configure_tls_certificates() -> None:
    """Ensure frozen Windows/macOS/Linux builds trust the OS certificate store + bundled certifi roots."""
    try:
        import certifi

        ca_bundle = certifi.where()
        if ca_bundle and os.path.exists(ca_bundle):
            os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
    except Exception:
        pass

    # Prefer the OS native certificate store (Windows Certificate Store / macOS Keychain)
    # so HTTPS works even behind corporate proxies or antivirus Web Shields (Avast, Bitdefender, etc.)
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


_configure_tls_certificates()

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402


def main() -> None:
    multiprocessing.freeze_support()
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8010"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
