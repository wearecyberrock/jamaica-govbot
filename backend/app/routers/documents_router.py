"""Official PDFs Viewer, Blueprint Uploader/Inspector, Auto-Fill Engine & Human Approval Gate Router."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.config import BLUEPRINTS_DIR, CLIENT_VAULT_DIR, encrypt_value
from app.database import get_db
from app.models import (
    BrandingConfig,
    ClientCase,
    ClientDocument,
    GeneratedAsset,
    OfficialDocument,
    PendingAction,
    PipelineJournal,
    User,
)
from app.services.doc_generator import (
    fill_custom_blueprint,
    generate_ds160_worksheet_pdf,
    generate_kingston_checklist_pdf,
    generate_support_letter_docx,
    generate_visual_roadmap_png,
    inspect_blueprint_file,
    sha256_file,
)
from app.services.doc_intelligence import (
    ai_autofill_official_pdf,
    burn_annotations_to_new_version,
    convert_to_rgd_92_pdf,
    export_client_embassy_packet,
    get_pdf_page_count,
    render_pdf_page_png,
    scan_document_with_ai,
)
from app.services.obsidian import sync_client_to_obsidian
from app.services.risk_engine import evaluate_client_standing

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


# ── Per-Client Document & Image Vault, Vision OCR, Full-Screen Studio & Packet Export ──


class StudioSaveRequest(BaseModel):
    source_type: str  # vault | asset | official
    source_id: str
    case_id: str | None = None
    title: str = ""
    category: str = "embassy_forms"
    annotations: list[dict[str, Any]] = []
    docx_paragraphs: list[str] | None = None


class AttachVaultDocRequest(BaseModel):
    case_id: str | None = None
    create_new_client: bool = False
    full_name: str = ""
    visa_class: str = "B1/B2"


class FillOfficialRequest(BaseModel):
    doc_key: str


class ExportPacketRequest(BaseModel):
    bundle_format: str = "pdf"  # pdf | zip


def _serialize_vault_doc(d: ClientDocument) -> dict[str, Any]:
    fields = {}
    try:
        fields = json.loads(d.extracted_fields_json or "{}")
    except Exception:
        fields = {}
    return {
        "id": d.id,
        "case_id": d.case_id,
        "category": d.category,
        "title": d.title,
        "filename": d.filename,
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "page_count": d.page_count,
        "extracted_fields": fields,
        "ai_summary": d.ai_summary,
        "parent_doc_id": d.parent_doc_id,
        "version_number": d.version_number,
        "visible_to_client": d.visible_to_client,
        "uploaded_by": d.uploaded_by,
        "file_url": f"/api/documents/vault/{d.id}/file",
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _resolve_studio_source(db: Session, source_type: str, source_id: str) -> tuple[Path, str, str, str, str | None, int | None]:
    """Return `(path, title, filename, mime_type, case_id, parent_doc_id)` for vault|asset|official."""
    if source_type == "vault":
        d = db.query(ClientDocument).filter(ClientDocument.id == int(source_id)).first()
        if not d or not Path(d.file_path).exists():
            raise HTTPException(status_code=404, detail="Vault document not found.")
        return Path(d.file_path), d.title, d.filename, d.mime_type, d.case_id, d.id
    if source_type == "asset":
        a = db.query(GeneratedAsset).filter(GeneratedAsset.id == int(source_id)).first()
        if not a or not Path(a.file_path).exists():
            raise HTTPException(status_code=404, detail="Generated asset not found.")
        return Path(a.file_path), a.title, a.filename, a.mime_type, a.case_id, None
    if source_type == "official":
        o = db.query(OfficialDocument).filter(OfficialDocument.doc_key == source_id).first()
        if not o or not Path(o.file_path).exists():
            raise HTTPException(status_code=404, detail="Official document not found.")
        mime = "application/pdf" if o.file_format.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return Path(o.file_path), o.title, o.filename, mime, None, None
    raise HTTPException(status_code=400, detail=f"Unknown source_type: {source_type}")


@router.get("/clients/{case_id}/documents")
def list_client_vault_documents(
    case_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    cid = case_id.upper()
    if user.role == "customer" and user.linked_case_id != cid:
        raise HTTPException(status_code=403, detail="Forbidden.")
    q = db.query(ClientDocument).filter(ClientDocument.case_id == cid)
    if user.role == "customer":
        q = q.filter(ClientDocument.visible_to_client == True)  # noqa: E712
    rows = q.order_by(ClientDocument.id.desc()).all()
    return [_serialize_vault_doc(d) for d in rows]


@router.post("/clients/{case_id}/documents/upload")
async def upload_client_vault_document(
    case_id: str,
    file: UploadFile = File(...),
    category: str = Form(""),
    title: str = Form(""),
    auto_scan: bool = Form(True),
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cid = case_id.upper()
    client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Case {cid} not found.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    case_dir = CLIENT_VAULT_DIR / cid
    case_dir.mkdir(parents=True, exist_ok=True)
    target = case_dir / f"{ts}_{safe_name}"
    raw_bytes = await file.read()
    target.write_bytes(raw_bytes)

    mime = file.content_type or ("application/pdf" if target.suffix.lower() == ".pdf" else "image/png")
    scan = scan_document_with_ai(db, target, mime, safe_name) if auto_scan else {
        "category": category or "photos_other",
        "summary": f"Uploaded {safe_name}",
        "extracted_text": "",
        "extracted_fields": {},
        "compliance_alerts": [],
    }
    final_cat = category.strip() if category.strip() else scan["category"]

    doc = ClientDocument(
        case_id=cid,
        category=final_cat,
        title=title.strip() or scan.get("document_type") or Path(safe_name).stem.replace("_", " "),
        filename=safe_name,
        file_path=str(target),
        mime_type=mime,
        size_bytes=len(raw_bytes),
        sha256=sha256_file(target),
        page_count=get_pdf_page_count(target),
        extracted_text=scan.get("extracted_text", ""),
        extracted_fields_json=json.dumps(scan.get("extracted_fields", {})),
        ai_summary=scan.get("summary", ""),
        uploaded_by=user.full_name,
    )
    db.add(doc)
    db.flush()

    # Build a 1-click Preview & Confirm card if OCR extracted any profile updates
    pending_action_out = None
    ext_fields: dict[str, Any] = scan.get("extracted_fields") or {}
    if ext_fields:
        before: dict[str, Any] = {}
        updates: dict[str, Any] = {}
        for k, v in ext_fields.items():
            if k in ("passport_number", "dob"):
                before[k] = "(encrypted)"
                updates[k] = v
            elif hasattr(client, k):
                cur = getattr(client, k)
                if cur != v:
                    before[k] = cur
                    updates[k] = v
        if updates:
            diff_str = ", ".join(f"{k}: {v!r}" for k, v in list(updates.items())[:6])
            pa = PendingAction(
                user_id=user.id,
                action_type="update_client",
                target_ref=cid,
                summary=f"Apply OCR scan from '{doc.title}' to {cid} ({diff_str})",
                before_json=json.dumps(before, default=str),
                after_json=json.dumps(updates, default=str),
            )
            db.add(pa)
            db.flush()
            pending_action_out = {
                "id": pa.id,
                "action_type": pa.action_type,
                "target_ref": pa.target_ref,
                "summary": pa.summary,
                "before": before,
                "after": updates,
                "status": pa.status,
            }

    db.add(
        PipelineJournal(
            case_id=cid,
            event_type="vault_document_uploaded",
            actor=user.full_name,
            summary=f"Stored '{doc.title}' in {final_cat} vault ({len(ext_fields)} field(s) scanned).",
        )
    )
    db.commit()
    db.refresh(doc)
    return {
        "document": _serialize_vault_doc(doc),
        "compliance_alerts": scan.get("compliance_alerts", []),
        "pending_action": pending_action_out,
    }


@router.post("/documents/vault/{doc_id}/scan")
def rescan_vault_document(
    doc_id: int,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    doc = db.query(ClientDocument).filter(ClientDocument.id == doc_id).first()
    if not doc or not Path(doc.file_path).exists():
        raise HTTPException(status_code=404, detail="Vault document not found.")
    scan = scan_document_with_ai(db, Path(doc.file_path), doc.mime_type, doc.filename)
    doc.category = scan["category"]
    doc.extracted_text = scan.get("extracted_text", "")
    doc.extracted_fields_json = json.dumps(scan.get("extracted_fields", {}))
    doc.ai_summary = scan.get("summary", "")
    db.commit()
    db.refresh(doc)
    return {"document": _serialize_vault_doc(doc), "compliance_alerts": scan.get("compliance_alerts", [])}


@router.post("/documents/vault/{doc_id}/attach")
def attach_vault_doc_to_client(
    doc_id: int,
    req: AttachVaultDocRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Attach an unassigned chat-pasted document to an existing client OR create a new client from its OCR scan."""
    import secrets

    doc = db.query(ClientDocument).filter(ClientDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Vault document not found.")

    extracted = {}
    try:
        extracted = json.loads(doc.extracted_fields_json or "{}")
    except Exception:
        extracted = {}

    if req.create_new_client:
        count = db.query(ClientCase).count()
        new_cid = f"C{count + 1:03d}"
        while db.query(ClientCase).filter(ClientCase.case_id == new_cid).first():
            count += 1
            new_cid = f"C{count + 1:03d}"
        name = req.full_name.strip() or str(extracted.get("full_name") or Path(doc.filename).stem.replace("_", " "))
        c = ClientCase(
            case_id=new_cid,
            access_code=f"JAH-{new_cid}-{secrets.token_hex(2).upper()}",
            pseudonym=name,
            full_name=name,
            email=str(extracted.get("email") or ""),
            phone=str(extracted.get("phone") or ""),
            parish=str(extracted.get("parish") or "Kingston & St. Andrew"),
            visa_class=req.visa_class or "B1/B2",
            passport_number_enc=encrypt_value(str(extracted.get("passport_number") or "")),
            dob_enc=encrypt_value(str(extracted.get("dob") or "")),
            passport_expiry=str(extracted.get("passport_expiry") or ""),
            occupation=str(extracted.get("occupation") or ""),
            employer_name=str(extracted.get("employer_name") or ""),
            monthly_gross_jmd=extracted.get("monthly_gross_jmd"),
            monthly_net_jmd=extracted.get("monthly_net_jmd"),
            ds160_confirmation_id=str(extracted.get("ds160_confirmation_id") or ""),
            us_destination=str(extracted.get("us_destination") or ""),
            purpose_of_trip=str(extracted.get("purpose_of_trip") or ""),
            pipeline_stage="data_synced",
            assigned_staff=user.full_name,
        )
        db.add(c)
        db.flush()
        doc.case_id = new_cid
        db.commit()
        evaluate_client_standing(db, c)
        sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
        return {"ok": True, "case_id": new_cid, "created_client": True, "document": _serialize_vault_doc(doc)}

    if not req.case_id:
        raise HTTPException(status_code=400, detail="Provide case_id or set create_new_client=True.")
    target = db.query(ClientCase).filter(ClientCase.case_id == req.case_id.upper()).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"Case {req.case_id} not found.")
    doc.case_id = target.case_id
    db.commit()
    return {"ok": True, "case_id": target.case_id, "created_client": False, "document": _serialize_vault_doc(doc)}


@router.delete("/documents/vault/{doc_id}")
def delete_vault_document(
    doc_id: int,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    doc = db.query(ClientDocument).filter(ClientDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Vault document not found.")
    db.delete(doc)
    db.commit()
    return {"deleted": True}


@router.get("/documents/vault/{doc_id}/file")
def serve_vault_document_file(doc_id: int, db: Session = Depends(get_db)) -> FileResponse:
    doc = db.query(ClientDocument).filter(ClientDocument.id == doc_id).first()
    if not doc or not Path(doc.file_path).exists():
        raise HTTPException(status_code=404, detail="Vault document file not found.")
    disp = "inline" if (doc.mime_type.startswith("image/") or doc.mime_type == "application/pdf") else "attachment"
    return FileResponse(
        path=doc.file_path,
        media_type=doc.mime_type,
        filename=doc.filename,
        headers={"Content-Disposition": f'{disp}; filename="{doc.filename}"'},
    )


@router.get("/documents/meta")
def get_studio_document_meta(
    source_type: str = Query(...),
    source_id: str = Query(...),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    path, title, filename, mime, case_id, parent_id = _resolve_studio_source(db, source_type, source_id)
    ext = path.suffix.lower()
    docx_paragraphs: list[str] = []
    if ext == ".docx":
        try:
            from docx import Document as DocxDocument

            docx_paragraphs = [p.text for p in DocxDocument(str(path)).paragraphs]
        except Exception:
            docx_paragraphs = []
    return {
        "source_type": source_type,
        "source_id": source_id,
        "case_id": case_id,
        "parent_doc_id": parent_id,
        "title": title,
        "filename": filename,
        "mime_type": mime,
        "file_format": ext,
        "page_count": get_pdf_page_count(path) if ext == ".pdf" else 1,
        "docx_paragraphs": docx_paragraphs,
    }


@router.get("/documents/render-page")
def render_studio_page(
    source_type: str = Query(...),
    source_id: str = Query(...),
    page: int = Query(0),
    db: Session = Depends(get_db),
) -> Response:
    path, _, _, mime, _, _ = _resolve_studio_source(db, source_type, source_id)
    if path.suffix.lower() == ".pdf":
        png = render_pdf_page_png(path, page_index=page, scale=2.0)
        return Response(content=png, media_type="image/png")
    if mime.startswith("image/") or path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return Response(content=path.read_bytes(), media_type=mime if mime.startswith("image/") else "image/png")
    raise HTTPException(status_code=400, detail="Page rendering is supported for PDF and image files.")


@router.post("/documents/studio/save")
def save_studio_edited_document(
    req: StudioSaveRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Burn text boxes, checkmarks, dates, signatures, or DOCX edits into a new versioned file in the client's vault."""
    src_path, orig_title, _, _, src_case_id, parent_id = _resolve_studio_source(db, req.source_type, req.source_id)
    target_cid = (req.case_id or src_case_id or "").upper() or None
    out_dir = (CLIENT_VAULT_DIR / target_cid) if target_cid else (CLIENT_VAULT_DIR / "_shared")

    base_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", src_path.stem)[:48]
    new_path, new_mime = burn_annotations_to_new_version(
        src_path=src_path,
        annotations=req.annotations,
        out_dir=out_dir,
        base_name=base_stem,
        docx_paragraphs=req.docx_paragraphs,
    )

    version_num = 2
    if parent_id:
        parent = db.query(ClientDocument).filter(ClientDocument.id == parent_id).first()
        if parent:
            version_num = parent.version_number + 1

    new_doc = ClientDocument(
        case_id=target_cid,
        category=req.category or "embassy_forms",
        title=req.title.strip() or f"{orig_title} (Edited v{version_num})",
        filename=new_path.name,
        file_path=str(new_path),
        mime_type=new_mime,
        size_bytes=new_path.stat().st_size,
        sha256=sha256_file(new_path),
        page_count=get_pdf_page_count(new_path),
        ai_summary=f"Edited & signed in Full-Screen Document Studio by {user.full_name} ({len(req.annotations)} annotation(s)).",
        parent_doc_id=parent_id,
        version_number=version_num,
        uploaded_by=user.full_name,
    )
    db.add(new_doc)
    if target_cid:
        db.add(
            PipelineJournal(
                case_id=target_cid,
                event_type="document_studio_saved",
                actor=user.full_name,
                summary=f"Saved edited version '{new_doc.title}' ({len(req.annotations)} overlay(s)).",
            )
        )
    db.commit()
    db.refresh(new_doc)
    return {"ok": True, "document": _serialize_vault_doc(new_doc)}


@router.post("/documents/vault/{doc_id}/rgd-92")
def convert_vault_doc_rgd_92(
    doc_id: int,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """1-Click 92% RGD Photocopy Converter — scales Jamaican birth/marriage cert cleanly on U.S. Letter PDF."""
    doc = db.query(ClientDocument).filter(ClientDocument.id == doc_id).first()
    if not doc or not Path(doc.file_path).exists():
        raise HTTPException(status_code=404, detail="Vault document not found.")
    cid = doc.case_id or "GENERAL"
    out_dir = CLIENT_VAULT_DIR / cid
    out_pdf = convert_to_rgd_92_pdf(Path(doc.file_path), out_dir, cid)

    scaled_doc = ClientDocument(
        case_id=doc.case_id,
        category="rgd_civil",
        title=f"{doc.title} (92% Kingston Embassy Scale)",
        filename=out_pdf.name,
        file_path=str(out_pdf),
        mime_type="application/pdf",
        size_bytes=out_pdf.stat().st_size,
        sha256=sha256_file(out_pdf),
        page_count=get_pdf_page_count(out_pdf),
        ai_summary="Scaled to exact 92% on U.S. Letter so Jamaican RGD top & bottom serial numbers are preserved.",
        parent_doc_id=doc.id,
        version_number=doc.version_number + 1,
        uploaded_by=user.full_name,
    )
    db.add(scaled_doc)
    if doc.case_id:
        db.add(
            PipelineJournal(
                case_id=doc.case_id,
                event_type="rgd_92_converted",
                actor=user.full_name,
                summary=f"Converted '{doc.title}' to 92% RGD Kingston-compliant PDF.",
            )
        )
    db.commit()
    db.refresh(scaled_doc)
    return {"ok": True, "document": _serialize_vault_doc(scaled_doc)}


@router.post("/clients/{case_id}/documents/fill-official")
def ai_fill_official_for_client(
    case_id: str,
    req: FillOfficialRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Select any Official Government PDF (PICA, DS-5535, DS-157, RGD BIRREQ) and AI-fill it into the client's vault."""
    cid = case_id.upper()
    client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
    if not client:
        raise HTTPException(status_code=404, detail="Case not found.")
    official = db.query(OfficialDocument).filter(OfficialDocument.doc_key == req.doc_key).first()
    if not official or not Path(official.file_path).exists():
        raise HTTPException(status_code=404, detail="Official document not found.")

    out_path, fields = ai_autofill_official_pdf(Path(official.file_path), client, CLIENT_VAULT_DIR / cid)
    mime = "application/pdf" if out_path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    filled_doc = ClientDocument(
        case_id=cid,
        category="embassy_forms",
        title=f"Auto-Filled: {official.title}",
        filename=out_path.name,
        file_path=str(out_path),
        mime_type=mime,
        size_bytes=out_path.stat().st_size,
        sha256=sha256_file(out_path),
        page_count=get_pdf_page_count(out_path),
        extracted_fields_json=json.dumps(fields),
        ai_summary=f"Pre-filled '{official.title}' from {cid}'s live profile. Open in Document Studio to fine-tune or sign.",
        uploaded_by=user.full_name,
    )
    db.add(filled_doc)
    db.add(
        PipelineJournal(
            case_id=cid,
            event_type="official_doc_autofilled",
            actor=user.full_name,
            summary=f"Auto-filled official form '{official.title}' for {cid}.",
        )
    )
    db.commit()
    db.refresh(filled_doc)
    return {"ok": True, "document": _serialize_vault_doc(filled_doc)}


@router.post("/clients/{case_id}/embassy-packet")
def build_client_embassy_packet(
    case_id: str,
    req: ExportPacketRequest = ExportPacketRequest(),
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """1-Click Embassy Packet Exporter — merges all approved forms, checklist, roadmap & vault docs into a PDF or ZIP."""
    cid = case_id.upper()
    client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
    if not client:
        raise HTTPException(status_code=404, detail="Case not found.")
    fmt = "zip" if req.bundle_format.lower() == "zip" else "pdf"
    out_path, mime, included = export_client_embassy_packet(client, bundle_format=fmt)

    asset = GeneratedAsset(
        case_id=cid,
        asset_type=f"embassy_packet_{fmt}",
        title=f"Embassy Packet Bundle ({fmt.upper()} — {len(included)} doc(s))",
        filename=out_path.name,
        file_path=str(out_path),
        mime_type=mime,
        filled_fields_json=json.dumps({"included_files": included}),
        approval_status="approved",
        approved_by=user.full_name,
        approved_at=datetime.now(timezone.utc),
        visible_to_client=True,
    )
    db.add(asset)
    db.add(
        PipelineJournal(
            case_id=cid,
            event_type="embassy_packet_exported",
            actor=user.full_name,
            summary=f"Exported {fmt.upper()} Embassy Packet containing {len(included)} document(s).",
        )
    )
    db.commit()
    db.refresh(asset)
    return {
        "ok": True,
        "id": asset.id,
        "title": asset.title,
        "filename": asset.filename,
        "mime_type": asset.mime_type,
        "included_count": len(included),
        "file_url": f"/api/assets/{asset.id}/file",
    }
