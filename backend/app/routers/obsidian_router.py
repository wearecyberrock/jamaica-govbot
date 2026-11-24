"""Obsidian Vault Router — browse, search, edit Markdown notes with [[wikilinks]] and client dossier sync."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import OBSIDIAN_VAULT_DIR
from app.database import get_db
from app.models import ClientCase, User
from app.services.obsidian import (
    delete_vault_note,
    list_vault_notes,
    read_vault_note,
    sync_client_to_obsidian,
    write_vault_note,
)

router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])


class SaveNoteRequest(BaseModel):
    path: str
    content: str


@router.get("/notes")
def get_notes(
    query: str = "",
    _user: User = Depends(require_roles("staff", "ceo")),
) -> dict[str, Any]:
    return {"vault_dir": str(OBSIDIAN_VAULT_DIR), "notes": list_vault_notes(query)}


@router.get("/note")
def get_note(
    path: str,
    _user: User = Depends(require_roles("staff", "ceo")),
) -> dict[str, Any]:
    try:
        return read_vault_note(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/note")
def save_note(
    req: SaveNoteRequest,
    _user: User = Depends(require_roles("staff", "ceo")),
) -> dict[str, Any]:
    try:
        return write_vault_note(req.path, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/note")
def remove_note(
    path: str,
    _user: User = Depends(require_roles("staff", "ceo")),
) -> dict[str, Any]:
    try:
        deleted = delete_vault_note(path)
        return {"deleted": deleted, "path": path}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync-client/{case_id}")
def sync_client_note(
    case_id: str,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client case not found.")
    return sync_client_to_obsidian(client, client.risk_flags, client.journal_entries)
