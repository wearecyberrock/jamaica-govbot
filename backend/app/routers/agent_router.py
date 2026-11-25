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
from app.config import BLUEPRINTS_DIR
from app.database import get_db
from app.models import (
    BrandingConfig,
    ChatMessage,
    ClientCase,
    Conversation,
    GeneratedAsset,
    OfficialDocument,
    PendingAction,
    PipelineJournal,
    RiskFlag,
    User,
)
from app.services.doc_generator import inspect_blueprint_file
from app.services.hermes_engine import (
    answer_customer_question,
    call_llm,
    load_conversation_history,
    run_staff_agent_loop,
)
from app.services.obsidian import sync_client_to_obsidian
from app.services.risk_engine import evaluate_client_standing

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
                if hasattr(c, k):
                    setattr(c, k, v)
            db.add(PipelineJournal(case_id=c.case_id, event_type="ai_edit_confirmed", actor=user.full_name, summary=f"Confirmed AI edit: {act.summary}"))
            db.commit()
            evaluate_client_standing(db, c)
            sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)

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
                if hasattr(c, k):
                    setattr(c, k, v)
            db.add(PipelineJournal(case_id=c.case_id, event_type="ai_edit_undone", actor=user.full_name, summary=f"Undid AI edit: {act.summary}"))
            db.commit()
            evaluate_client_standing(db, c)
            sync_client_to_obsidian(c, c.risk_flags, c.journal_entries)

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


# ── AI-in-the-Loop Dynamic Questionnaire Generator ───────────────────────────

@router.post("/clients/{case_id}/questionnaire/generate")
def generate_dynamic_questionnaire(
    case_id: str,
    req: GenerateQuestionsRequest = GenerateQuestionsRequest(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate tailored on-the-fly follow-up questions based on client gaps & risks, synced to Right Side Panel."""
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    existing_codes = {f.code for f in c.risk_flags}
    new_questions: list[tuple[str, str, str]] = []

    # Try active LLM first for bespoke follow-ups
    llm_text, provider = call_llm(
        db,
        "You are a Jamaican U.S. Visa verification specialist. Return ONLY a JSON array of 3 objects with keys 'title' and 'question' for truthful DS-160 & Kingston Embassy interview readiness. Never coach concealment.",
        f"Case {c.case_id}, Visa={c.visa_class}, Occupation={c.occupation}, Gross JMD={c.monthly_gross_jmd}, Net JMD={c.monthly_net_jmd}, "
        f"Destination={c.us_destination}, Prior Refusals={c.prior_us_refusals}, US Relatives={c.us_relatives_details}, Focus={req.focus}",
    )
    if llm_text:
        try:
            m = re.search(r"\[[\s\S]*\]", llm_text)
            if m:
                parsed = json.loads(m.group(0))
                for idx, item in enumerate(parsed[:4], start=1):
                    q = str(item.get("question") or "").strip()
                    t = str(item.get("title") or f"Dynamic Follow-Up #{idx}").strip()
                    if q:
                        new_questions.append((f"AI_DYN_{secrets.token_hex(2).upper()}", t, q))
        except Exception:
            pass

    if not new_questions:
        pool = [
            ("AI_TIES_HOME", "Home Ties & Return Commitment", "What specific job duties, property, or family responsibilities require your return to Jamaica immediately after your U.S. visit?"),
            ("AI_TRIP_FUNDING", "Trip Funding & Budget Alignment", "Who is paying for your flight, hotel, and daily expenses, and does your bank balance comfortably match that budget?"),
            ("AI_SOCIAL_CHECK", "DS-160 5-Year Social Media & Employment Accuracy", "Have you listed every employer from the last 5 years and your public social media handles accurately for Form DS-160?"),
        ]
        if c.prior_us_refusals > 0:
            pool.insert(0, ("AI_REFUSAL_CHANGE", "Changes Since Prior U.S. Refusal", "What genuine, verifiable changes in your employment, income, or family ties have occurred since your last U.S. visa refusal?"))
        for code, title, q in pool:
            if code not in existing_codes:
                new_questions.append((code, title, q))

    added = []
    for code, title, q in new_questions[:3]:
        fl = RiskFlag(
            case_id=c.case_id,
            code=code,
            severity="amber",
            category="ai_questionnaire",
            title=title,
            detail=f"AI-generated verification question ({req.focus or 'live readiness check'}).",
            suggested_fix="Record the client's truthful answer and verify against supporting documents.",
            follow_up_question=q,
            source_citation="Dynamic Consular Questionnaire",
            score_impact=0,
            resolved=False,
        )
        db.add(fl)
        added.append({"code": code, "title": title, "question": q})

    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="ai_questionnaire_generated",
            actor=user.full_name,
            summary=f"Generated {len(added)} dynamic AI follow-up question(s) for {c.case_id}.",
        )
    )
    db.commit()
    return {"case_id": c.case_id, "provider_used": provider, "questions_added": added}


# ── Direct Chat File Drop / Attachment ───────────────────────────────────────

@router.post("/agent/upload-chat-file")
async def upload_file_in_chat(
    file: UploadFile = File(...),
    case_id: str = Form(""),
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    ext = Path(file.filename).suffix.lower()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    target = BLUEPRINTS_DIR / safe_name
    target.write_bytes(await file.read())
    info = inspect_blueprint_file(target)

    doc_key = re.sub(r"[^a-z0-9_]+", "_", target.stem.lower()).strip("_")[:55]
    if db.query(OfficialDocument).filter(OfficialDocument.doc_key == doc_key).first():
        doc_key = f"{doc_key}_{secrets.token_hex(2)}"

    doc = OfficialDocument(
        doc_key=doc_key,
        title=target.stem.replace("_", " "),
        agency=f"Uploaded ({case_id or user.full_name})",
        category="agency_blueprint",
        filename=safe_name,
        file_path=str(target),
        file_format=ext or ".bin",
        size_bytes=info["size_bytes"],
        sha256=info["sha256"],
        description=f"Attached directly in chat by {user.full_name}.",
        detected_fields_json=json.dumps(info["detected_fields"]),
        is_blueprint=ext in (".pdf", ".docx"),
    )
    db.add(doc)
    db.commit()
    return {
        "doc_key": doc.doc_key,
        "title": doc.title,
        "filename": doc.filename,
        "pages": info["pages"],
        "detected_fields": info["detected_fields"],
        "panel": {"panel": "official_pdfs", "doc_key": doc.doc_key, "title": f"Attached: {doc.title}"},
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
    db.add(ChatMessage(session_id=conv_id, case_id=req.case_id or user.linked_case_id, user_role=role, sender="user", content=msg))

    ui_panel: dict[str, Any] | None = None
    tool_trace: list[dict[str, Any]] = []
    citations: list[dict[str, str]] = []
    created_assets: list[dict[str, Any]] = []
    pending_action_payload: dict[str, Any] | None = None
    reply = ""
    provider = "consular-ai-local"

    # ── CUSTOMER FLOW ────────────────────────────────────────────────────────
    if role == "customer":
        cid = user.linked_case_id or "C034"
        client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()

        if any(k in low for k in ("generate question", "questionnaire", "ask me question")):
            if client:
                q_res = generate_dynamic_questionnaire(cid, GenerateQuestionsRequest(focus=msg), user=user, db=db)
                qs = q_res["questions_added"]
                ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "intake", "title": "Interactive Questionnaire"}
                reply = (
                    "I generated tailored follow-up verification questions for your profile and opened your **Interactive Questionnaire** in the side panel:\n\n"
                    + "\n".join(f"- **{q['title']}:** {q['question']}" for q in qs)
                    + "\n\nAnswer them right here in chat or fill them in the side panel to update your Good Standing bar live."
                )
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

        # Check CEO / Staff Conversational Edit Proposal FIRST (Preview/Confirm + Undo!)
        proposed = _detect_ceo_conversational_edit(db, user, msg, target_cid)
        if proposed:
            pending_action_payload = _serialize_action(proposed)
            reply = f"I prepared this change for your review:\n\n**{proposed.summary}**\n\nClick **Confirm & Apply** below to execute (with full Undo & audit logging)."
            if proposed.action_type == "update_client" and target_cid:
                ui_panel = {"panel": "client", "case_id": target_cid, "subview": "intake", "title": f"Case {target_cid}"}
            elif proposed.action_type == "update_branding":
                ui_panel = {"panel": "settings", "title": "Settings & Branding"}
        elif target_cid and _wants_questionnaire_generation(low):
            q_res = generate_dynamic_questionnaire(target_cid, GenerateQuestionsRequest(focus=msg), user=user, db=db)
            qs = q_res["questions_added"]
            ui_panel = {"panel": "client", "case_id": target_cid, "subview": "intake", "title": f"Questionnaire — {target_cid}"}
            reply = (
                f"Generated **{len(qs)} dynamic follow-up questions** for **{target_cid}** and opened the interactive Questionnaire in the side panel:\n\n"
                + "\n".join(f"- **{q['title']}:** {q['question']}" for q in qs)
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
            if role == "ceo" and any(k in low for k in ("ceo", "analytics", "graph", "chart", "kpi", "revenue", "approval rate", "recall", "metrics", "overview", "executive")):
                ui_panel = {"panel": "ceo_analytics", "title": "CEO Executive Analytics & Graphs"}
            elif role == "ceo" and any(k in low for k in ("staff", "team", "create account", "new user", "add staff", "manage user", "logins")):
                ui_panel = {"panel": "team", "title": "Team & Staff Account Manager"}
            elif any(k in low for k in ("open setting", "voice setting", "elevenlabs", "fish audio", "subscription", "codex", "claude", "chatgpt", "antigravity", "api key", "ollama", "composio", "mcp", "brand")):
                ui_panel = {"panel": "settings", "title": "AI Subscriptions, Voice & Setup"}
            elif any(k in low for k in ("obsidian", "vault", "wikilink")):
                note_path = f"Clients/{target_cid}.md" if target_cid and "client" in low else "Index.md"
                ui_panel = {"panel": "obsidian", "path": note_path, "title": f"Obsidian Vault — {note_path}"}
            elif any(k in low for k in ("database", "sql", "table", "manifest", "csv", "spreadsheet", "import")):
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
                elif any(k in low for k in ("roadmap", "image", "worksheet", "checklist", "letter", "docx", "generate", "draft", "approve", "asset", "file", "doc")):
                    sub = "blueprints"
                elif any(k in low for k in ("journal", "history", "timeline", "log")):
                    sub = "journal"
                ui_panel = {"panel": "client", "case_id": target_cid, "subview": sub, "title": f"Case {target_cid}"}

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
                # Build rich live workspace context and ALWAYS let the live AI respond naturally!
                client = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first() if target_cid else None
                extra_parts: list[str] = []
                if ui_panel:
                    extra_parts.append(
                        f"UI Action Already Performed: Opened the right-hand side panel '{ui_panel.get('title')}' "
                        f"(panel={ui_panel.get('panel')}, subview={ui_panel.get('subview', 'default')})."
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
                elif ui_panel and ui_panel["panel"] == "clients_list":
                    top_cases = db.query(ClientCase).order_by(ClientCase.updated_at.desc()).limit(10).all()
                    case_list = ", ".join(f"{c.case_id} ({c.full_name or c.pseudonym}, {c.standing_score}%)" for c in top_cases)
                    extra_parts.append(f"Recent Clients in Pipeline: {case_list}.")

                # For bare navigation commands when no LLM is connected, or if live AI answers directly:
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

                # If no live AI is connected yet AND a panel was opened, give a crisp panel-specific summary
                if provider == "none-configured" and ui_panel:
                    if ui_panel["panel"] == "client" and client:
                        red_n = sum(1 for f in client.risk_flags if f.severity == "red" and not f.resolved)
                        amber_n = sum(1 for f in client.risk_flags if f.severity == "amber" and not f.resolved)
                        reply = (
                            f"Opened **{client.case_id} — {client.full_name or client.pseudonym}** (`{client.visa_class}`) in the side panel.\n\n"
                            f"- **Good Standing:** `{client.standing_score}%` ({client.denial_risk_level.upper()} risk — {red_n} Red, {amber_n} Amber)\n"
                            f"- **Stage:** `{client.pipeline_stage.replace('_', ' ').title()}` | **DS-160:** `{client.ds160_confirmation_id or 'Pending'}`\n\n"
                            "*Connect an AI provider in Settings → AI Subscriptions & Setup for full conversational answers about this case.*"
                        )
                    elif ui_panel["panel"] == "ceo_analytics":
                        total = db.query(ClientCase).count()
                        approved = db.query(ClientCase).filter(ClientCase.outcome == "approved").count()
                        refused = db.query(ClientCase).filter(ClientCase.outcome == "refused").count()
                        reply = (
                            f"Opened **CEO Executive Analytics & Graphs** in the side panel ({total} total cases: {approved} approved, {refused} refused)."
                        )
                    else:
                        reply = f"Opened **{ui_panel.get('title', 'Workspace Panel')}** in the side panel.\n\n{reply}"

    meta_blob = {
        "tool_trace": tool_trace,
        "citations": citations,
        "created_assets": created_assets,
        "panel": ui_panel,
        "pending_action": pending_action_payload,
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
    }
