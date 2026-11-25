"""Gmail Messaging, Dual-Mode Cron Rules, Approval Queue, Inbox Attachment Sync & Hermes Cron Bridge Router."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import ClientCase, EmailAutomationRule, EmailMessageLog, User
from app.services.gmail_service import (
    build_whatsapp_version,
    draft_email_for_client,
    get_gmail_config,
    poll_gmail_inbox,
    run_email_automation_cycle,
    save_gmail_config,
    send_email_now,
    serialize_email_log,
    serialize_rule,
    sync_rules_to_hermes_cron,
    test_gmail_connection,
)

router = APIRouter(prefix="/api/gmail", tags=["gmail"])


class GmailConfigUpdate(BaseModel):
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    default_mode: str | None = None  # dual | auto | approval
    sender_name: str | None = None
    imap_enabled: bool | None = None


class CreateRuleRequest(BaseModel):
    name: str
    description: str = ""
    rule_type: str = "custom"
    enabled: bool = True
    send_mode: str = "dual"  # auto | approval | dual
    cron_expr: str = "0 9 * * *"
    interval_minutes: int = 1440
    cooldown_days: int = 14
    threshold_days: int = 180
    subject_template: str = ""
    body_template: str = ""
    use_ai_personalization: bool = True


class UpdateRuleRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    send_mode: str | None = None
    cron_expr: str | None = None
    interval_minutes: int | None = None
    cooldown_days: int | None = None
    threshold_days: int | None = None
    subject_template: str | None = None
    body_template: str | None = None
    use_ai_personalization: bool | None = None


class DraftOrSendRequest(BaseModel):
    case_id: str | None = None
    to_email: str = ""
    subject: str = ""
    body_text: str = ""
    topic: str = ""
    send_immediately: bool = False


class ApproveMessageRequest(BaseModel):
    subject: str | None = None
    body_text: str | None = None


@router.get("/overview")
def gmail_overview(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cfg = get_gmail_config(db)
    rules = db.query(EmailAutomationRule).order_by(EmailAutomationRule.id.asc()).all()
    logs = db.query(EmailMessageLog).order_by(EmailMessageLog.id.desc()).limit(60).all()
    queued_count = db.query(EmailMessageLog).filter(EmailMessageLog.status == "queued_approval").count()
    sent_count = db.query(EmailMessageLog).filter(EmailMessageLog.status == "sent").count()
    inbound_count = db.query(EmailMessageLog).filter(EmailMessageLog.direction == "inbound").count()
    clients = (
        db.query(ClientCase)
        .filter(ClientCase.email != "")
        .order_by(ClientCase.updated_at.desc())
        .limit(50)
        .all()
    )
    return {
        "config": cfg,
        "stats": {
            "queued_approval": queued_count,
            "sent_total": sent_count,
            "inbound_total": inbound_count,
            "active_rules": sum(1 for r in rules if r.enabled),
        },
        "rules": [serialize_rule(r) for r in rules],
        "messages": [serialize_email_log(m) for m in logs],
        "emailable_clients": [
            {
                "case_id": c.case_id,
                "full_name": c.full_name or c.pseudonym,
                "email": c.email,
                "passport_expiry": c.passport_expiry,
                "embassy_interview_date": c.embassy_interview_date,
                "standing_score": c.standing_score,
                "email_muted": bool(getattr(c, "email_muted", False)),
            }
            for c in clients
            if not (c.full_name or "").startswith("Reference Case")
        ],
    }


@router.put("/config")
def update_gmail_config(
    req: GmailConfigUpdate,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return save_gmail_config(
        db,
        gmail_address=req.gmail_address,
        gmail_app_password=req.gmail_app_password,
        default_mode=req.default_mode,
        sender_name=req.sender_name,
        imap_enabled=req.imap_enabled,
    )


@router.post("/test-connection")
def test_connection(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return test_gmail_connection(db)


@router.post("/rules")
def create_rule(
    req: CreateRuleRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rule = EmailAutomationRule(
        name=req.name.strip(),
        description=req.description.strip(),
        rule_type=req.rule_type.strip() or "custom",
        enabled=req.enabled,
        send_mode=req.send_mode if req.send_mode in ("auto", "approval", "dual") else "dual",
        cron_expr=req.cron_expr.strip() or "0 9 * * *",
        interval_minutes=max(15, req.interval_minutes),
        cooldown_days=max(0, req.cooldown_days),
        threshold_days=max(1, req.threshold_days),
        subject_template=req.subject_template.strip(),
        body_template=req.body_template.strip(),
        use_ai_personalization=req.use_ai_personalization,
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=max(15, req.interval_minutes)),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return serialize_rule(rule)


@router.patch("/rules/{rule_id}")
def update_rule(
    rule_id: int,
    req: UpdateRuleRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rule = db.query(EmailAutomationRule).filter(EmailAutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found.")
    for field, val in req.model_dump(exclude_none=True).items():
        if hasattr(rule, field):
            setattr(rule, field, val)
    db.commit()
    db.refresh(rule)
    return serialize_rule(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    rule = db.query(EmailAutomationRule).filter(EmailAutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found.")
    db.delete(rule)
    db.commit()
    return {"deleted": True}


@router.post("/rules/{rule_id}/run")
def run_single_rule(
    rule_id: int,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rule = db.query(EmailAutomationRule).filter(EmailAutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found.")
    return run_email_automation_cycle(db, rule_id=rule_id, force=True)


@router.post("/run-all")
def run_all_rules_now(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return run_email_automation_cycle(db, force=True)


@router.post("/ai-draft")
def ai_draft_client_email(
    req: DraftOrSendRequest,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not req.case_id:
        raise HTTPException(status_code=400, detail="Select a client case_id to draft a personalized email.")
    client = db.query(ClientCase).filter(ClientCase.case_id == req.case_id.upper()).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    draft = draft_email_for_client(db, client, custom_topic=req.topic.strip())
    return {
        "case_id": client.case_id,
        "to_email": client.email,
        **draft,
    }


@router.post("/send")
def compose_and_send(
    req: DraftOrSendRequest,
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    to_email = req.to_email.strip()
    cid = req.case_id.upper() if req.case_id else None
    if cid and not to_email:
        c = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
        if c:
            to_email = c.email
    if not req.subject.strip() or not req.body_text.strip():
        raise HTTPException(status_code=400, detail="Subject and message body are required.")

    if req.send_immediately:
        return send_email_now(
            db,
            to_email=to_email,
            subject=req.subject.strip(),
            body_text=req.body_text.strip(),
            case_id=cid,
            ai_reason=req.topic.strip() or "Manual compose",
            approved_by=user.full_name,
        )

    cfg = get_gmail_config(db)
    log = EmailMessageLog(
        case_id=cid,
        direction="outbound",
        status="queued_approval",
        to_email=to_email,
        from_email=cfg["gmail_address"] or "pending-gmail-setup",
        subject=req.subject.strip(),
        body_text=req.body_text.strip(),
        whatsapp_text=build_whatsapp_version(req.subject.strip(), req.body_text.strip()),
        ai_reason=req.topic.strip() or "Queued for approval",
        delivery_backend="gmail_smtp" if cfg["smtp_ready"] else ("composio" if cfg["composio_gmail_ready"] else "dry_run"),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return serialize_email_log(log)


@router.post("/messages/{msg_id}/approve")
def approve_and_send_message(
    msg_id: int,
    req: ApproveMessageRequest,
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    log = db.query(EmailMessageLog).filter(EmailMessageLog.id == msg_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Queued message not found.")
    subj = (req.subject if req.subject is not None else log.subject).strip()
    body = (req.body_text if req.body_text is not None else log.body_text).strip()
    return send_email_now(
        db,
        to_email=log.to_email,
        subject=subj,
        body_text=body,
        case_id=log.case_id,
        rule_id=log.rule_id,
        ai_reason=log.ai_reason,
        approved_by=user.full_name,
        existing_log=log,
    )


@router.post("/messages/{msg_id}/reject")
def reject_queued_message(
    msg_id: int,
    user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    log = db.query(EmailMessageLog).filter(EmailMessageLog.id == msg_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Message not found.")
    log.status = "rejected"
    log.approved_by = f"Rejected by {user.full_name}"
    db.commit()
    return serialize_email_log(log)


@router.post("/clients/{case_id}/mute")
def toggle_client_email_mute(
    case_id: str,
    muted: bool = True,
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found.")
    c.email_muted = muted
    db.commit()
    return {"case_id": c.case_id, "email_muted": bool(c.email_muted)}


@router.post("/poll-inbox")
def poll_inbox_now(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return poll_gmail_inbox(db, limit=25)


@router.post("/sync-hermes-cron")
def sync_hermes_cron(
    _user: User = Depends(require_roles("ceo", "staff")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return sync_rules_to_hermes_cron(db)
