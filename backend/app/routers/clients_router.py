"""Clients Pipeline, Intake Form, Good Standing Audit, Adaptive Questionnaire & Pipeline Journal Router."""

from __future__ import annotations

import csv
import io
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.config import decrypt_value, encrypt_value
from app.database import get_db
from app.models import (
    ClientCase,
    ClientDocument,
    GeneratedAsset,
    InterviewEvent,
    InterviewPrediction,
    PipelineJournal,
    ProfileFact,
    RiskFlag,
    User,
)
from app.services.connectors import import_clients_from_csv
from app.services.obsidian import sync_client_to_obsidian
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions

router = APIRouter(prefix="/api", tags=["clients"])


def _safe_json(val: str | None, default: Any) -> Any:
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default


def serialize_client_summary(c: ClientCase) -> dict[str, Any]:
    return {
        "case_id": c.case_id,
        "access_code": c.access_code,
        "pseudonym": c.pseudonym,
        "full_name": c.full_name,
        "email": c.email,
        "phone": c.phone,
        "nationality": c.nationality,
        "parish": c.parish,
        "visa_class": c.visa_class,
        "pipeline_stage": c.pipeline_stage,
        "standing_score": c.standing_score,
        "denial_risk_level": c.denial_risk_level,
        "outcome": c.outcome,
        "outcome_evidence": c.outcome_evidence,
        "prior_us_refusals": c.prior_us_refusals,
        "embassy_interview_date": c.embassy_interview_date,
        "assigned_staff": c.assigned_staff,
        "predictions_frozen": c.predictions_frozen,
        "profile_tags": _safe_json(c.profile_tags_json, []),
        "service_package_usd": c.service_package_usd,
        "occupation": c.occupation,
        "employer_name": c.employer_name,
        "monthly_gross_jmd": c.monthly_gross_jmd,
        "monthly_net_jmd": c.monthly_net_jmd,
        "us_destination": c.us_destination,
        "purpose_of_trip": c.purpose_of_trip,
        "passport_expiry": c.passport_expiry,
        "ds160_confirmation_id": c.ds160_confirmation_id,
        "document_count": len(c.documents) + len(c.assets),
        "doc_previews": [
            {
                "id": d.id,
                "source_type": "vault",
                "title": d.title,
                "category": d.category,
                "mime_type": d.mime_type,
                "file_url": f"/api/documents/vault/{d.id}/file",
            }
            for d in sorted(c.documents, key=lambda x: x.id, reverse=True)[:4]
        ] + [
            {
                "id": a.id,
                "source_type": "asset",
                "title": a.title,
                "category": "generated",
                "mime_type": a.mime_type,
                "file_url": f"/api/assets/{a.id}/file",
            }
            for a in sorted(c.assets, key=lambda x: x.id, reverse=True)[:2]
        ],
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def serialize_client_detail(c: ClientCase, include_internal: bool = True) -> dict[str, Any]:
    base = serialize_client_summary(c)
    base.update(
        {
            "passport_number": decrypt_value(c.passport_number_enc),
            "dob": decrypt_value(c.dob_enc),
            "passport_expiry": c.passport_expiry,
            "ds160_confirmation_id": c.ds160_confirmation_id,
            "ais_appointment_barcode": c.ais_appointment_barcode,
            "intended_travel_date": c.intended_travel_date,
            "intended_return_date": c.intended_return_date,
            "purpose_of_trip": c.purpose_of_trip,
            "us_destination": c.us_destination,
            "us_host_contact": c.us_host_contact,
            "occupation": c.occupation,
            "employer_name": c.employer_name,
            "monthly_gross_jmd": c.monthly_gross_jmd,
            "monthly_net_jmd": c.monthly_net_jmd,
            "marital_status": c.marital_status,
            "children_count": c.children_count,
            "has_us_relatives": c.has_us_relatives,
            "us_relatives_details": c.us_relatives_details,
            "travel_history_summary": c.travel_history_summary,
            "refusal_statute": c.refusal_statute,
            "predictions_frozen_at": c.predictions_frozen_at.isoformat() if c.predictions_frozen_at else None,
            "predictions_frozen_by": c.predictions_frozen_by,
            "data_quality": c.data_quality,
            "open_verification_items": c.open_verification_items if include_internal else "",
            "consent_status": c.consent_status,
            "risk_flags": [
                {
                    "id": f.id,
                    "code": f.code,
                    "severity": f.severity,
                    "category": f.category,
                    "title": f.title,
                    "detail": f.detail,
                    "suggested_fix": f.suggested_fix,
                    "follow_up_question": f.follow_up_question,
                    "client_response": f.client_response,
                    "options": _safe_json(getattr(f, "options_json", "[]"), []),
                    "source_citation": f.source_citation,
                    "source_url": f.source_url,
                    "score_impact": f.score_impact,
                    "resolved": f.resolved,
                }
                for f in c.risk_flags
            ],
            "predictions": [
                {
                    "id": p.id,
                    "theme_id": p.theme_id,
                    "question_text": p.question_text,
                    "question_type": p.question_type,
                    "rank": p.rank,
                    "confidence": p.confidence,
                    "rationale": p.rationale,
                    "author": p.author,
                    "frozen_at": p.frozen_at.isoformat() if p.frozen_at else None,
                }
                for p in sorted(c.predictions, key=lambda x: (x.question_type, x.rank))
            ],
            "assets": [
                {
                    "id": a.id,
                    "asset_type": a.asset_type,
                    "title": a.title,
                    "filename": a.filename,
                    "mime_type": a.mime_type,
                    "approval_status": a.approval_status,
                    "approved_by": a.approved_by,
                    "approved_at": a.approved_at.isoformat() if a.approved_at else None,
                    "visible_to_client": a.visible_to_client,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in sorted(c.assets, key=lambda x: x.id, reverse=True)
                if include_internal or (a.approval_status == "approved" and a.visible_to_client)
            ],
            "documents": [
                {
                    "id": d.id,
                    "case_id": d.case_id,
                    "category": d.category,
                    "title": d.title,
                    "filename": d.filename,
                    "mime_type": d.mime_type,
                    "size_bytes": d.size_bytes,
                    "page_count": d.page_count,
                    "extracted_fields": _safe_json(d.extracted_fields_json, {}),
                    "ai_summary": d.ai_summary,
                    "parent_doc_id": d.parent_doc_id,
                    "version_number": d.version_number,
                    "visible_to_client": d.visible_to_client,
                    "uploaded_by": d.uploaded_by,
                    "file_url": f"/api/documents/vault/{d.id}/file",
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in sorted(c.documents, key=lambda x: x.id, reverse=True)
                if include_internal or d.visible_to_client
            ],
        }
    )
    if include_internal:
        base["facts"] = [
            {
                "id": ft.id,
                "fact_key": ft.fact_key,
                "value": ft.value,
                "as_of_date": ft.as_of_date,
                "evidence_source": ft.evidence_source,
                "confidence": ft.confidence,
                "conflict_status": ft.conflict_status,
                "resolution_note": ft.resolution_note,
            }
            for ft in sorted(c.facts, key=lambda x: x.id, reverse=True)
        ]
        base["interview_events"] = [
            {
                "id": ev.id,
                "event_mode": ev.event_mode,
                "sequence": ev.sequence,
                "theme": ev.theme,
                "question_text": ev.question_text,
                "client_answer": ev.client_answer,
                "discrepancy_type": ev.discrepancy_type,
                "verified_resolution": ev.verified_resolution,
                "source_type": ev.source_type,
                "pre_interview_predicted_theme": ev.pre_interview_predicted_theme,
                "prediction_classification": ev.prediction_classification,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in sorted(c.interview_events, key=lambda x: (x.sequence, x.id))
        ]
        base["journal"] = [
            {
                "id": j.id,
                "event_type": j.event_type,
                "actor": j.actor,
                "summary": j.summary,
                "metadata": _safe_json(j.metadata_json, {}),
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in sorted(c.journal_entries, key=lambda x: x.id, reverse=True)
        ]
    return base


class CreateClientRequest(BaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
    parish: str = "Kingston & St. Andrew"
    visa_class: str = "B1/B2"
    purpose_of_trip: str = ""
    us_destination: str = ""
    occupation: str = ""
    employer_name: str = ""
    monthly_gross_jmd: float | None = None
    monthly_net_jmd: float | None = None
    passport_number: str = ""
    passport_expiry: str = ""
    dob: str = ""
    ds160_confirmation_id: str = ""
    ais_appointment_barcode: str = ""
    marital_status: str = ""
    children_count: int = 0
    prior_us_refusals: int = 0
    has_us_relatives: bool = False
    us_relatives_details: str = ""


class UpdateClientRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    parish: str | None = None
    visa_class: str | None = None
    pipeline_stage: str | None = None
    passport_number: str | None = None
    dob: str | None = None
    passport_expiry: str | None = None
    ds160_confirmation_id: str | None = None
    ais_appointment_barcode: str | None = None
    intended_travel_date: str | None = None
    intended_return_date: str | None = None
    purpose_of_trip: str | None = None
    us_destination: str | None = None
    us_host_contact: str | None = None
    occupation: str | None = None
    employer_name: str | None = None
    monthly_gross_jmd: float | None = None
    monthly_net_jmd: float | None = None
    marital_status: str | None = None
    children_count: int | None = None
    prior_us_refusals: int | None = None
    has_us_relatives: bool | None = None
    us_relatives_details: str | None = None
    travel_history_summary: str | None = None
    embassy_interview_date: str | None = None
    open_verification_items: str | None = None
    assigned_staff: str | None = None
    service_package_usd: float | None = None
    profile_tags: list[str] | None = None


class QuestionnaireAnswerRequest(BaseModel):
    flag_id: int
    client_response: str
    mark_resolved: bool = False


class AddJournalNoteRequest(BaseModel):
    summary: str
    event_type: str = "staff_note"


class AddProfileFactRequest(BaseModel):
    fact_key: str
    value: str
    evidence_source: str = "staff_verification"
    confidence: str = "high"
    conflict_status: str = "verified"
    resolution_note: str = ""


@router.get("/clients")
def list_clients(
    stage: str | None = None,
    search: str | None = None,
    risk: str | None = None,
    visa_class: str | None = None,
    parish: str | None = None,
    sort_by: str = Query("updated_at"),
    sort_dir: str = Query("desc"),
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    q = db.query(ClientCase)
    if stage:
        q = q.filter(ClientCase.pipeline_stage == stage)
    if risk:
        q = q.filter(ClientCase.denial_risk_level == risk.lower())
    if visa_class:
        q = q.filter(ClientCase.visa_class.ilike(f"%{visa_class}%"))
    if parish:
        q = q.filter(ClientCase.parish.ilike(f"%{parish}%"))
    rows = q.order_by(ClientCase.id.desc()).all()
    if search:
        s = search.strip().lower()
        rows = [
            r
            for r in rows
            if s in r.case_id.lower()
            or s in (r.full_name or "").lower()
            or s in (r.pseudonym or "").lower()
            or s in (r.profile_tags_json or "").lower()
            or s in (r.visa_class or "").lower()
            or s in (r.parish or "").lower()
            or s in (r.occupation or "").lower()
        ]

    risk_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    def _key(c: ClientCase):
        if sort_by == "standing_score":
            return c.standing_score
        if sort_by == "denial_risk_level":
            return risk_rank.get((c.denial_risk_level or "").lower(), 0)
        if sort_by == "full_name":
            return (c.full_name or c.pseudonym or "").lower()
        if sort_by == "monthly_gross_jmd":
            return c.monthly_gross_jmd or 0.0
        if sort_by == "embassy_interview_date":
            return c.embassy_interview_date or "9999-12-31"
        if sort_by == "pipeline_stage":
            return c.pipeline_stage or ""
        if sort_by == "case_id":
            return c.case_id
        return c.updated_at.timestamp() if c.updated_at else float(c.id)

    rows.sort(key=_key, reverse=(sort_dir.lower() == "desc"))
    return [serialize_client_summary(r) for r in rows]


@router.get("/clients/export/xlsx")
def export_clients_xlsx(
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> Response:
    """Export all clients as a styled Excel (.xlsx) workbook with document counts & visa metrics."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jahtaria Clients"

    headers = [
        "Case ID", "Full Name", "Visa Class", "Stage", "Good Standing %", "Denial Risk", "Outcome",
        "Parish", "Email", "Phone", "Occupation", "Employer", "Monthly Gross JMD", "Monthly Net JMD",
        "U.S. Destination", "Purpose of Trip", "Passport Expiry", "DS-160 Barcode", "Interview Date",
        "Prior Refusals", "Vault Docs",
    ]
    ws.append(headers)
    hdr_fill = PatternFill(start_color="1A472A", end_color="1A472A", fill_type="solid")
    hdr_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")

    for c in db.query(ClientCase).order_by(ClientCase.id.desc()).all():
        ws.append([
            c.case_id, c.full_name or c.pseudonym, c.visa_class, c.pipeline_stage, c.standing_score,
            c.denial_risk_level, c.outcome, c.parish, c.email, c.phone, c.occupation, c.employer_name,
            c.monthly_gross_jmd, c.monthly_net_jmd, c.us_destination, c.purpose_of_trip,
            c.passport_expiry, c.ds160_confirmation_id, c.embassy_interview_date, c.prior_us_refusals,
            len(c.documents) + len(c.assets),
        ])

    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(38, max(12, max_len + 3))

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="jahtaria_clients.xlsx"'},
    )


@router.get("/clients/export/csv")
def export_clients_csv(
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "case_id", "full_name", "visa_class", "pipeline_stage", "standing_score", "denial_risk_level",
        "outcome", "parish", "email", "phone", "occupation", "employer_name", "monthly_gross_jmd",
        "monthly_net_jmd", "us_destination", "purpose_of_trip", "passport_expiry", "ds160_confirmation_id",
        "embassy_interview_date", "prior_us_refusals", "document_count",
    ])
    for c in db.query(ClientCase).order_by(ClientCase.id.desc()).all():
        writer.writerow([
            c.case_id, c.full_name or c.pseudonym, c.visa_class, c.pipeline_stage, c.standing_score,
            c.denial_risk_level, c.outcome, c.parish, c.email, c.phone, c.occupation, c.employer_name,
            c.monthly_gross_jmd, c.monthly_net_jmd, c.us_destination, c.purpose_of_trip,
            c.passport_expiry, c.ds160_confirmation_id, c.embassy_interview_date, c.prior_us_refusals,
            len(c.documents) + len(c.assets),
        ])
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jahtaria_clients.csv"'},
    )


@router.post("/clients/import/spreadsheet")
async def import_clients_spreadsheet(
    file: UploadFile = File(...),
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Import clients directly from an uploaded .xlsx Excel workbook or .csv file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    raw = await file.read()
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = list(ws.iter_rows(values_only=True))
        if not rows_iter:
            return {"imported_count": 0, "skipped_count": 0, "case_ids": []}
        buf = io.StringIO()
        w = csv.writer(buf)
        for r in rows_iter:
            w.writerow(["" if v is None else str(v) for v in r])
        csv_text = buf.getvalue()
    else:
        csv_text = raw.decode("utf-8", errors="replace")
    return import_clients_from_csv(db, csv_text, actor=user.full_name)


@router.post("/clients")
def create_client(
    req: CreateClientRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    next_num = db.query(ClientCase).count() + 1
    case_id = f"C{next_num:03d}"
    while db.query(ClientCase).filter(ClientCase.case_id == case_id).first():
        next_num += 1
        case_id = f"C{next_num:03d}"

    c = ClientCase(
        case_id=case_id,
        access_code=f"JAH-{case_id}",
        pseudonym=req.full_name.strip(),
        full_name=req.full_name.strip(),
        email=req.email.strip(),
        phone=req.phone.strip(),
        parish=req.parish.strip(),
        visa_class=req.visa_class.strip() or "B1/B2",
        purpose_of_trip=req.purpose_of_trip.strip(),
        us_destination=req.us_destination.strip(),
        occupation=req.occupation.strip(),
        employer_name=req.employer_name.strip(),
        monthly_gross_jmd=req.monthly_gross_jmd,
        monthly_net_jmd=req.monthly_net_jmd,
        passport_number_enc=encrypt_value(req.passport_number.strip()),
        dob_enc=encrypt_value(req.dob.strip()),
        passport_expiry=req.passport_expiry.strip(),
        ds160_confirmation_id=req.ds160_confirmation_id.strip().upper(),
        ais_appointment_barcode=req.ais_appointment_barcode.strip().upper(),
        marital_status=req.marital_status.strip(),
        children_count=req.children_count,
        prior_us_refusals=req.prior_us_refusals,
        has_us_relatives=req.has_us_relatives,
        us_relatives_details=req.us_relatives_details.strip(),
        pipeline_stage="new_intake",
        assigned_staff=user.full_name,
    )
    db.add(c)
    db.flush()
    db.add(
        PipelineJournal(
            case_id=case_id,
            event_type="client_created",
            actor=user.full_name,
            summary=f"Created new visa case {case_id} for {c.full_name} ({c.visa_class}). Access code: {c.access_code}.",
        )
    )
    db.commit()
    evaluate_client_standing(db, c)
    generate_ranked_predictions(db, c, author=user.full_name)
    sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    db.refresh(c)
    return serialize_client_detail(c, include_internal=True)


@router.get("/portal/my-case")
def get_customer_own_case(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    cid = user.linked_case_id or "C034"
    c = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Linked client case not found.")
    return serialize_client_detail(c, include_internal=False)


@router.get("/clients/{case_id}")
def get_client(case_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Customers may only view their own case.")
    return serialize_client_detail(c, include_internal=(user.role in ("staff", "ceo")))


@router.patch("/clients/{case_id}")
def update_client(
    case_id: str,
    req: UpdateClientRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    data = req.model_dump(exclude_unset=True)
    changed_fields: list[str] = []

    # Customers cannot change staff-only pipeline fields
    if user.role == "customer":
        for restricted in ("pipeline_stage", "assigned_staff", "service_package_usd", "open_verification_items"):
            data.pop(restricted, None)

    for k, v in data.items():
        if k == "passport_number":
            c.passport_number_enc = encrypt_value(v or "")
            changed_fields.append("passport_number (encrypted)")
        elif k == "dob":
            c.dob_enc = encrypt_value(v or "")
            changed_fields.append("dob (encrypted)")
        elif k == "profile_tags" and isinstance(v, list):
            c.profile_tags_json = json.dumps(v)
            changed_fields.append("profile_tags")
        elif hasattr(c, k):
            setattr(c, k, v)
            changed_fields.append(k)

    if changed_fields:
        db.add(
            PipelineJournal(
                case_id=c.case_id,
                event_type="profile_updated",
                actor=user.full_name,
                summary=f"Updated client fields: {', '.join(changed_fields)}.",
            )
        )
    db.commit()
    evaluate_client_standing(db, c)
    if not c.predictions_frozen:
        generate_ranked_predictions(db, c, author=user.full_name)
    sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    db.refresh(c)
    return serialize_client_detail(c, include_internal=(user.role in ("staff", "ceo")))


@router.post("/clients/{case_id}/audit")
def run_audit(
    case_id: str,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    result = evaluate_client_standing(db, c)
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="risk_audit",
            actor=user.full_name,
            summary=f"Re-ran U.S. Embassy Kingston Good Standing audit: {result['standing_score']}% ({result['red_count']} red, {result['amber_count']} amber).",
        )
    )
    db.commit()
    sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    return result


@router.post("/clients/{case_id}/questionnaire")
def submit_questionnaire_answer(
    case_id: str,
    req: QuestionnaireAnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    flag = db.query(RiskFlag).filter(RiskFlag.id == req.flag_id, RiskFlag.case_id == c.case_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Questionnaire item not found.")

    flag.client_response = req.client_response.strip()
    if req.mark_resolved and user.role in ("staff", "ceo"):
        flag.resolved = True
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="questionnaire_response",
            actor=user.full_name,
            summary=f"Answered follow-up [{flag.code}]: {flag.client_response[:140]}",
        )
    )
    db.commit()
    evaluate_client_standing(db, c)
    db.refresh(c)
    return serialize_client_detail(c, include_internal=(user.role in ("staff", "ceo")))


@router.post("/clients/{case_id}/journal")
def add_journal_note(
    case_id: str,
    req: AddJournalNoteRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    entry = PipelineJournal(
        case_id=c.case_id,
        event_type=req.event_type,
        actor=user.full_name,
        summary=req.summary.strip(),
    )
    db.add(entry)
    db.commit()
    sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    return {"id": entry.id, "summary": entry.summary, "actor": entry.actor, "created_at": entry.created_at.isoformat()}


@router.post("/clients/{case_id}/facts")
def add_profile_fact(
    case_id: str,
    req: AddProfileFactRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    fact = ProfileFact(
        case_id=c.case_id,
        fact_key=req.fact_key.strip(),
        value=req.value.strip(),
        evidence_source=req.evidence_source.strip(),
        confidence=req.confidence.strip(),
        conflict_status=req.conflict_status.strip(),
        resolution_note=req.resolution_note.strip(),
    )
    db.add(fact)
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="fact_recorded",
            actor=user.full_name,
            summary=f"Recorded provenance fact '{fact.fact_key}' = '{fact.value}' ({fact.evidence_source}, {fact.conflict_status}).",
        )
    )
    db.commit()
    return {"id": fact.id, "fact_key": fact.fact_key, "value": fact.value}
