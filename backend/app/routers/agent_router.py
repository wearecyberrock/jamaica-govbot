"""Unified Agent-First Router: Saved Conversations, Dynamic AI Questionnaires, CEO Preview/Confirm/Undo Edits & File Drop."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.config import BLUEPRINTS_DIR, CLIENT_VAULT_DIR, encrypt_value
from app.database import get_db
from app.models import (
    BrandingConfig,
    ChatMessage,
    ClientCase,
    ClientDocument,
    Conversation,
    GeneratedAsset,
    OfficialDocument,
    PendingAction,
    PipelineJournal,
    RiskFlag,
    User,
)
from app.services.connectors import save_mcp_servers, set_setting
from app.services.doc_generator import inspect_blueprint_file, sha256_file
from app.services.doc_intelligence import get_pdf_page_count, scan_document_with_ai
from app.services.hermes_engine import (
    answer_customer_question,
    call_llm,
    load_conversation_history,
    run_staff_agent_loop,
)
from app.services.file_synthesizer import (
    _extract_text_from_bytes,
    _parse_structured_clients,
    synthesize_clients_from_text,
    synthesize_zip_archive,
)
from app.services.obsidian import sync_client_to_obsidian
from app.services.risk_engine import evaluate_client_standing
from app.services.smart_paste import (
    build_dynamic_data_table,
    detect_and_apply_smart_paste,
    detect_chat_delete_or_reset,
    detect_chat_gmail_command,
    detect_natural_client_crud,
)

router = APIRouter(prefix="/api", tags=["agent"])


class UnifiedCommandRequest(BaseModel):
    message: str
    mode: str = "chat"  # chat | task
    case_id: str | None = None
    conversation_id: str | None = None


class CreateConversationRequest(BaseModel):
    title: str = "New Conversation"
    case_id: str | None = None


class GenerateQuestionsRequest(BaseModel):
    focus: str = ""
    count: int = 5


def _safe_options(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()][:6]
    except Exception:
        pass
    return []


def _default_options_for_flag(f: RiskFlag) -> list[str]:
    """Provide helpful multiple-choice options when a legacy RiskFlag has no saved options_json."""
    existing = _safe_options(getattr(f, "options_json", "[]"))
    if existing:
        return existing
    text = f"{f.title} {f.follow_up_question}".lower()
    if "passport" in text:
        return ["Valid > 6 months beyond travel", "Expires in under 6 months (need PICA renewal)", "Renewal currently in progress", "Not yet checked"]
    if "ds-160" in text or "barcode" in text or "ais" in text:
        return ["DS-160 AA-barcode matches AIS profile", "Need to update AIS profile barcode", "DS-160 not submitted yet", "Need staff verification"]
    if "salary" in text or "gross" in text or "income" in text or "pay" in text:
        return ["Matches monthly gross on payslips", "Listed net take-home instead of gross", "Self-employed / variable monthly income", "Need to verify with HR / payslips"]
    if "refus" in text or "214" in text:
        return ["Never refused a U.S. visa", "Refused once — circumstances improved", "Refused 2+ times — ready to disclose dates", "Unsure of prior refusal date"]
    if "relative" in text or "family" in text:
        return ["No relatives in the U.S.", "Immediate family in the U.S. (will disclose)", "Extended relatives only", "Need to confirm exact relationship/status"]
    if "fund" in text or "bank" in text or "sponsor" in text:
        return ["Self-funded from personal savings/salary", "Employer-funded business trip", "Immediate family / host sponsoring", "Shared funding (self + sponsor)"]
    return ["Verified & matches documents", "Needs update on DS-160", "Need supporting document", "Will provide details below"]


def _serialize_questionnaire_payload(c: ClientCase) -> dict[str, Any]:
    """Serialize all follow-up questionnaire items for a client (used by both Side Panel and Chat Card)."""
    items = []
    for f in c.risk_flags:
        if not (f.follow_up_question or "").strip():
            continue
        items.append(
            {
                "flag_id": f.id,
                "code": f.code,
                "title": f.title,
                "question": f.follow_up_question,
                "explanation": f.detail or "Helps verify truthful consistency for your DS-160 and U.S. Embassy Kingston interview.",
                "tip": f.suggested_fix or "Answer truthfully and keep dates/amounts consistent with your supporting documents.",
                "options": _default_options_for_flag(f),
                "client_response": f.client_response or "",
                "resolved": bool(f.resolved),
                "severity": f.severity or "amber",
                "source_citation": f.source_citation or "Consular Verification",
            }
        )
    return {
        "case_id": c.case_id,
        "client_name": c.full_name or c.pseudonym,
        "visa_class": c.visa_class,
        "standing_score": c.standing_score,
        "total_count": len(items),
        "answered_count": sum(1 for i in items if i["client_response"].strip() or i["resolved"]),
        "items": items,
    }


def _extract_requested_question_count(msg: str, default: int = 5) -> int:
    """Extract requested count from phrases like 'generate 100 questions', 'give me 25 follow-up questions', '500 questions'."""
    m = re.search(r"\b(\d{1,4})\s+(?:[a-z-]+\s+){0,3}(?:question|scenario|senario|item)", msg, re.I)
    if not m:
        m = re.search(r"(?:generate|genereate|prepare|create|make|give\s+me|add)\s+(\d{1,4})\b", msg, re.I)
    if m:
        n = int(m.group(1))
        return max(1, min(n, 1000))
    return default


def _detect_case_id(db: Session, text: str, fallback: str | None) -> str | None:
    """Detect case IDs tolerating common typos like CO33, co27, C-034, case 34, or client names."""
    upper = text.upper()
    # Match C034, CO34 (letter O instead of zero), C-034, C34
    m = re.search(r"\bC[-\s]?[0O]?(\d{1,3})\b", upper)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 999:
            return f"C{num:03d}"
    # Match "case 33", "case #27"
    m_case = re.search(r"\bCASE\s*#?\s*0?(\d{1,3})\b", upper)
    if m_case:
        num = int(m_case.group(1))
        if 1 <= num <= 999:
            return f"C{num:03d}"
    low = text.lower()
    if len(low) >= 4:
        for c in db.query(ClientCase).all():
            nm = (c.full_name or "").lower()
            if nm and not nm.startswith("reference case"):
                parts = [p for p in nm.split() if len(p) >= 4]
                if any(p in low for p in parts):
                    return c.case_id
    return fallback


def _wants_questionnaire_generation(low: str) -> bool:
    """Fuzzy detection for generating/preparing follow-up questions or a questionnaire (tolerates typos)."""
    has_action = any(k in low for k in ("generat", "genereat", "creat", "prepar", "make", "build", "add", "new"))
    has_q_word = any(
        k in low
        for k in (
            "questionn",
            "questiona",
            "follow-up",
            "followup",
            "folloup",
            "follow up",
            "questions",
            "question for",
            "on the fly",
        )
    )
    return has_action and has_q_word


def _wants_explicit_panel_only(low: str) -> bool:
    """True only when the user typed a short bare navigation command like 'open case c033' or 'CO33'."""
    stripped = re.sub(r"[^a-z0-9\s]", "", low).strip()
    if re.fullmatch(r"(?:open\s+|show\s+|view\s+|go\s+to\s+)?(?:case\s+)?c[0o]?\d{1,3}", stripped):
        return True
    return False


def _match_official_pdf(db: Session, low: str) -> str | None:
    docs = db.query(OfficialDocument).all()
    if "5535" in low:
        return "us_dos_ds5535"
    if "157" in low:
        return "us_dos_ds157"
    if "156" in low:
        return "us_dos_ds156e"
    if "renew" in low and ("pica" in low or "passport" in low):
        return "pica_adult_renewal_simplified"
    if "birth" in low or "rgd" in low or "birreq" in low:
        return "rgd_birth_cert_birreq"
    if "descent" in low or "citizenship" in low:
        return "pica_citizenship_descent"
    if "declaration" in low:
        return "pica_declaration_form"
    if "pica" in low or "passport" in low:
        return "pica_passport_full_form"
    return docs[0].doc_key if docs else None


def _detect_ceo_conversational_edit(
    db: Session,
    user: User,
    msg: str,
    target_cid: str | None,
) -> PendingAction | None:
    """Detect CEO/Staff conversational edit requests and build a 1-click Preview/Confirm + Undo card."""
    if user.role not in ("ceo", "staff"):
        return None
    low = msg.lower()

    # 1. CEO Branding change: "change agency name to ..."
    if user.role == "ceo":
        m_brand = re.search(r"(?:change|rename|set|update)\s+(?:the\s+)?agency(?:\s+name)?\s+to\s+[\"']?([^\"'\n.]{3,80})[\"']?", msg, re.I)
        if m_brand:
            new_name = m_brand.group(1).strip()
            b = db.query(BrandingConfig).first()
            old_name = b.agency_name if b else "Jahtaria Travel Services"
            act = PendingAction(
                user_id=user.id,
                action_type="update_branding",
                target_ref="branding",
                summary=f"Change Agency Name from '{old_name}' → '{new_name}'",
                before_json=json.dumps({"agency_name": old_name}),
                after_json=json.dumps({"agency_name": new_name}),
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            return act

    # 2. Client field update / rename: "rename C032 to Devon Brown", "update C034 gross salary to 310000", "change C034 destination to Atlanta"
    if target_cid:
        client = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first()
        if not client:
            return None
        updates: dict[str, Any] = {}
        before: dict[str, Any] = {}

        m_ren = re.search(r"(?:rename|change\s+name\s+(?:of\s+)?)\s*(?:case\s+)?C\d{3}\s+to\s+[\"']?([^\"'\n.]{2,80})[\"']?", msg, re.I)
        if m_ren:
            before["full_name"] = client.full_name
            updates["full_name"] = m_ren.group(1).strip()

        m_gross = re.search(r"(?:gross\s*(?:salary|income)?|salary)\s*(?:to|=)\s*(?:jmd\s*)?\$?([\d,]+)", msg, re.I)
        if m_gross:
            before["monthly_gross_jmd"] = client.monthly_gross_jmd
            updates["monthly_gross_jmd"] = float(m_gross.group(1).replace(",", ""))

        m_net = re.search(r"net\s*(?:salary|income|pay)?\s*(?:to|=)\s*(?:jmd\s*)?\$?([\d,]+)", msg, re.I)
        if m_net:
            before["monthly_net_jmd"] = client.monthly_net_jmd
            updates["monthly_net_jmd"] = float(m_net.group(1).replace(",", ""))

        m_dest = re.search(r"destination\s*(?:to|=)\s*[\"']?([^\"'\n.]{2,60})[\"']?", msg, re.I)
        if m_dest:
            before["us_destination"] = client.us_destination
            updates["us_destination"] = m_dest.group(1).strip()

        m_exp = re.search(r"passport\s*expir(?:y|ation)\s*(?:to|=)\s*(\d{4}-\d{2}-\d{2})", msg, re.I)
        if m_exp:
            before["passport_expiry"] = client.passport_expiry
            updates["passport_expiry"] = m_exp.group(1).strip()

        m_ds = re.search(r"(?:ds-?160|barcode)\s*(?:to|=)\s*(AA[A-Z0-9]{4,14})", msg, re.I)
        if m_ds:
            before["ds160_confirmation_id"] = client.ds160_confirmation_id
            updates["ds160_confirmation_id"] = m_ds.group(1).upper()

        m_purp = re.search(r"purpose(?:\s+of\s+trip)?\s*(?:to|=)\s*[\"']?([^\"'\n.]{3,120})[\"']?", msg, re.I)
        if m_purp:
            before["purpose_of_trip"] = client.purpose_of_trip
            updates["purpose_of_trip"] = m_purp.group(1).strip()

        if updates:
            diff_str = ", ".join(f"{k}: {before.get(k)!r} → {v!r}" for k, v in updates.items())
            act = PendingAction(
                user_id=user.id,
                action_type="update_client",
                target_ref=client.case_id,
                summary=f"Update {client.case_id} ({diff_str})",
                before_json=json.dumps(before),
                after_json=json.dumps(updates),
            )
            db.add(act)
            db.commit()
            db.refresh(act)
            return act

    return None


def _serialize_action(a: PendingAction) -> dict[str, Any]:
    return {
        "id": a.id,
        "action_type": a.action_type,
        "target_ref": a.target_ref,
        "summary": a.summary,
        "before": json.loads(a.before_json or "{}"),
        "after": json.loads(a.after_json or "{}"),
        "status": a.status,
    }


# ── Saved Multi-Conversation History ─────────────────────────────────────────

@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(30).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "case_id": c.case_id,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in rows
    ]


@router.post("/conversations")
def create_conversation(
    req: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cid = f"conv_{secrets.token_hex(6)}"
    conv = Conversation(id=cid, user_id=user.id, title=req.title.strip() or "New Conversation", case_id=req.case_id)
    db.add(conv)
    db.commit()
    return {"id": conv.id, "title": conv.title, "case_id": conv.case_id}


@router.get("/conversations/{conv_id}/messages")
def get_conversation_messages(
    conv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    rows = db.query(ChatMessage).filter(ChatMessage.session_id == conv_id).order_by(ChatMessage.id.asc()).all()
    out = []
    for m in rows:
        meta = {}
        try:
            meta = json.loads(m.tool_trace_json or "{}")
        except Exception:
            meta = {}
        out.append(
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content,
                "provider_used": m.provider_used,
                "tool_trace": meta.get("tool_trace", []) if isinstance(meta, dict) else [],
                "citations": meta.get("citations", []) if isinstance(meta, dict) else [],
                "created_assets": meta.get("created_assets", []) if isinstance(meta, dict) else [],
                "panel": meta.get("panel") if isinstance(meta, dict) else None,
                "pending_action": meta.get("pending_action") if isinstance(meta, dict) else None,
                "questionnaire": meta.get("questionnaire") if isinstance(meta, dict) else None,
                "data_table": meta.get("data_table") if isinstance(meta, dict) else None,
                "vault_doc": meta.get("vault_doc") if isinstance(meta, dict) else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return out


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if conv:
        db.query(ChatMessage).filter(ChatMessage.session_id == conv_id).delete()
        db.delete(conv)
        db.commit()
    return {"deleted": True}


# ── CEO / Staff Conversational Edit Confirm & Undo ───────────────────────────

@router.post("/actions/{action_id}/confirm")
def confirm_pending_action(
    action_id: int,
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    act = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not act or act.status != "pending":
        raise HTTPException(status_code=404, detail="Pending action not found or already processed.")

    after = json.loads(act.after_json or "{}")
    if act.action_type == "update_branding" and user.role == "ceo":
        b = db.query(BrandingConfig).first()
        if b:
            for k, v in after.items():
                if hasattr(b, k):
                    setattr(b, k, v)
    elif act.action_type == "update_client":
        c = db.query(ClientCase).filter(ClientCase.case_id == act.target_ref).first()
        if c:
            for k, v in after.items():
                if k == "passport_number":
                    c.passport_number_enc = encrypt_value(str(v))
                elif k == "dob":
                    c.dob_enc = encrypt_value(str(v))
                elif hasattr(c, k):
                    setattr(c, k, v)
            db.add(PipelineJournal(case_id=c.case_id, event_type="ai_edit_confirmed", actor=user.full_name, summary=f"Confirmed AI edit: {act.summary}"))
            db.commit()
            evaluate_client_standing(db, c)
            sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    elif act.action_type == "create_client":
        count = db.query(ClientCase).count()
        cid = f"C{count + 1:03d}"
        while db.query(ClientCase).filter(ClientCase.case_id == cid).first():
            count += 1
            cid = f"C{count + 1:03d}"
        full_name = str(after.get("full_name") or f"New Client {cid}")
        c = ClientCase(
            case_id=cid,
            access_code=f"JAH-{cid}-{secrets.token_hex(2).upper()}",
            pseudonym=full_name,
            full_name=full_name,
            pipeline_stage="new_intake",
            assigned_staff=user.full_name,
        )
        for k, v in after.items():
            if k == "passport_number":
                c.passport_number_enc = encrypt_value(str(v))
            elif k == "dob":
                c.dob_enc = encrypt_value(str(v))
            elif hasattr(c, k):
                setattr(c, k, v)
        db.add(c)
        db.flush()
        act.target_ref = cid
        act.before_json = json.dumps({"created_case_id": cid})
        db.add(PipelineJournal(case_id=cid, event_type="ai_client_created", actor=user.full_name, summary=f"Created client {cid} ({full_name}) via chat confirm."))
        db.commit()
        evaluate_client_standing(db, c)
        sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    elif act.action_type in ("bulk_create_clients", "bulk_create_clients_with_files"):
        import shutil as _shutil

        created_ids = []
        created_doc_ids = []
        for item in after.get("clients") or []:
            count = db.query(ClientCase).count()
            cid = f"C{count + 1:03d}"
            while db.query(ClientCase).filter(ClientCase.case_id == cid).first():
                count += 1
                cid = f"C{count + 1:03d}"
            nm = str(item.get("full_name") or f"Imported {cid}")
            c = ClientCase(
                case_id=cid,
                access_code=f"JAH-{cid}-{secrets.token_hex(2).upper()}",
                pseudonym=nm,
                full_name=nm,
                email=str(item.get("email") or ""),
                phone=str(item.get("phone") or ""),
                parish=str(item.get("parish") or "Kingston & St. Andrew"),
                visa_class=str(item.get("visa_class") or "B1/B2"),
                occupation=str(item.get("occupation") or ""),
                employer_name=str(item.get("employer_name") or ""),
                us_destination=str(item.get("us_destination") or ""),
                purpose_of_trip=str(item.get("purpose_of_trip") or ""),
                passport_expiry=str(item.get("passport_expiry") or ""),
                embassy_interview_date=str(item.get("embassy_interview_date") or ""),
                ds160_confirmation_id=str(item.get("ds160_confirmation_id") or ""),
                monthly_gross_jmd=item.get("monthly_gross_jmd"),
                monthly_net_jmd=item.get("monthly_net_jmd"),
                pipeline_stage="data_synced",
                assigned_staff=user.full_name,
            )
            if item.get("passport_number"):
                c.passport_number_enc = encrypt_value(str(item["passport_number"]))
            if item.get("dob"):
                c.dob_enc = encrypt_value(str(item["dob"]))
            db.add(c)
            db.flush()
            evaluate_client_standing(db, c)
            created_ids.append(cid)

            # Attach any ZIP-matched files directly into the newly synthesized client's Vault!
            for mf in item.get("_matched_files") or []:
                sp = Path(mf.get("staged_path", ""))
                if sp.exists() and sp.is_file():
                    dest_dir = CLIENT_VAULT_DIR / cid
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / sp.name
                    _shutil.copy2(sp, dest)
                    ext_f = dest.suffix.lower()
                    mime_f = "application/pdf" if ext_f == ".pdf" else ("image/png" if ext_f in (".png", ".jpg", ".jpeg", ".webp") else "application/octet-stream")
                    vdoc = ClientDocument(
                        case_id=cid,
                        category="photos_other",
                        title=mf.get("filename") or dest.stem,
                        filename=mf.get("filename") or dest.name,
                        file_path=str(dest),
                        mime_type=mime_f,
                        size_bytes=dest.stat().st_size,
                        sha256=sha256_file(dest),
                        page_count=get_pdf_page_count(dest),
                        uploaded_by=f"ZIP Synthesizer ({user.full_name})",
                    )
                    db.add(vdoc)
                    db.flush()
                    created_doc_ids.append(vdoc.id)
        act.before_json = json.dumps({"created_case_ids": created_ids, "created_doc_ids": created_doc_ids})
        db.commit()
    elif act.action_type == "delete_client":
        c = db.query(ClientCase).filter(ClientCase.case_id == act.target_ref).first()
        if c:
            db.delete(c)
            db.commit()
    elif act.action_type == "bulk_delete_clients":
        for cid in after.get("case_ids") or []:
            c = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
            if c:
                db.delete(c)
        db.commit()
    elif act.action_type == "wipe_all_clients":
        if user.role != "ceo" and not bool(getattr(user, "all_tiers", False)):
            raise HTTPException(status_code=403, detail="Only CEO can wipe all client data.")
        for c in db.query(ClientCase).all():
            db.delete(c)
        db.query(ClientDocument).delete()
        db.commit()
    elif act.action_type == "reset_seed_data":
        if user.role != "ceo" and not bool(getattr(user, "all_tiers", False)):
            raise HTTPException(status_code=403, detail="Only CEO can restore pristine seed data.")
        from app.seed import reset_seed_clients_to_pristine

        reset_seed_clients_to_pristine(db)

    act.status = "applied"
    act.applied_at = datetime.now(timezone.utc)
    db.commit()
    return _serialize_action(act)


@router.post("/actions/{action_id}/undo")
def undo_applied_action(
    action_id: int,
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    act = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not act or act.status != "applied":
        raise HTTPException(status_code=404, detail="Action cannot be undone.")

    before = json.loads(act.before_json or "{}")
    if act.action_type == "update_branding" and user.role == "ceo":
        b = db.query(BrandingConfig).first()
        if b:
            for k, v in before.items():
                if hasattr(b, k):
                    setattr(b, k, v)
    elif act.action_type == "update_client":
        c = db.query(ClientCase).filter(ClientCase.case_id == act.target_ref).first()
        if c:
            for k, v in before.items():
                if k in ("passport_number", "dob"):
                    continue
                if hasattr(c, k):
                    setattr(c, k, v)
            db.add(PipelineJournal(case_id=c.case_id, event_type="ai_edit_undone", actor=user.full_name, summary=f"Undid AI edit: {act.summary}"))
            db.commit()
            evaluate_client_standing(db, c)
            sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)
    elif act.action_type == "create_client":
        cid = before.get("created_case_id") or act.target_ref
        c = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
        if c:
            db.delete(c)
    elif act.action_type in ("bulk_create_clients", "bulk_create_clients_with_files"):
        for cid in before.get("created_case_ids") or []:
            c = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
            if c:
                db.delete(c)
        for did in before.get("created_doc_ids") or []:
            d = db.query(ClientDocument).filter(ClientDocument.id == did).first()
            if d:
                db.delete(d)
    elif act.action_type == "delete_client":
        snap = before.get("client")
        if isinstance(snap, dict) and snap.get("case_id"):
            if not db.query(ClientCase).filter(ClientCase.case_id == snap["case_id"]).first():
                restored = ClientCase(**{k: v for k, v in snap.items() if hasattr(ClientCase, k)})
                db.add(restored)
                db.flush()
                evaluate_client_standing(db, restored)
    elif act.action_type in ("bulk_delete_clients", "wipe_all_clients"):
        for snap in before.get("clients") or []:
            if isinstance(snap, dict) and snap.get("case_id"):
                if not db.query(ClientCase).filter(ClientCase.case_id == snap["case_id"]).first():
                    restored = ClientCase(**{k: v for k, v in snap.items() if hasattr(ClientCase, k)})
                    db.add(restored)
                    db.flush()
                    evaluate_client_standing(db, restored)
    elif act.action_type == "update_setting":
        for k, v in before.items():
            is_sec = any(x in k.lower() for x in ("key", "token", "secret"))
            set_setting(db, k, str(v or ""), is_secret=is_sec, category="ai")
    elif act.action_type == "update_mcp_servers":
        save_mcp_servers(db, before.get("servers") or [])
    elif act.action_type == "add_gov_source":
        from app.models import GovSource

        sk = before.get("source_key") or act.target_ref
        src = db.query(GovSource).filter(GovSource.source_key == sk).first()
        if src:
            db.delete(src)

    act.status = "undone"
    db.commit()
    return _serialize_action(act)


@router.post("/actions/{action_id}/cancel")
def cancel_pending_action(
    action_id: int,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    act = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not act:
        raise HTTPException(status_code=404, detail="Action not found.")
    act.status = "cancelled"
    db.commit()
    return _serialize_action(act)


# ── AI-in-the-Loop Dynamic Questionnaire Generator (Unlimited N Questions!) ──

_CONSULAR_BANK_SEEDS: list[tuple[str, str, str, str, list[str]]] = [
    ("Home Ties & Return Commitment", "What specific job duties, property ownership, or family commitments require your return to Jamaica immediately after your trip?", "Under INA 214(b), Kingston Consular Officers evaluate concrete social and economic ties to Jamaica.", "Give 2–3 concrete, verifiable ties (employer letter, children's school, property/lease, or ongoing business).", ["Full-time job with approved leave", "Business owner with active local clients", "Property / lease + dependent family in Jamaica", "University enrollment + family ties"]),
    ("Trip Funding & Budget Alignment", "Who is paying for your flight, hotel, and daily expenses, and does your bank balance comfortably match that budget?", "Officers compare stated trip cost against monthly JMD salary and savings to ensure financial feasibility.", "Know your approximate USD budget and match it cleanly to your bank statements or sponsor's letter.", ["100% self-funded from personal salary/savings", "Employer-funded business travel", "Immediate family / host covering lodging", "Shared funding (self + sponsor)"]),
    ("Gross vs. Net Monthly Income", "Does the monthly salary figure on your DS-160 reflect your monthly GROSS income in JMD before NIS/NHT/PAYE deductions?", "Form DS-160 asks for monthly gross income; confusing net take-home with gross causes unnecessary discrepancies.", "Bring your last 3 payslips and be ready to state both gross and net figures clearly.", ["Yes — DS-160 shows exact monthly gross JMD", "No — currently lists net take-home (will update)", "Self-employed (using average monthly revenue/draw)", "Unemployed / student / retired"]),
    ("DS-160 & AIS Barcode Matching", "Have you confirmed that the AA-prefixed barcode on your printed DS-160 confirmation page exactly matches your AIS Kingston appointment profile?", "Effective April 1, 2025, U.S. Embassy Kingston denies entry if the DS-160 barcode does not match AIS.", "Check every character of your AA... code at ais.usvisa-info.com/en-jm/niv at least 48 hours before interview.", ["Confirmed exact AA-barcode match", "Need to update AIS profile with latest DS-160", "DS-160 draft not submitted yet", "Need staff double-check"]),
    ("Jamaican Passport 6-Month Validity", "Is your Jamaican passport undamaged and valid for at least 6 months beyond your intended U.S. travel date?", "Both PICA and the U.S. Embassy require an undamaged passport with sufficient remaining validity.", "If under 6 months remaining, renew via PICA Simplified Adult Renewal Form 1 before scheduling.", ["Valid > 1 year beyond trip", "Valid 6–12 months beyond trip", "Under 6 months — need PICA renewal", "Damaged / full pages — replacing"]),
    ("RGD Civil Documents 92% Rule", "Are your Jamaican RGD birth and/or marriage certificates original, and are photocopies reduced to 92% scale so serial numbers aren't clipped?", "Jamaican RGD certificates are longer than U.S. Letter paper; 100% copies often crop serial numbers.", "Bring original RGD certificates plus 92%-scaled photocopies showing the full header and serial number.", ["Originals + 92% copies ready", "Have originals, still need 92% copies", "Waiting on RGD replacement certificate", "Not applicable to this trip"]),
    ("5-Year Employment & Education Timeline", "Have you listed every employer, self-employment period, and school attended over the past 5 years on your DS-160 with consistent dates?", "Gaps or conflicting dates between DS-160 and verbal answers trigger follow-up scrutiny.", "Review your exact start/end months and job titles before interview day.", ["Complete 5-year timeline verified", "Minor date gaps to clarify", "Multiple short-term / freelance roles", "Student / recent graduate"]),
    ("Prior U.S. Visa Refusals Disclosure", "If you have ever been refused a U.S. visa or had an application placed in 221(g), have you disclosed every instance truthfully on DS-160?", "Consular records permanently show all prior U.S. applications; omission is far worse than a prior 214(b) refusal.", "Always disclose truthfully and focus on genuine, verifiable changes in your life since the prior application.", ["Never previously refused", "1 prior refusal — disclosed on DS-160", "2+ prior refusals — dates & reasons documented", "Prior 221(g) administrative processing"]),
    ("U.S. Relatives & Host Transparency", "Do you have any immediate or extended relatives living in the United States, and do you know their exact immigration status and city?", "Officers routinely ask about U.S. family ties to verify DS-160 honesty and evaluate immigrant intent.", "Answer directly and accurately—never omit a sibling, parent, or spouse living in the U.S.", ["No relatives in the U.S.", "Immediate relatives in U.S. (disclosed)", "Extended relatives only (aunts/uncles/cousins)", "Staying with U.S. friend/host (not relative)"]),
    ("Exact Travel Itinerary & Length of Stay", "What are your exact intended arrival and departure dates, cities visited, and why is that specific trip length appropriate for your job leave?", "Vague plans or unusually long B1/B2 stays (e.g., 3–6 months for a full-time worker) raise red flags.", "Keep your trip length realistic for your approved vacation leave and know where you will stay.", ["Short trip (4–10 days) matching approved leave", "2–3 week vacation with hotel/host itinerary", "Business conference / event with fixed dates", "Flexible dates — need to finalize itinerary"]),
    ("International Travel History", "Which countries outside Jamaica have you visited in the past 5 years, and did you comply with every entry/exit deadline?", "Prior international travel with timely returns demonstrates strong travel compliance.", "Bring expired passports containing previous visas or entry/exit stamps.", ["Visited U.S. / UK / Canada / Schengen before", "Caribbean / regional travel only", "First international trip", "Prior visa stamps in expired passport"]),
    ("DS-160 5-Year Social Media Accuracy", "Have you accurately listed all public social media handles used in the past 5 years on your DS-160?", "DS-160 requires disclosure of social media platforms used in the last 5 years.", "List your actual public usernames cleanly—do not delete accounts right before applying.", ["All 5-year handles listed accurately", "Use 1–2 platforms only (listed)", "No social media accounts used", "Need to review old handles before submitting"]),
    ("Employment Leave Approval Verification", "Does your employer letter explicitly confirm your job title, tenure, gross salary, and approved return-to-work date?", "A detailed Jamaican employer letter on company letterhead strongly supports economic ties.", "Request a fresh letter dated within 30 days of your Kingston interview.", ["Employer letter ready with all 4 details", "Requested from HR — waiting", "Self-employed (TRN, TCC, company reg ready)", "Not employed (student/retired/dependent)"]),
    ("Embassy Day Security & Logistics", "Do you have a plan for arriving at 142 Old Hope Road without cellphones, smartwatches, or large bags (no storage at Embassy)?", "U.S. Embassy Kingston prohibits electronic devices and large bags inside the compound with no on-site lockers.", "Leave your phone in a trusted vehicle or with a companion outside; bring documents in a clear folder.", ["Have a companion / vehicle plan ready", "Will leave electronics at home/hotel", "Need checklist of allowed items", "First time visiting Kingston Embassy"]),
    ("Interview Photo Compliance", "Do you have one recent (within 6 months) 2×2 inch color photo on a plain white background with NO eyeglasses?", "Outdated photos or photos with glasses are rejected at the Embassy intake window.", "Take a fresh 2×2 white-background photo without glasses even if you wear them daily.", ["Fresh 2×2 no-glasses photo ready", "Need to take a new photo before interview", "Digital DS-160 upload matches print", "Unsure if photo meets 6-month rule"]),
    ("Prior Overstay or Status Violation Check", "Have you ever stayed past your I-94 authorized stay or worked without authorization during any prior U.S. visit?", "Even short unauthorized stays or work on a B1/B2 visa affect eligibility under INA 222(g) or 212(a).", "Verify past I-94 arrival/departure records online at i94.cbp.dhs.gov before your interview.", ["No prior U.S. travel", "All prior U.S. visits departed on time", "Had a prior extension/delay (have receipts)", "Need to check I-94 history online"]),
]

_QUESTION_ANGLE_PREFIXES: list[tuple[str, str, str]] = [
    ("Consular Interview Drill", "In a 20-second Kingston interview answer, how would you clearly explain:", "Officers make quick credibility assessments; concise, direct 1–2 sentence answers work best."),
    ("Document Proof Check", "Which exact original document will you bring to verify:", "Bring supporting proof neatly organized in a clear folder, and only hand it over if asked."),
    ("DS-160 Consistency Audit", "Does your DS-160 form match your spoken answer regarding:", "Any mismatch between your DS-160 submission and verbal interview response can trigger follow-up scrutiny."),
    ("Follow-Up Officer Probe", "If the Consular Officer asks a sharp follow-up question probing:", "Stay calm, answer only what is asked truthfully, and avoid over-explaining or memorizing scripts."),
    ("Scenario Readiness", "Suppose the officer questions whether your ties are strong enough on:", "Anchor your response in verifiable facts (dates, employers, family responsibilities, and finances)."),
    ("Pre-Submission Verification", "Before locking in your Kingston appointment, have you double-checked:", "Catching small errors before submitting DS-160 avoids needing a new AA-barcode confirmation."),
]


def _generate_rich_question_batch(
    db: Session,
    c: ClientCase,
    count: int,
    focus: str,
    existing_questions_lower: set[str],
) -> tuple[list[dict[str, Any]], str]:
    """Generate `count` unique rich questionnaire items (title, question, explanation, tip, options) — supports 1 to 1000+."""
    results: list[dict[str, Any]] = []
    seen = set(existing_questions_lower)
    provider_used = "consular-bank"

    # 1. Ask live LLM for bespoke case-tailored questions (up to 3 batches of 15 = up to 45 live LLM questions!)
    llm_target = min(count, 45)
    llm_batch_size = min(llm_target, 15)
    max_llm_calls = 1 if count <= 15 else (2 if count <= 30 else 3)

    for batch_idx in range(max_llm_calls):
        remaining_llm = llm_target - len(results)
        if remaining_llm <= 0:
            break
        ask_n = min(llm_batch_size, remaining_llm)
        avoid_sample = list(seen)[:12]
        llm_text, prov = call_llm(
            db,
            (
                "You are a Jamaican U.S. Visa verification specialist. Return ONLY a valid JSON array of "
                f"{ask_n} unique objects. Each object MUST have keys: "
                "'title' (short 2-5 word topic), 'question' (clear question for the applicant), "
                "'explanation' (1-2 sentence explanation of why U.S. Embassy Kingston / DS-160 cares), "
                "'tip' (1 concise practical truthful tip), and 'options' (array of 3 to 4 realistic short multiple-choice answers). "
                "Truthful preparation only; never coach concealment."
            ),
            (
                f"Generate {ask_n} unique follow-up questionnaire items (batch {batch_idx + 1}).\n"
                f"Case {c.case_id} ({c.full_name or c.pseudonym}), Visa={c.visa_class}, Occupation={c.occupation or 'Pending'}, "
                f"Employer={c.employer_name or 'Pending'}, Gross JMD={c.monthly_gross_jmd}, Net JMD={c.monthly_net_jmd}, "
                f"Destination={c.us_destination or 'Pending'}, Purpose={c.purpose_of_trip or 'Pending'}, "
                f"Prior Refusals={c.prior_us_refusals}, US Relatives={c.us_relatives_details or 'None'}, "
                f"Focus={focus or 'comprehensive Kingston Embassy & DS-160 readiness'}.\n"
                f"Avoid duplicating these topics/questions: {json.dumps(avoid_sample)}"
            ),
        )
        if prov and not prov.startswith(("error:", "none-configured")):
            provider_used = prov
        if not llm_text:
            break
        try:
            m = re.search(r"\[[\s\S]*\]", llm_text)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, list):
                    for idx, item in enumerate(parsed, start=1):
                        if not isinstance(item, dict):
                            continue
                        q = str(item.get("question") or "").strip()
                        if not q or q.lower() in seen:
                            continue
                        seen.add(q.lower())
                        opts = item.get("options") or item.get("choices") or []
                        clean_opts = [str(o).strip() for o in opts if str(o).strip()][:5] if isinstance(opts, list) else []
                        if not clean_opts:
                            clean_opts = ["Verified & ready", "Need to update DS-160", "Need supporting document", "Will explain below"]
                        results.append(
                            {
                                "title": str(item.get("title") or f"Verification Item #{len(results) + 1}").strip()[:120],
                                "question": q,
                                "explanation": str(item.get("explanation") or f"Tailored verification check ({focus or 'Kingston Embassy readiness'}).").strip(),
                                "tip": str(item.get("tip") or "Answer truthfully and keep all dates and amounts consistent with your documents.").strip(),
                                "options": clean_opts,
                            }
                        )
                        if len(results) >= count:
                            break
        except Exception:
            break

    # 2. Fill remaining up to ANY requested count (e.g. 50, 100, 500) using structured Kingston Consular Bank + variations
    if len(results) < count:
        for title, q, exp, tip, opts in _CONSULAR_BANK_SEEDS:
            if len(results) >= count:
                break
            if q.lower() not in seen:
                seen.add(q.lower())
                results.append({"title": title, "question": q, "explanation": exp, "tip": tip, "options": opts})

    round_num = 1
    while len(results) < count:
        for angle_title, prefix, angle_tip in _QUESTION_ANGLE_PREFIXES:
            for base_title, base_q, base_exp, base_tip, base_opts in _CONSULAR_BANK_SEEDS:
                if len(results) >= count:
                    break
                suffix = f" (Deep Check #{round_num})" if round_num > 1 else ""
                variant_q = f"{prefix} {base_q[0].lower()}{base_q[1:]}" if round_num == 1 else f"[{angle_title} #{round_num}] {prefix} {base_q[0].lower()}{base_q[1:]}"
                if variant_q.lower() in seen:
                    continue
                seen.add(variant_q.lower())
                results.append(
                    {
                        "title": f"{base_title} — {angle_title}{suffix}"[:120],
                        "question": variant_q,
                        "explanation": f"{base_exp} (Focus: {focus or c.visa_class} readiness for {c.case_id}).",
                        "tip": f"{angle_tip} {base_tip}",
                        "options": base_opts,
                    }
                )
            if len(results) >= count:
                break
        round_num += 1

    return results[:count], provider_used


@router.get("/clients/{case_id}/questionnaire")
def get_client_questionnaire(
    case_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the structured interactive questionnaire (with explanations, tips & multiple-choice options) for a case."""
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Forbidden.")
    return _serialize_questionnaire_payload(c)


@router.post("/clients/{case_id}/questionnaire/generate")
def generate_dynamic_questionnaire(
    case_id: str,
    req: GenerateQuestionsRequest = GenerateQuestionsRequest(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate `req.count` (1 to 1000+, infinitely repeatable) tailored questions with tips, explanations & multiple choice."""
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    req_count = max(1, min(int(req.count or 5), 1000))
    existing_questions_lower = {(f.follow_up_question or "").strip().lower() for f in c.risk_flags if f.follow_up_question}

    generated, provider = _generate_rich_question_batch(db, c, req_count, req.focus, existing_questions_lower)

    added = []
    for item in generated:
        code = f"AI_DYN_{secrets.token_hex(3).upper()}"
        fl = RiskFlag(
            case_id=c.case_id,
            code=code,
            severity="amber",
            category="ai_questionnaire",
            title=item["title"],
            detail=item["explanation"],
            suggested_fix=item["tip"],
            follow_up_question=item["question"],
            options_json=json.dumps(item["options"]),
            source_citation="Dynamic Consular Questionnaire",
            score_impact=0,
            resolved=False,
        )
        db.add(fl)
        db.flush()
        added.append(
            {
                "flag_id": fl.id,
                "code": code,
                "title": item["title"],
                "question": item["question"],
                "explanation": item["explanation"],
                "tip": item["tip"],
                "options": item["options"],
            }
        )

    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="ai_questionnaire_generated",
            actor=user.full_name,
            summary=f"Generated {len(added)} dynamic AI follow-up question(s) for {c.case_id}.",
        )
    )
    db.commit()
    db.refresh(c)
    return {
        "case_id": c.case_id,
        "provider_used": provider,
        "count_requested": req_count,
        "questions_added": added,
        "questionnaire": _serialize_questionnaire_payload(c),
    }


# ── Direct Chat File Drop / Clipboard Image Paste / CSV-Excel Import ─────────

@router.post("/agent/upload-chat-file")
async def upload_file_in_chat(
    file: UploadFile = File(...),
    case_id: str = Form(""),
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Smart Chat Upload: handles images, PDFs, DOCX, CSV, and Excel (.xlsx) pasted or dropped into chat."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    ext = Path(file.filename).suffix.lower()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    raw_bytes = await file.read()

    # 0. ZIP Archive -> unpack, synthesize ALL clients + stage matched files for Vault attachment!
    if ext == ".zip":
        syn = synthesize_zip_archive(db, raw_bytes, safe_name)
        clients_found = syn.get("clients") or []
        if clients_found:
            names_preview = ", ".join(c["full_name"] for c in clients_found[:5])
            if len(clients_found) > 5:
                names_preview += f" (+{len(clients_found) - 5} more)"
            matched_doc_total = sum(len(c.get("_matched_files") or []) for c in clients_found)
            pa = PendingAction(
                user_id=user.id,
                action_type="bulk_create_clients_with_files",
                target_ref="clients",
                summary=f"Synthesize {len(clients_found)} client(s) & {matched_doc_total} matched vault doc(s) from ZIP '{safe_name}': {names_preview}",
                before_json=json.dumps({}),
                after_json=json.dumps({"clients": clients_found, "batch_id": syn["batch_id"]}),
                status="pending",
            )
            db.add(pa)
            db.commit()
            db.refresh(pa)
            return {
                "kind": "spreadsheet_import",
                "title": safe_name,
                "filename": safe_name,
                "row_count": len(clients_found),
                "pending_action": _serialize_action(pa),
                "panel": {"panel": "spreadsheet", "title": "Client Spreadsheet"},
                "summary": (
                    f"Unpacked **`{safe_name}`** ({syn['files_scanned']} file(s) scanned) and synthesized **{len(clients_found)} new client(s)** "
                    f"(`{names_preview}`) with **{matched_doc_total}** matched Vault document(s). Click **Confirm & Apply** to import all (with 1-click Undo)."
                ),
            }
        raise HTTPException(
            status_code=400,
            detail=f"Scanned {syn['files_scanned']} file(s) inside '{safe_name}', but found no recognizable client names or records.",
        )

    # 1. CSV / Excel / JSON customer data file -> propose bulk import via Confirm card!
    if ext in (".csv", ".xlsx", ".json"):
        parsed_rows = _parse_structured_clients(safe_name, raw_bytes)
        if parsed_rows:
            pa = PendingAction(
                user_id=user.id,
                action_type="bulk_create_clients",
                target_ref="clients",
                summary=f"Import {len(parsed_rows)} client(s) from '{safe_name}'",
                before_json=json.dumps({}),
                after_json=json.dumps({"clients": parsed_rows}),
                status="pending",
            )
            db.add(pa)
            db.commit()
            db.refresh(pa)
            return {
                "kind": "spreadsheet_import",
                "title": safe_name,
                "filename": safe_name,
                "row_count": len(parsed_rows),
                "pending_action": _serialize_action(pa),
                "panel": {"panel": "spreadsheet", "title": "Client Spreadsheet"},
                "summary": f"Detected **{len(parsed_rows)} customer record(s)** in `{safe_name}`. Click **Confirm & Apply** to add them to your Client Spreadsheet.",
            }

    # 1b. TXT / MD or multi-client DOCX / PDF (when no single case is targeted) -> AI Client Synthesizer!
    cid_hint = case_id.strip().upper() if case_id and case_id.strip() else None
    if ext in (".txt", ".md") or (not cid_hint and ext in (".docx", ".pdf")):
        extracted_txt = _extract_text_from_bytes(safe_name, raw_bytes)
        if extracted_txt.strip():
            syn_clients = synthesize_clients_from_text(db, extracted_txt, source_label=safe_name)
            # Trigger bulk synthesis if it's a TXT/MD with 1+ clients, or a DOCX/PDF with 2+ clients (so single-client PDFs still go to Vault!)
            if (ext in (".txt", ".md") and len(syn_clients) >= 1) or len(syn_clients) >= 2:
                names_preview = ", ".join(c["full_name"] for c in syn_clients[:5])
                if len(syn_clients) > 5:
                    names_preview += f" (+{len(syn_clients) - 5} more)"
                pa = PendingAction(
                    user_id=user.id,
                    action_type="bulk_create_clients",
                    target_ref="clients",
                    summary=f"Synthesize {len(syn_clients)} new client(s) from '{safe_name}': {names_preview}",
                    before_json=json.dumps({}),
                    after_json=json.dumps({"clients": syn_clients}),
                    status="pending",
                )
                db.add(pa)
                db.commit()
                db.refresh(pa)
                return {
                    "kind": "spreadsheet_import",
                    "title": safe_name,
                    "filename": safe_name,
                    "row_count": len(syn_clients),
                    "pending_action": _serialize_action(pa),
                    "panel": {"panel": "spreadsheet", "title": "Client Spreadsheet"},
                    "summary": (
                        f"AI synthesized **{len(syn_clients)} new client profile(s)** from `{safe_name}` (`{names_preview}`). "
                        "Click **Confirm & Apply** below to create them all (with full Undo)."
                    ),
                }

    # 2. Client Document / Image / PDF / DOCX -> store in Client Vault + run AI Vision/OCR scan!
    cid = case_id.strip().upper() if case_id and case_id.strip() else None
    client = db.query(ClientCase).filter(ClientCase.case_id == cid).first() if cid else None
    if not client:
        cid = None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest_dir = (CLIENT_VAULT_DIR / cid) if cid else (CLIENT_VAULT_DIR / "_inbox")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{ts}_{safe_name}"
    target.write_bytes(raw_bytes)

    mime = file.content_type or ("application/pdf" if ext == ".pdf" else ("image/png" if ext in (".png", ".jpg", ".jpeg", ".webp") else "application/octet-stream"))
    scan = scan_document_with_ai(db, target, mime, safe_name)

    vdoc = ClientDocument(
        case_id=cid,
        category=scan["category"],
        title=scan.get("document_type") or target.stem.replace("_", " "),
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
    db.add(vdoc)
    db.flush()

    pending_action_out = None
    ext_fields: dict[str, Any] = scan.get("extracted_fields") or {}
    if client and ext_fields:
        before: dict[str, Any] = {}
        updates: dict[str, Any] = {}
        for k, v in ext_fields.items():
            if k in ("passport_number", "dob"):
                before[k] = "(encrypted)"
                updates[k] = v
            elif hasattr(client, k) and getattr(client, k) != v:
                before[k] = getattr(client, k)
                updates[k] = v
        if updates:
            diff_str = ", ".join(f"{k}: {v!r}" for k, v in list(updates.items())[:6])
            pa = PendingAction(
                user_id=user.id,
                action_type="update_client",
                target_ref=client.case_id,
                summary=f"Apply scanned fields from '{vdoc.title}' to {client.case_id} ({diff_str})",
                before_json=json.dumps(before, default=str),
                after_json=json.dumps(updates, default=str),
            )
            db.add(pa)
            db.flush()
            pending_action_out = _serialize_action(pa)

    # Also index PDF/DOCX blueprints in OfficialDocument if unassigned blueprint
    info = inspect_blueprint_file(target) if ext in (".pdf", ".docx") else {"pages": 1, "detected_fields": []}
    if cid:
        db.add(
            PipelineJournal(
                case_id=cid,
                event_type="chat_document_uploaded",
                actor=user.full_name,
                summary=f"Uploaded & scanned '{vdoc.title}' via chat ({len(ext_fields)} field(s) extracted).",
            )
        )
    db.commit()
    db.refresh(vdoc)

    vault_doc_payload = {
        "id": vdoc.id,
        "case_id": vdoc.case_id,
        "category": vdoc.category,
        "title": vdoc.title,
        "filename": vdoc.filename,
        "mime_type": vdoc.mime_type,
        "page_count": vdoc.page_count,
        "ai_summary": vdoc.ai_summary,
        "extracted_fields": ext_fields,
        "compliance_alerts": scan.get("compliance_alerts", []),
        "file_url": f"/api/documents/vault/{vdoc.id}/file",
        "needs_client_assignment": cid is None,
    }
    panel = (
        {"panel": "client", "case_id": cid, "subview": "blueprints", "title": f"Vault — {cid}"}
        if cid
        else {"panel": "spreadsheet", "title": "Client Spreadsheet"}
    )
    return {
        "kind": "vault_document",
        "doc_id": vdoc.id,
        "title": vdoc.title,
        "filename": vdoc.filename,
        "pages": info["pages"],
        "detected_fields": info["detected_fields"],
        "vault_doc": vault_doc_payload,
        "pending_action": pending_action_out,
        "panel": panel,
        "summary": vdoc.ai_summary,
    }


# ── Unified Agent-First Command Endpoint ─────────────────────────────────────

@router.post("/agent/command")
def unified_agent_command(
    req: UnifiedCommandRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    msg = req.message.strip()
    low = msg.lower()
    role = user.role

    # Ensure persistent Conversation record exists
    conv_id = req.conversation_id or f"conv_{secrets.token_hex(6)}"
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        short_title = msg[:44] + ("…" if len(msg) > 44 else "")
        conv = Conversation(id=conv_id, user_id=user.id, title=short_title, case_id=req.case_id or user.linked_case_id)
        db.add(conv)
        db.flush()
    else:
        if conv.title == "New Conversation":
            conv.title = msg[:44] + ("…" if len(msg) > 44 else "")
        conv.updated_at = datetime.now(timezone.utc)

    history = load_conversation_history(db, conv_id, max_turns=10)
    user_msg_row = ChatMessage(session_id=conv_id, case_id=req.case_id or user.linked_case_id, user_role=role, sender="user", content=msg)
    db.add(user_msg_row)

    ui_panel: dict[str, Any] | None = None
    tool_trace: list[dict[str, Any]] = []
    citations: list[dict[str, str]] = []
    created_assets: list[dict[str, Any]] = []
    pending_action_payload: dict[str, Any] | None = None
    questionnaire_payload: dict[str, Any] | None = None
    data_table_payload: dict[str, Any] | None = None
    reply = ""
    provider = "consular-ai-local"

    # ── CUSTOMER FLOW ────────────────────────────────────────────────────────
    if role == "customer":
        cid = user.linked_case_id or "C034"
        client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()

        if _wants_questionnaire_generation(low) or any(k in low for k in ("questionnaire", "questionare", "ask me question")):
            if client:
                req_n = _extract_requested_question_count(msg, default=5)
                if _wants_questionnaire_generation(low) or not any(f.follow_up_question for f in client.risk_flags):
                    q_res = generate_dynamic_questionnaire(cid, GenerateQuestionsRequest(focus=msg, count=req_n), user=user, db=db)
                    questionnaire_payload = q_res["questionnaire"]
                    provider = q_res["provider_used"]
                    reply = f"Generated **{len(q_res['questions_added'])} tailored question(s)** for your case (`{cid}`) — answer them interactively right here below (click the **Tips** icon on any question for guidance, or use the side panel)."
                else:
                    questionnaire_payload = _serialize_questionnaire_payload(client)
                    reply = f"Loaded your **Interactive Questionnaire** (`{questionnaire_payload['total_count']}` questions) right here in chat. Click the **Tips** icon on any question for an explanation, pick a choice or type your answer, or generate more questions anytime."
                ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "intake", "title": "Interactive Questionnaire"}
        else:
            if any(k in low for k in ("my status", "good standing", "standing", "my case", "progress", "flag", "score")):
                ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "overview", "title": f"My Case Status ({cid})"}
            elif any(k in low for k in ("intake", "form", "my detail", "update my", "edit my")):
                ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "intake", "title": "My Details & Questionnaire"}
            elif any(k in low for k in ("mock", "practice", "interview", "simulate")):
                ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "practice", "title": "Voice & Text Mock Interview"}
            elif any(k in low for k in ("doc", "roadmap", "checklist", "pdf", "download", "file", "image")):
                ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "docs", "title": "My Approved Docs & Roadmap"}
            elif any(k in low for k in ("pica", "official", "embassy", "link", "source")):
                ui_panel = {"panel": "gov_sources", "title": "Official U.S. Embassy & PICA Links"}

            res = answer_customer_question(db, msg, client, conversation_id=conv_id, history=history)
            reply = res["reply"]
            citations = res.get("citations", [])
            provider = res["provider_used"]

    # ── CEO / STAFF FLOW ─────────────────────────────────────────────────────
    else:
        target_cid = _detect_case_id(db, msg, req.case_id)

        # 0. Smart Paste Auto-Setup FIRST (API keys, MCP URLs/JSON, ClawLink, Composio, pasted CSV, Gov URLs!)
        smart = detect_and_apply_smart_paste(db, user, msg)
        gmail_cmd = None if smart else detect_chat_gmail_command(db, user, msg, target_cid)
        if smart:
            # Redact pasted secret keys from saved chat history!
            if smart.get("redacted_message"):
                user_msg_row.content = smart["redacted_message"]
                if conv.title and any(tok in conv.title for tok in ("sk-", "AIza", "xai-", "ak_")):
                    conv.title = "API Key / Connection Setup"
            pending_action_payload = _serialize_action(smart["pending_action"]) if smart.get("pending_action") else None
            ui_panel = smart.get("ui_panel")
            reply = smart["reply"]
            provider = "smart-paste-engine"
        elif gmail_cmd:
            ui_panel = gmail_cmd.get("ui_panel")
            reply = gmail_cmd["reply"]
            provider = "gmail-automation"
        else:
            # 1. Check Safe Chat Delete / Wipe OR CEO/Staff Conversational Edit / Client Creation (Preview/Confirm + Undo!)
            proposed = (
                detect_chat_delete_or_reset(db, user, msg, target_cid)
                or _detect_ceo_conversational_edit(db, user, msg, target_cid)
                or detect_natural_client_crud(db, user, msg, target_cid)
            )
            if proposed:
                pending_action_payload = _serialize_action(proposed)
                is_del = proposed.action_type in ("delete_client", "bulk_delete_clients", "wipe_all_clients", "reset_seed_data")
                reply = (
                    f"⚠️ **Please confirm this destructive action:**\n\n**{proposed.summary}**\n\n"
                    "Nothing has been deleted yet. Click **Confirm & Apply** below to proceed (a full snapshot is saved for **1-click Undo**)."
                    if is_del
                    else f"I prepared this change for your review:\n\n**{proposed.summary}**\n\nClick **Confirm & Apply** below to execute (with full Undo & audit logging)."
                )
                if proposed.action_type == "update_client" and target_cid:
                    ui_panel = {"panel": "client", "case_id": target_cid, "subview": "intake", "title": f"Case {target_cid}"}
                elif proposed.action_type in ("create_client", "delete_client", "bulk_delete_clients", "wipe_all_clients", "reset_seed_data"):
                    ui_panel = {"panel": "spreadsheet", "title": "Client Spreadsheet"}
                elif proposed.action_type == "update_branding":
                    ui_panel = {"panel": "settings", "title": "Settings & Branding"}
            elif target_cid and _wants_questionnaire_generation(low):
                req_n = _extract_requested_question_count(msg, default=5)
                q_res = generate_dynamic_questionnaire(target_cid, GenerateQuestionsRequest(focus=msg, count=req_n), user=user, db=db)
                qs = q_res["questions_added"]
                questionnaire_payload = q_res["questionnaire"]
                ui_panel = {"panel": "client", "case_id": target_cid, "subview": "intake", "title": f"Questionnaire — {target_cid}"}
                reply = (
                    f"Generated **{len(qs)} interactive question(s)** for **{target_cid}** (total in case: **{questionnaire_payload['total_count']}**) — "
                    "use the interactive card below with **Tips**, **Multiple Choice**, or custom answers, and generate as many more as you need anytime."
                )
                provider = q_res["provider_used"]
            else:
                is_action_task = req.mode == "task" or (
                    any(
                        k in low
                        for k in (
                            "audit",
                            "generate",
                            "draft",
                            "create packet",
                            "roadmap",
                            "worksheet",
                            "checklist",
                            "scrape",
                            "refresh",
                            "sync obsidian",
                        )
                    )
                    and not any(k in low for k in ("ceo", "analytics", "graph", "chart", "recall", "scenario", "senario", "possible question"))
                )

                # Decide which companion side panel (if any) to open alongside the AI reply
                if any(k in low for k in ("gmail", "email automation", "email rule", "email queue", "inbox sync", "cron job", "hermes cron")):
                    ui_panel = {"panel": "gmail", "title": "Gmail Automation & Cron"}
                elif any(k in low for k in ("spreadsheet", "excel", "sort client", "sort case", "sort by", "client table")):
                    ui_panel = {"panel": "spreadsheet", "title": "Client Spreadsheet & Vault"}
                elif role == "ceo" and any(k in low for k in ("ceo", "analytics", "graph", "chart", "kpi", "revenue", "approval rate", "recall", "metrics", "overview", "executive")):
                    ui_panel = {"panel": "ceo_analytics", "title": "CEO Executive Analytics & Graphs"}
                elif role == "ceo" and any(k in low for k in ("staff", "team", "create account", "new user", "add staff", "manage user", "logins")):
                    ui_panel = {"panel": "team", "title": "Team & Staff Account Manager"}
                elif any(k in low for k in ("open setting", "voice setting", "elevenlabs", "fish audio", "subscription", "codex", "claude", "chatgpt", "antigravity", "api key", "ollama", "composio", "clawlink", "mcp", "brand")):
                    ui_panel = {"panel": "settings", "title": "Connections, AI & Voice Setup"}
                elif any(k in low for k in ("obsidian", "vault", "wikilink")):
                    note_path = f"Clients/{target_cid}.md" if target_cid and "client" in low else "Index.md"
                    ui_panel = {"panel": "obsidian", "path": note_path, "title": f"Obsidian Vault — {note_path}"}
                elif any(k in low for k in ("database", "sql", "manifest", "import")):
                    tbl = "source_manifest" if "manifest" in low else ("gov_sources" if "source" in low else "clients")
                    ui_panel = {"panel": "database", "table": tbl, "title": f"Database Explorer ({tbl})"}
                elif any(k in low for k in ("pdf", "pica", "ds-5535", "ds5535", "ds-157", "ds157", "ds-156", "birreq", "passport form", "blueprint", "official doc", "show doc", "document")) and not any(k in low for k in ("generate", "draft", "create")):
                    doc_key = _match_official_pdf(db, low)
                    ui_panel = {"panel": "official_pdfs", "doc_key": doc_key, "title": "Official Government PDF Viewer"}
                elif any(k in low for k in ("source", "scrape", "embassy link", "gov link", "website")):
                    ui_panel = {"panel": "gov_sources", "title": "Official Scraped Gov Sources"}
                elif any(k in low for k in ("all client", "list client", "pipeline", "kanban", "all case", "show case")):
                    ui_panel = {"panel": "clients_list", "title": "Client Pipeline & Cases"}
                elif target_cid:
                    sub = "overview"
                    if any(k in low for k in ("intake", "edit", "form", "questionn", "questiona", "follow-up", "followup", "folloup")):
                        sub = "intake"
                    elif any(k in low for k in ("interview", "mock", "predict", "freeze", "scenario", "senario", "possible question", "questions")):
                        sub = "interview"
                    elif any(k in low for k in ("roadmap", "image", "worksheet", "checklist", "letter", "docx", "generate", "draft", "approve", "asset", "file", "doc", "vault", "sign")):
                        sub = "blueprints"
                    elif any(k in low for k in ("journal", "history", "timeline", "log")):
                        sub = "journal"
                    ui_panel = {"panel": "client", "case_id": target_cid, "subview": sub, "title": f"Case {target_cid}"}

                # Check if user requested a dynamic client data table / chart / sorted breakdown
                data_table_payload = build_dynamic_data_table(db, msg)

                if is_action_task:
                    res = run_staff_agent_loop(
                        db,
                        msg,
                        case_id=target_cid,
                        actor=f"Consular AI ({user.full_name})",
                        conversation_id=conv_id,
                        history=history,
                    )
                    reply = res["reply"]
                    tool_trace = res.get("tool_trace", [])
                    provider = res["provider_used"]
                    if res.get("created_assets") and target_cid:
                        recent = (
                            db.query(GeneratedAsset)
                            .filter(GeneratedAsset.case_id == target_cid)
                            .order_by(GeneratedAsset.id.desc())
                            .limit(len(res["created_assets"]))
                            .all()
                        )
                        created_assets = [
                            {
                                "id": a.id,
                                "title": a.title,
                                "filename": a.filename,
                                "mime_type": a.mime_type,
                                "approval_status": a.approval_status,
                                "file_url": f"/api/assets/{a.id}/file",
                            }
                            for a in recent
                        ]
                        ui_panel = {
                            "panel": "client",
                            "case_id": target_cid,
                            "subview": "blueprints",
                            "preview_asset_id": recent[0].id if recent else None,
                            "title": f"Draft Deliverables — {target_cid}",
                        }
                else:
                    client = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first() if target_cid else None
                    extra_parts: list[str] = []
                    if ui_panel:
                        extra_parts.append(
                            f"UI Action Already Performed: Opened the right-hand side panel '{ui_panel.get('title')}' "
                            f"(panel={ui_panel.get('panel')}, subview={ui_panel.get('subview', 'default')})."
                        )
                    if data_table_payload:
                        extra_parts.append(
                            f"Interactive Data Table Already Rendered Below Your Reply: {data_table_payload['title']} ({data_table_payload['subtitle']}). "
                            f"Summarize the key takeaways concisely without manually printing a huge raw table."
                        )
                    if ui_panel and ui_panel["panel"] == "ceo_analytics":
                        total = db.query(ClientCase).count()
                        approved = db.query(ClientCase).filter(ClientCase.outcome == "approved").count()
                        refused = db.query(ClientCase).filter(ClientCase.outcome == "refused").count()
                        extra_parts.append(f"Live Agency Portfolio KPIs: Total={total} cases, Approved={approved}, Refused={refused}.")
                    elif ui_panel and ui_panel["panel"] == "official_pdfs":
                        docs = db.query(OfficialDocument).all()
                        doc_list = ", ".join(f"{d.title} ({d.filename})" for d in docs[:10])
                        extra_parts.append(f"Available Official Government PDFs & Blueprints in the side panel: {doc_list}.")
                    elif ui_panel and ui_panel["panel"] in ("clients_list", "spreadsheet"):
                        top_cases = db.query(ClientCase).order_by(ClientCase.updated_at.desc()).limit(10).all()
                        case_list = ", ".join(f"{c.case_id} ({c.full_name or c.pseudonym}, {c.standing_score}%)" for c in top_cases)
                        extra_parts.append(f"Recent Clients in Pipeline: {case_list}.")

                    if client and any(k in low for k in ("questionn", "questiona", "import question", "show question")):
                        if not any(f.follow_up_question for f in client.risk_flags):
                            q_res = generate_dynamic_questionnaire(client.case_id, GenerateQuestionsRequest(focus=msg, count=5), user=user, db=db)
                            questionnaire_payload = q_res["questionnaire"]
                        else:
                            questionnaire_payload = _serialize_questionnaire_payload(client)

                    res = answer_customer_question(
                        db,
                        msg,
                        client,
                        conversation_id=conv_id,
                        history=history,
                        extra_context="\n".join(extra_parts),
                    )
                    reply = res["reply"]
                    citations = res.get("citations", [])
                    provider = res["provider_used"]

                    if provider == "none-configured" and (ui_panel or data_table_payload):
                        if data_table_payload:
                            reply = f"**{data_table_payload['title']}** — {data_table_payload['subtitle']}. Click any row to open that client's profile or documents."
                        elif ui_panel and ui_panel["panel"] == "client" and client:
                            red_n = sum(1 for f in client.risk_flags if f.severity == "red" and not f.resolved)
                            amber_n = sum(1 for f in client.risk_flags if f.severity == "amber" and not f.resolved)
                            reply = (
                                f"Opened **{client.case_id} — {client.full_name or client.pseudonym}** (`{client.visa_class}`) in the side panel.\n\n"
                                f"- **Good Standing:** `{client.standing_score}%` ({client.denial_risk_level.upper()} risk — {red_n} Red, {amber_n} Amber)\n"
                                f"- **Stage:** `{client.pipeline_stage.replace('_', ' ').title()}` | **DS-160:** `{client.ds160_confirmation_id or 'Pending'}`"
                            )
                        elif ui_panel and ui_panel["panel"] == "ceo_analytics":
                            total = db.query(ClientCase).count()
                            approved = db.query(ClientCase).filter(ClientCase.outcome == "approved").count()
                            refused = db.query(ClientCase).filter(ClientCase.outcome == "refused").count()
                            reply = f"Opened **CEO Executive Analytics & Graphs** in the side panel ({total} total cases: {approved} approved, {refused} refused)."
                        elif ui_panel:
                            reply = f"Opened **{ui_panel.get('title', 'Workspace Panel')}** in the side panel."

    meta_blob = {
        "tool_trace": tool_trace,
        "citations": citations,
        "created_assets": created_assets,
        "panel": ui_panel,
        "pending_action": pending_action_payload,
        "questionnaire": questionnaire_payload,
        "data_table": data_table_payload,
    }
    db.add(
        ChatMessage(
            session_id=conv_id,
            case_id=req.case_id or user.linked_case_id,
            user_role=role,
            sender="assistant",
            content=reply,
            tool_trace_json=json.dumps(meta_blob),
            provider_used=provider,
        )
    )
    db.commit()

    return {
        "conversation_id": conv_id,
        "conversation_title": conv.title,
        "reply": reply,
        "provider_used": provider,
        "mode": req.mode,
        "tool_trace": tool_trace,
        "citations": citations,
        "created_assets": created_assets,
        "ui_panel": ui_panel,
        "pending_action": pending_action_payload,
        "questionnaire": questionnaire_payload,
        "data_table": data_table_payload,
    }
