"""Live Extensions API Router — Safe Self-Evolving Rules, Sandboxed Widgets, Cohorts & Portable Packs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import ClientCase, LiveExtension, User
from app.services.extensions_service import (
    _remove_disk_mirror,
    build_extension_from_prompt,
    export_extensions_pack,
    import_extensions_pack,
    list_extensions,
    render_sandboxed_widget_html,
    rollback_extension,
    serialize_extension,
)
from app.services.risk_engine import evaluate_client_standing

router = APIRouter(prefix="/api/extensions", tags=["Live Extensions"])


class BuildExtensionRequest(BaseModel):
    prompt: str


class ImportPackRequest(BaseModel):
    format: str = "jahtaria-pack/v1"
    extensions: list[dict[str, Any]] = []


@router.get("")
def get_all_extensions(
    ext_type: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_extensions(db, ext_type=ext_type, enabled_only=enabled_only)


@router.post("/build")
def build_live_extension(
    req: BuildExtensionRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        res = build_extension_from_prompt(db, req.prompt, author=user.full_name, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "extension": res["extension"],
        "provider_used": res["provider_used"],
        "affected_cases": res["affected_cases"],
    }


@router.get("/export-pack")
def export_pack(
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return export_extensions_pack(db)


@router.post("/import-pack")
def import_pack(
    req: ImportPackRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return import_extensions_pack(db, req.model_dump(), author=user.full_name)


@router.get("/{slug_or_id}")
def get_single_extension(
    slug_or_id: str,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ext = (
        db.query(LiveExtension).filter(LiveExtension.id == int(slug_or_id)).first()
        if slug_or_id.isdigit()
        else db.query(LiveExtension).filter(LiveExtension.slug == slug_or_id).first()
    )
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found.")
    return serialize_extension(ext, include_code=True)


@router.get("/{slug_or_id}/render", response_class=HTMLResponse)
def render_widget_extension(
    slug_or_id: str,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    ext = (
        db.query(LiveExtension).filter(LiveExtension.id == int(slug_or_id)).first()
        if slug_or_id.isdigit()
        else db.query(LiveExtension).filter(LiveExtension.slug == slug_or_id).first()
    )
    if not ext:
        raise HTTPException(status_code=404, detail="Widget not found.")
    html = render_sandboxed_widget_html(db, ext)
    return HTMLResponse(content=html)


@router.post("/{ext_id}/toggle")
def toggle_extension(
    ext_id: int,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ext = db.query(LiveExtension).filter(LiveExtension.id == ext_id).first()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found.")
    ext.enabled = not bool(ext.enabled)
    db.commit()
    db.refresh(ext)
    if ext.ext_type == "risk_rule":
        for c in db.query(ClientCase).all():
            evaluate_client_standing(db, c)
    return serialize_extension(ext)


@router.post("/{ext_id}/rollback")
def rollback_live_extension(
    ext_id: int,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ext = db.query(LiveExtension).filter(LiveExtension.id == ext_id).first()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found.")
    try:
        out = rollback_extension(db, ext)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if ext.ext_type == "risk_rule":
        for c in db.query(ClientCase).all():
            evaluate_client_standing(db, c)
    return out


@router.delete("/{ext_id}")
def delete_live_extension(
    ext_id: int,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    ext = db.query(LiveExtension).filter(LiveExtension.id == ext_id).first()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found.")
    was_rule = ext.ext_type == "risk_rule"
    slug = ext.slug
    db.delete(ext)
    db.commit()
    _remove_disk_mirror(slug)
    if was_rule:
        for c in db.query(ClientCase).all():
            evaluate_client_standing(db, c)
    return {"deleted": True}
