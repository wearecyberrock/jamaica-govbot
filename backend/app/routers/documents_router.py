"""Official PDFs Viewer, Blueprint Uploader/Inspector, Auto-Fill Engine & Human Approval Gate Router."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.config import BLUEPRINTS_DIR
from app.database import get_db
from app.models import BrandingConfig, ClientCase, GeneratedAsset, OfficialDocument, PipelineJournal, User
from app.services.doc_generator import (
    fill_custom_blueprint,
    generate_ds160_worksheet_pdf,
    generate_kingston_checklist_pdf,
    generate_support_letter_docx,
    generate_visual_roadmap_png,
    inspect_blueprint_file,
)
from app.services.obsidian import sync_client_to_obsidian

router = APIRouter(prefix="/api", tags=["documents"])


class GenerateAssetRequest(BaseModel):
    asset_type: str  # ds160_worksheet_pdf | checklist_pdf | cover_letter_docx | visual_roadmap_png | custom_blueprint
    blueprint_doc_key: str | None = None


class ApproveAssetRequest(BaseModel):
    decision: str = "approved"  # approved | rejected
    visible_to_client: bool = True


@router.get("/documents/official")
def list_official_documents(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    docs = db.query(OfficialDocument).order_by(OfficialDocument.id).all()
    out = []
    for d in docs:
        fields = []
        try:
            fields = json.loads(d.detected_fields_json or "[]")
        except Exception:
            pass
        out.append(
            {
                "id": d.id,
                "doc_key": d.doc_key,
                "title": d.title,
                "agency": d.agency,
                "category": d.category,
                "filename": d.filename,
                "file_format": d.file_format,
                "size_bytes": d.size_bytes,
                "sha256": d.sha256,
                "source_url": d.source_url,
                "description": d.description,
                "detected_fields": fields,
                "is_blueprint": d.is_blueprint,
                "file_exists": Path(d.file_path).exists(),
                "view_url": f"/api/documents/official/{d.doc_key}/view",
            }
        )
    return out


@router.get("/documents/official/{doc_key}/view")
def view_official_document(doc_key: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serve official PDF or DOCX inline so the embedded PDF viewer in the dashboard can display it cleanly."""
    doc = db.query(OfficialDocument).filter(OfficialDocument.doc_key == doc_key).first()
    if not doc or not Path(doc.file_path).exists():
        raise HTTPException(status_code=404, detail="Official document file not found.")
    media = "application/pdf" if doc.file_format.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(
        path=doc.file_path,
        media_type=media,
        filename=doc.filename,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.post("/documents/blueprints/upload")
async def upload_blueprint(
    file: UploadFile = File(...),
    title: str = Form(""),
    agency: str = Form("Agency Blueprint"),
    source_url: str = Form(""),
    description: str = Form(""),
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="Only .pdf and .docx blueprint files are supported.")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    target = BLUEPRINTS_DIR / safe_name
    content = await file.read()
    target.write_bytes(content)

    info = inspect_blueprint_file(target)
    doc_key = re.sub(r"[^a-z0-9_]+", "_", target.stem.lower()).strip("_")[:60]
    if db.query(OfficialDocument).filter(OfficialDocument.doc_key == doc_key).first():
        doc_key = f"{doc_key}_{int(datetime.now(timezone.utc).timestamp())}"

    record = OfficialDocument(
        doc_key=doc_key,
        title=title.strip() or target.stem.replace("_", " "),
        agency=agency.strip() or "Agency Blueprint",
        category="agency_blueprint",
        filename=safe_name,
        file_path=str(target),
        file_format=ext,
        size_bytes=info["size_bytes"],
        sha256=info["sha256"],
        source_url=source_url.strip(),
        description=description.strip() or f"Uploaded by {user.full_name} ({info['pages']} page(s)).",
        detected_fields_json=json.dumps(info["detected_fields"]),
        is_blueprint=True,
    )
    db.add(record)
    db.commit()
    return {
        "doc_key": record.doc_key,
        "title": record.title,
        "filename": record.filename,
        "pages": info["pages"],
        "detected_fields": info["detected_fields"],
        "view_url": f"/api/documents/official/{record.doc_key}/view",
    }


@router.post("/clients/{case_id}/assets/generate")
def generate_client_asset(
    case_id: str,
    req: GenerateAssetRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate a draft PDF, DOCX, or Visual Roadmap PNG paused at the Human Approval Gate."""
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    branding = db.query(BrandingConfig).first()

    if req.asset_type == "ds160_worksheet_pdf":
        path, fields = generate_ds160_worksheet_pdf(c, c.risk_flags, branding)
        title, mime = "DS-160 Preparation & Verification Worksheet (PDF)", "application/pdf"
    elif req.asset_type == "checklist_pdf":
        path, fields = generate_kingston_checklist_pdf(c, c.predictions, branding)
        title, mime = "U.S. Embassy Kingston Pre-Interview Checklist (PDF)", "application/pdf"
    elif req.asset_type == "cover_letter_docx":
        path, fields = generate_support_letter_docx(c, c.risk_flags, branding)
        title, mime = "Editable Support & Employment Verification Packet (DOCX)", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif req.asset_type == "visual_roadmap_png":
        path, fields = generate_visual_roadmap_png(c, c.risk_flags, branding)
        title, mime = "Client Visual Step-by-Step Roadmap Card (PNG)", "image/png"
    elif req.asset_type == "custom_blueprint" and req.blueprint_doc_key:
        bp = db.query(OfficialDocument).filter(OfficialDocument.doc_key == req.blueprint_doc_key).first()
        if not bp or not Path(bp.file_path).exists():
            raise HTTPException(status_code=404, detail="Blueprint file not found.")
        path, fields = fill_custom_blueprint(Path(bp.file_path), c)
        title = f"Auto-Filled: {bp.title}"
        mime = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported asset_type: {req.asset_type}")

    asset = GeneratedAsset(
        case_id=c.case_id,
        asset_type=req.asset_type,
        title=title,
        filename=path.name,
        file_path=str(path),
        mime_type=mime,
        filled_fields_json=json.dumps(fields),
        approval_status="pending_approval",
        visible_to_client=False,
    )
    db.add(asset)
    if c.pipeline_stage in ("new_intake", "data_synced", "risk_audit", "questionnaire"):
        c.pipeline_stage = "review_approval"
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="asset_drafted",
            actor=user.full_name,
            summary=f"Generated draft '{title}' ({path.name}) — awaiting Human Approval before client release.",
        )
    )
    db.commit()
    db.refresh(asset)
    return {
        "id": asset.id,
        "title": asset.title,
        "filename": asset.filename,
        "mime_type": asset.mime_type,
        "approval_status": asset.approval_status,
        "file_url": f"/api/assets/{asset.id}/file",
    }


@router.post("/assets/{asset_id}/approve")
def approve_or_reject_asset(
    asset_id: int,
    req: ApproveAssetRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    asset = db.query(GeneratedAsset).filter(GeneratedAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Generated asset not found.")
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Decision must be 'approved' or 'rejected'.")

    now = datetime.now(timezone.utc)
    asset.approval_status = req.decision
    asset.approved_by = user.full_name
    asset.approved_at = now
    asset.visible_to_client = bool(req.visible_to_client and req.decision == "approved")

    c = db.query(ClientCase).filter(ClientCase.case_id == asset.case_id).first()
    if c and req.decision == "approved" and c.pipeline_stage == "review_approval":
        c.pipeline_stage = "docs_ready"

    db.add(
        PipelineJournal(
            case_id=asset.case_id,
            event_type=f"asset_{req.decision}",
            actor=user.full_name,
            summary=f"{req.decision.upper()} '{asset.title}' (client portal visible={asset.visible_to_client}).",
        )
    )
    db.commit()
    if c:
        sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    return {
        "id": asset.id,
        "approval_status": asset.approval_status,
        "approved_by": asset.approved_by,
        "visible_to_client": asset.visible_to_client,
    }


@router.get("/assets/{asset_id}/file")
def download_or_preview_asset(asset_id: int, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.query(GeneratedAsset).filter(GeneratedAsset.id == asset_id).first()
    if not asset or not Path(asset.file_path).exists():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    disp = "inline" if asset.mime_type in ("application/pdf", "image/png") else "attachment"
    return FileResponse(
        path=asset.file_path,
        media_type=asset.mime_type,
        filename=asset.filename,
        headers={"Content-Disposition": f'{disp}; filename="{asset.filename}"'},
    )
