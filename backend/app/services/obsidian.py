"""Real local Obsidian Vault manager (Markdown notes, [[wikilinks]], backlinks & client dossier sync)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import OBSIDIAN_VAULT_DIR
from app.models import ClientCase, PipelineJournal, RiskFlag

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _safe_note_path(rel_path: str) -> Path:
    clean = rel_path.strip().lstrip("/").replace("\\", "/")
    if not clean.endswith(".md"):
        clean += ".md"
    target = (OBSIDIAN_VAULT_DIR / clean).resolve()
    if not str(target).startswith(str(OBSIDIAN_VAULT_DIR.resolve())):
        raise ValueError("Invalid vault path.")
    return target


def list_vault_notes(query: str = "") -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    q = query.strip().lower()
    for md in sorted(OBSIDIAN_VAULT_DIR.rglob("*.md")):
        rel = md.relative_to(OBSIDIAN_VAULT_DIR).as_posix()
        content = md.read_text(encoding="utf-8", errors="replace")
        if q and q not in rel.lower() and q not in content.lower():
            continue
        folder = md.parent.relative_to(OBSIDIAN_VAULT_DIR).as_posix()
        if folder == ".":
            folder = "Root"
        links = WIKILINK_RE.findall(content)
        tags = sorted(set(re.findall(r"(?<!\w)#([a-zA-Z0-9_-]+)", content)))
        notes.append(
            {
                "path": rel,
                "name": md.stem,
                "folder": folder,
                "size_bytes": md.stat().st_size,
                "updated_at": datetime.fromtimestamp(md.stat().st_mtime, tz=timezone.utc).isoformat(),
                "links": links,
                "tags": tags[:10],
                "excerpt": content[:200].replace("\n", " "),
            }
        )
    return notes


def read_vault_note(rel_path: str) -> dict[str, Any]:
    target = _safe_note_path(rel_path)
    if not target.exists():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    content = target.read_text(encoding="utf-8", errors="replace")
    stem = target.stem
    rel = target.relative_to(OBSIDIAN_VAULT_DIR).as_posix()
    links = WIKILINK_RE.findall(content)

    # Calculate backlinks across vault
    backlinks: list[str] = []
    for other in OBSIDIAN_VAULT_DIR.rglob("*.md"):
        if other.resolve() == target.resolve():
            continue
        other_txt = other.read_text(encoding="utf-8", errors="replace")
        other_links = [lnk.split("/")[-1].replace(".md", "") for lnk in WIKILINK_RE.findall(other_txt)]
        if stem in other_links or rel.replace(".md", "") in WIKILINK_RE.findall(other_txt):
            backlinks.append(other.relative_to(OBSIDIAN_VAULT_DIR).as_posix())

    return {
        "path": rel,
        "name": stem,
        "content": content,
        "links": links,
        "backlinks": sorted(backlinks),
        "updated_at": datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).isoformat(),
        "vault_dir": str(OBSIDIAN_VAULT_DIR),
    }


def write_vault_note(rel_path: str, content: str) -> dict[str, Any]:
    target = _safe_note_path(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return read_vault_note(target.relative_to(OBSIDIAN_VAULT_DIR).as_posix())


def delete_vault_note(rel_path: str) -> bool:
    target = _safe_note_path(rel_path)
    if target.exists():
        target.unlink()
        return True
    return False


def sync_client_to_obsidian(
    client: ClientCase,
    flags: list[RiskFlag],
    journal: list[PipelineJournal],
) -> dict[str, Any]:
    """Export/update a client's structured dossier & journal directly into Obsidian Vault."""
    tags = []
    try:
        tags = json.loads(client.profile_tags_json or "[]")
    except Exception:
        pass

    lines = [
        "---",
        f"case_id: {client.case_id}",
        f"visa_class: {client.visa_class}",
        f"stage: {client.pipeline_stage}",
        f"standing_score: {client.standing_score}",
        f"outcome: {client.outcome}",
        f"updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "---",
        "",
        f"# {client.case_id} — {client.full_name or client.pseudonym}",
        "",
        f"> **Good Standing:** `{client.standing_score}%` ({client.denial_risk_level.upper()} risk) | **Visa:** `{client.visa_class}` | **Stage:** `{client.pipeline_stage}`",
        "",
        "## Core Profile",
        f"- **Nationality / Parish:** {client.nationality} ({client.parish or 'N/A'})",
        f"- **Occupation / Employer:** {client.occupation or 'Pending'} — {client.employer_name or 'Pending'}",
        f"- **Monthly Gross / Net JMD:** {client.monthly_gross_jmd or 'Unverified'} / {client.monthly_net_jmd or 'Unverified'}",
        f"- **DS-160 Barcode:** `{client.ds160_confirmation_id or 'Pending'}` | **AIS Barcode:** `{client.ais_appointment_barcode or 'Pending'}`",
        f"- **Passport Expiry:** `{client.passport_expiry or 'Pending'}`",
        f"- **Purpose & Destination:** {client.purpose_of_trip or 'Pending'} → {client.us_destination or 'USA'}",
        f"- **Profile Tags:** {', '.join('#' + str(t) for t in tags) if tags else 'none'}",
        "",
        "## Linked Official References",
        "- [[Gov-Rules/US-Embassy-Kingston-Rules]]",
        "- [[Gov-Rules/PICA-Jamaica-Passport-Rules]]",
        "- [[Gov-Rules/Compliance-and-Evaluation-Standards]]",
        "",
        "## Active Risk Flags & Readiness Checks",
    ]

    for fl in flags:
        icon = "🔴" if fl.severity == "red" else ("🟠" if fl.severity == "amber" else "🟢")
        lines.append(f"- {icon} **{fl.title}** (`{fl.code}`): {fl.detail}")
        if fl.suggested_fix:
            lines.append(f"  - *Fix:* {fl.suggested_fix}")
        if fl.client_response:
            lines.append(f"  - *Client Response:* {fl.client_response}")

    lines.extend(["", "## Pipeline Journal (Chronological)"])
    for entry in journal[:20]:
        ts = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else ""
        lines.append(f"- `{ts}` **{entry.event_type}** ({entry.actor}): {entry.summary}")

    return write_vault_note(f"Clients/{client.case_id}.md", "\n".join(lines) + "\n")
