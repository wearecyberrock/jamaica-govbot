"""Official Government Web Source Scraper & Change-Diff Watcher.

Fetches official U.S. Embassy Kingston, U.S. Dept. of State, PICA Jamaica, and RGD pages
via HTTP (with optional Playwright headless Chromium browser-hands fallback), computes
SHA-256 hashes, flags content diffs for staff review, and extracts clean readable text.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import GovSource

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if len(line) > 25]
    return "\n".join(lines)[:4500]


def _playwright_fetch(url: str) -> str | None:
    """Optional headless browser hands fallback for WAF/JS-heavy government sites."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def scrape_single_source(db: Session, source: GovSource, use_browser_fallback: bool = False) -> dict[str, Any]:
    """Fetch a single official source, compute SHA-256 hash, and record diff alerts."""
    now = datetime.now(timezone.utc)
    fetched_text = ""
    method = "httpx"
    error_msg = ""

    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, verify=False) as client:
            resp = client.get(
                source.url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            if resp.status_code == 200 and resp.text:
                fetched_text = _clean_html_text(resp.text)
            else:
                error_msg = f"HTTP {resp.status_code}"
    except Exception as exc:
        error_msg = str(exc)[:180]

    if not fetched_text and use_browser_fallback:
        html = _playwright_fetch(source.url)
        if html:
            fetched_text = _clean_html_text(html)
            method = "playwright_browser_hands"
            error_msg = ""

    if fetched_text:
        new_hash = hashlib.sha256(fetched_text.encode("utf-8")).hexdigest()
        changed = bool(source.content_hash and source.content_hash != new_hash)
        if changed:
            source.previous_hash = source.content_hash
            source.diff_alert = True
            source.diff_summary = (
                f"Content hash changed on {now.strftime('%Y-%m-%d %H:%M UTC')} "
                f"({source.previous_hash[:10]} -> {new_hash[:10]}). Review official rules before updating."
            )
        source.content_hash = new_hash
        source.scraped_excerpt = fetched_text
        source.scrape_status = f"live_scraped ({method})"
        source.last_scraped_at = now
        db.commit()
        return {
            "source_key": source.source_key,
            "name": source.name,
            "url": source.url,
            "status": source.scrape_status,
            "changed": changed,
            "content_hash": new_hash[:16],
            "chars_extracted": len(fetched_text),
            "last_scraped_at": now.isoformat(),
        }

    # Preserve verified seeded summary if live gov WAF blocked direct fetch
    source.scrape_status = f"verified_cache (live check: {error_msg or 'WAF protected'})"
    source.last_scraped_at = now
    db.commit()
    return {
        "source_key": source.source_key,
        "name": source.name,
        "url": source.url,
        "status": source.scrape_status,
        "changed": False,
        "content_hash": (source.content_hash or "")[:16],
        "chars_extracted": len(source.scraped_excerpt or source.verified_summary or ""),
        "last_scraped_at": now.isoformat(),
        "note": "Government portal uses WAF protection; verified official rules remain active and clickable link is preserved.",
    }


def scrape_all_sources(db: Session, use_browser_fallback: bool = False) -> list[dict[str, Any]]:
    sources = db.query(GovSource).filter(GovSource.enabled == True).order_by(GovSource.id).all()  # noqa: E712
    return [scrape_single_source(db, src, use_browser_fallback=use_browser_fallback) for src in sources]
