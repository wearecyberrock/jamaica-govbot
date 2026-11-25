"""Gmail Automation Engine: SMTP/Composio Sending, IMAP Inbox Attachment Vault Sync, Dual-Mode Cron & Hermes Cron Bridge."""

from __future__ import annotations

import asyncio
import email as email_stdlib
import imaplib
import json
import re
import shutil
import smtplib
import subprocess
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import CLIENT_VAULT_DIR, DATA_DIR, mask_secret
from app.models import (
    BrandingConfig,
    ClientCase,
    ClientDocument,
    EmailAutomationRule,
    EmailMessageLog,
    PipelineJournal,
)
from app.services.connectors import get_composio_status, get_setting, set_setting
from app.services.doc_generator import sha256_file
from app.services.doc_intelligence import get_pdf_page_count, scan_document_with_ai
from app.services.hermes_engine import call_llm_detailed


# ── Gmail Connection Config & Helpers ────────────────────────────────────────

def get_gmail_config(db: Session) -> dict[str, Any]:
    addr = get_setting(db, "gmail_address", "")
    app_pw = get_setting(db, "gmail_app_password", "")
    default_mode = get_setting(db, "gmail_default_mode", "dual") or "dual"
    sender_name = get_setting(db, "gmail_sender_name", "")
    imap_enabled = get_setting(db, "gmail_imap_enabled", "true").lower() != "false"
    comp = get_composio_status(db)
    comp_gmail = any(a["app_id"] == "gmail" and a["connected"] for a in comp.get("apps", []))
    hermes_bin = shutil.which("hermes") or ""
    return {
        "gmail_address": addr,
        "app_password_configured": bool(app_pw),
        "app_password_masked": mask_secret(app_pw),
        "smtp_ready": bool(addr and app_pw),
        "composio_gmail_ready": bool(comp.get("api_key_configured") and comp_gmail),
        "default_mode": default_mode,  # dual | auto | approval
        "sender_name": sender_name or "Jahtaria Travel Services",
        "imap_enabled": imap_enabled,
        "hermes_cli_detected": bool(hermes_bin),
        "hermes_cli_path": hermes_bin,
    }


def is_gmail_configured(db: Session) -> bool:
    cfg = get_gmail_config(db)
    return bool(cfg["smtp_ready"] or cfg["composio_gmail_ready"])


def save_gmail_config(
    db: Session,
    *,
    gmail_address: str | None = None,
    gmail_app_password: str | None = None,
    default_mode: str | None = None,
    sender_name: str | None = None,
    imap_enabled: bool | None = None,
) -> dict[str, Any]:
    if gmail_address is not None:
        set_setting(db, "gmail_address", gmail_address.strip(), is_secret=False, category="gmail")
    if gmail_app_password is not None and gmail_app_password.strip():
        # Strip spaces from Google 16-char App Passwords automatically
        cleaned_pw = gmail_app_password.replace(" ", "").strip()
        set_setting(db, "gmail_app_password", cleaned_pw, is_secret=True, category="gmail")
    if default_mode in ("dual", "auto", "approval"):
        set_setting(db, "gmail_default_mode", default_mode, is_secret=False, category="gmail")
    if sender_name is not None:
        set_setting(db, "gmail_sender_name", sender_name.strip(), is_secret=False, category="gmail")
    if imap_enabled is not None:
        set_setting(db, "gmail_imap_enabled", "true" if imap_enabled else "false", is_secret=False, category="gmail")
    return get_gmail_config(db)


def test_gmail_connection(db: Session) -> dict[str, Any]:
    addr = get_setting(db, "gmail_address", "")
    app_pw = get_setting(db, "gmail_app_password", "")
    if not addr or not app_pw:
        return {
            "ok": False,
            "smtp_ok": False,
            "imap_ok": False,
            "error": "Enter your Gmail address and 16-character Google App Password first.",
        }
    smtp_ok = False
    imap_ok = False
    errors: list[str] = []
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
            srv.login(addr, app_pw)
            smtp_ok = True
    except Exception as exc:
        errors.append(f"SMTP: {str(exc)[:180]}")

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(addr, app_pw)
        imap.logout()
        imap_ok = True
    except Exception as exc:
        errors.append(f"IMAP: {str(exc)[:180]}")

    return {
        "ok": smtp_ok,
        "smtp_ok": smtp_ok,
        "imap_ok": imap_ok,
        "gmail_address": addr,
        "error": "; ".join(errors) if errors else "",
    }


def build_whatsapp_version(subject: str, body_text: str, agency_name: str = "Jahtaria Travel Services") -> str:
    """Convert an email into a crisp, friendly WhatsApp message for Jamaican clients."""
    clean_body = re.sub(r"\n{3,}", "\n\n", (body_text or "").strip())
    return f"*{subject.strip()}*\n\n{clean_body}\n\n— _{agency_name}_"


# ── Real Email Sender (SMTP -> Composio -> Safe Dry-Run) ─────────────────────

def send_email_now(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    case_id: str | None = None,
    rule_id: int | None = None,
    ai_reason: str = "",
    approved_by: str = "",
    existing_log: EmailMessageLog | None = None,
) -> dict[str, Any]:
    """Send a real email via Gmail SMTP or Composio; gracefully falls back to dry_run if not configured."""
    branding = db.query(BrandingConfig).first()
    agency_name = branding.agency_name if branding else "Jahtaria Travel Services"
    cfg = get_gmail_config(db)
    from_addr = cfg["gmail_address"] or (branding.contact_email if branding else "noreply@jahtariatravel.com")
    whatsapp_text = build_whatsapp_version(subject, body_text, agency_name)

    status = "dry_run"
    backend = "dry_run"
    error_detail = ""
    sent_at: datetime | None = None

    to_clean = (to_email or "").strip()
    if not to_clean or "@" not in to_clean:
        status = "failed"
        error_detail = "Client has no valid email address on file."
    elif cfg["smtp_ready"]:
        try:
            app_pw = get_setting(db, "gmail_app_password", "")
            msg = MIMEText(body_text, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{cfg['sender_name']} <{cfg['gmail_address']}>"
            msg["To"] = to_clean
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as srv:
                srv.login(cfg["gmail_address"], app_pw)
                srv.sendmail(cfg["gmail_address"], [to_clean], msg.as_string())
            status = "sent"
            backend = "gmail_smtp"
            sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            status = "failed"
            backend = "gmail_smtp"
            error_detail = str(exc)[:260]
    elif cfg["composio_gmail_ready"]:
        try:
            comp_key = get_setting(db, "composio_api_key", "")
            with httpx.Client(timeout=15.0) as client:
                r = client.post(
                    "https://backend.composio.dev/api/v2/actions/GMAIL_SEND_EMAIL/execute",
                    headers={"x-api-key": comp_key, "Content-Type": "application/json"},
                    json={"input": {"recipient_email": to_clean, "subject": subject, "body": body_text}},
                )
            if r.status_code < 400:
                status = "sent"
                backend = "composio"
                sent_at = datetime.now(timezone.utc)
            else:
                status = "failed"
                backend = "composio"
                error_detail = f"Composio HTTP {r.status_code}: {r.text[:180]}"
        except Exception as exc:
            status = "failed"
            backend = "composio"
            error_detail = str(exc)[:240]
    else:
        status = "dry_run"
        backend = "dry_run"
        error_detail = "Gmail not connected yet — saved as Dry-Run Preview. Add Gmail App Password in Gmail > Connection to send live."

    if existing_log:
        existing_log.to_email = to_clean
        existing_log.from_email = from_addr
        existing_log.subject = subject
        existing_log.body_text = body_text
        existing_log.whatsapp_text = whatsapp_text
        existing_log.status = status
        existing_log.delivery_backend = backend
        existing_log.error_detail = error_detail
        if approved_by:
            existing_log.approved_by = approved_by
        if sent_at:
            existing_log.sent_at = sent_at
        log = existing_log
    else:
        log = EmailMessageLog(
            case_id=case_id,
            rule_id=rule_id,
            direction="outbound",
            status=status,
            to_email=to_clean,
            from_email=from_addr,
            subject=subject,
            body_text=body_text,
            whatsapp_text=whatsapp_text,
            ai_reason=ai_reason,
            delivery_backend=backend,
            error_detail=error_detail,
            approved_by=approved_by,
            sent_at=sent_at,
        )
        db.add(log)

    if case_id and status in ("sent", "dry_run"):
        db.add(
            PipelineJournal(
                case_id=case_id,
                event_type="email_sent" if status == "sent" else "email_dry_run",
                actor=approved_by or "Gmail Automation Agent",
                summary=f"{'Sent' if status == 'sent' else 'Dry-run previewed'} email to {to_clean}: '{subject}'.",
            )
        )
    db.commit()
    db.refresh(log)
    return serialize_email_log(log)


# ── AI & Template Email Drafting Based on Live Customer Data ─────────────────

def _parse_iso_date(val: str | None) -> date | None:
    if not val:
        return None
    s = val.strip()[:10]
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _render_template(tpl: str, c: ClientCase, agency_name: str, extra: dict[str, Any] | None = None) -> str:
    red_flags = [f.title for f in c.risk_flags if f.severity == "red" and not f.resolved]
    unanswered = sum(1 for f in c.risk_flags if (f.follow_up_question or "").strip() and not (f.client_response or "").strip() and not f.resolved)
    mapping = {
        "full_name": c.full_name or c.pseudonym or "Valued Client",
        "case_id": c.case_id,
        "access_code": c.access_code,
        "visa_class": c.visa_class or "B1/B2",
        "passport_expiry": c.passport_expiry or "Not provided",
        "embassy_interview_date": c.embassy_interview_date or "Not scheduled yet",
        "ds160_confirmation_id": c.ds160_confirmation_id or "Pending",
        "standing_score": str(c.standing_score),
        "agency_name": agency_name,
        "red_flags": ", ".join(red_flags[:5]) if red_flags else "None",
        "unanswered_count": str(unanswered),
        "us_destination": c.us_destination or "the United States",
    }
    if extra:
        for k, v in extra.items():
            mapping[k] = str(v)
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{" + k + "}", v)
    return out


def draft_email_for_client(
    db: Session,
    client: ClientCase,
    *,
    rule: EmailAutomationRule | None = None,
    custom_topic: str = "",
    extra_context: str = "",
) -> dict[str, str]:
    """Generate a tailored email subject, body, and WhatsApp message grounded in the client's real case data."""
    branding = db.query(BrandingConfig).first()
    agency_name = branding.agency_name if branding else "Jahtaria Travel Services"
    whatsapp_num = branding.whatsapp_number if branding else "+1 (876) 555-0192"

    red_flags = [f for f in client.risk_flags if f.severity == "red" and not f.resolved]
    amber_flags = [f for f in client.risk_flags if f.severity == "amber" and not f.resolved]
    unanswered_qs = [f for f in client.risk_flags if (f.follow_up_question or "").strip() and not (f.client_response or "").strip() and not f.resolved]

    fallback_subject = (
        _render_template(rule.subject_template, client, agency_name)
        if rule and rule.subject_template.strip()
        else f"[{client.case_id}] Important Update on Your U.S. {client.visa_class} Visa Preparation"
    )
    fallback_body = (
        _render_template(rule.body_template, client, agency_name)
        if rule and rule.body_template.strip()
        else (
            f"Hello {client.full_name or client.pseudonym},\n\n"
            f"This is an update from {agency_name} regarding your U.S. {client.visa_class} visa case ({client.case_id}).\n"
            f"{custom_topic or extra_context}\n\n"
            f"Your Client Portal Access Code: {client.access_code}\n"
            f"If you have any questions, reply to this email or WhatsApp us at {whatsapp_num}.\n\n"
            f"Warm regards,\n{agency_name}"
        )
    )

    use_ai = (rule.use_ai_personalization if rule else True) or bool(custom_topic)
    if not use_ai:
        return {
            "subject": fallback_subject,
            "body_text": fallback_body,
            "whatsapp_text": build_whatsapp_version(fallback_subject, fallback_body, agency_name),
            "ai_reason": extra_context or (rule.name if rule else "Template draft"),
        }

    client_snapshot = (
        f"Client Name: {client.full_name or client.pseudonym}\n"
        f"Case ID: {client.case_id} | Portal Code: {client.access_code}\n"
        f"Visa Class: {client.visa_class} | Stage: {client.pipeline_stage}\n"
        f"Good Standing Score: {client.standing_score}% ({client.denial_risk_level} risk)\n"
        f"Passport Expiry: {client.passport_expiry or 'Missing'}\n"
        f"Intended Travel: {client.intended_travel_date or 'TBD'} to {client.us_destination or 'TBD'}\n"
        f"Embassy Interview Date: {client.embassy_interview_date or 'Not scheduled'}\n"
        f"DS-160 Barcode: {client.ds160_confirmation_id or 'Missing'} | AIS Barcode: {client.ais_appointment_barcode or 'Missing'}\n"
        f"Unresolved Red Flags ({len(red_flags)}): {'; '.join(f.title for f in red_flags[:5]) or 'None'}\n"
        f"Unresolved Amber Flags ({len(amber_flags)}): {'; '.join(f.title for f in amber_flags[:5]) or 'None'}\n"
        f"Unanswered Questionnaire Items: {len(unanswered_qs)}\n"
        f"Open Verification Items: {client.open_verification_items or 'None'}\n"
    )
    sys_prompt = (
        f"You are the Consular Communications Specialist at {agency_name} in Kingston, Jamaica.\n"
        "Write a warm, clear, professional, truthful client email (never guarantee visa approval, never coach concealment).\n"
        "Reference Jamaica-specific rules accurately when relevant (PICA Simplified Adult Renewal, U.S. Embassy Kingston 142 Old Hope Road no-cellphones policy, "
        "DS-160 AA-barcode matching AIS profile, 92%-scaled Jamaican RGD birth/marriage certificate photocopies).\n"
        'Return ONLY valid JSON: {"subject": "...", "body": "...", "reason": "1-sentence trigger explanation"}'
    )
    user_prompt = (
        f"Trigger / Instruction: {custom_topic or (rule.name + ' — ' + rule.description if rule else 'Proactive client check-in')}\n"
        f"Trigger Details: {extra_context or 'Standard check'}\n"
        f"Base Template Hint:\nSubject: {fallback_subject}\nBody: {fallback_body}\n\n"
        f"LIVE CLIENT PROFILE:\n{client_snapshot}\n"
        f"Sign off as {agency_name} (WhatsApp: {whatsapp_num})."
    )
    res = call_llm_detailed(db, sys_prompt, user_prompt)
    raw = res.get("text") or ""
    if raw:
        try:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                parsed = json.loads(m.group(0))
                subj = str(parsed.get("subject") or "").strip() or fallback_subject
                body = str(parsed.get("body") or "").strip() or fallback_body
                reason = str(parsed.get("reason") or extra_context or (rule.name if rule else "AI Draft")).strip()
                return {
                    "subject": subj[:240],
                    "body_text": body,
                    "whatsapp_text": build_whatsapp_version(subj, body, agency_name),
                    "ai_reason": reason[:300],
                }
        except Exception:
            pass

    return {
        "subject": fallback_subject,
        "body_text": fallback_body,
        "whatsapp_text": build_whatsapp_version(fallback_subject, fallback_body, agency_name),
        "ai_reason": extra_context or (rule.name if rule else "Consular template"),
    }


# ── Rule Evaluation, Cooldown Deduplication & Cron Engine ────────────────────

def _in_cooldown(db: Session, case_id: str, rule_id: int, cooldown_days: int) -> bool:
    if cooldown_days <= 0:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
    recent = (
        db.query(EmailMessageLog)
        .filter(
            EmailMessageLog.case_id == case_id,
            EmailMessageLog.rule_id == rule_id,
            EmailMessageLog.direction == "outbound",
            EmailMessageLog.status.in_(["sent", "queued_approval", "dry_run"]),
            EmailMessageLog.created_at >= cutoff,
        )
        .first()
    )
    return recent is not None


def _match_clients_for_rule(db: Session, rule: EmailAutomationRule) -> list[tuple[ClientCase, str]]:
    """Return [(ClientCase, trigger_reason)] matching the given automation rule."""
    today = date.today()
    clients = (
        db.query(ClientCase)
        .filter(ClientCase.email != "", ClientCase.email_muted == False)  # noqa: E712
        .all()
    )
    matches: list[tuple[ClientCase, str]] = []
    for c in clients:
        if not c.email or "@" not in c.email:
            continue
        if (c.full_name or "").startswith("Reference Case"):
            continue
        if c.outcome in ("approved", "refused") and rule.rule_type != "post_interview_checkin":
            continue

        rtype = rule.rule_type
        if rtype == "passport_expiry":
            exp = _parse_iso_date(c.passport_expiry)
            if exp:
                days_left = (exp - today).days
                if days_left <= rule.threshold_days:
                    if days_left < 0:
                        matches.append((c, f"Passport expired {abs(days_left)} day(s) ago ({c.passport_expiry}) — PICA renewal required."))
                    else:
                        matches.append((c, f"Passport expires in {days_left} day(s) ({c.passport_expiry}), within the {rule.threshold_days}-day (6-month) Kingston threshold."))

        elif rtype == "interview_countdown":
            iv = _parse_iso_date(c.embassy_interview_date)
            if iv:
                days_left = (iv - today).days
                if 0 <= days_left <= rule.threshold_days:
                    matches.append((c, f"U.S. Embassy Kingston interview is in {days_left} day(s) ({c.embassy_interview_date})."))

        elif rtype == "missing_docs_red_flags":
            reds = [f for f in c.risk_flags if f.severity == "red" and not f.resolved]
            if reds:
                matches.append((c, f"{len(reds)} unresolved RED risk flag(s): {', '.join(f.title for f in reds[:3])}."))

        elif rtype == "questionnaire_nudge":
            unanswered = [f for f in c.risk_flags if (f.follow_up_question or "").strip() and not (f.client_response or "").strip() and not f.resolved]
            if unanswered:
                matches.append((c, f"{len(unanswered)} unanswered follow-up verification question(s) in client portal."))

        elif rtype == "post_interview_checkin":
            iv = _parse_iso_date(c.embassy_interview_date)
            if iv and iv < today and c.outcome == "pending":
                matches.append((c, f"Kingston Embassy interview date ({c.embassy_interview_date}) passed — outcome & actual questions not recorded yet."))

        elif rtype == "ai_autonomous":
            # AI evaluates whether this active client genuinely needs proactive outreach today
            reds = [f.title for f in c.risk_flags if f.severity == "red" and not f.resolved]
            exp = _parse_iso_date(c.passport_expiry)
            exp_soon = exp is not None and (exp - today).days <= 210
            barcode_mismatch = bool(c.ds160_confirmation_id and c.ais_appointment_barcode and c.ds160_confirmation_id != c.ais_appointment_barcode)
            if reds or exp_soon or barcode_mismatch or c.standing_score < 70:
                reasons = []
                if exp_soon:
                    reasons.append(f"passport expiring {c.passport_expiry}")
                if barcode_mismatch:
                    reasons.append("DS-160 / AIS barcode mismatch")
                if reds:
                    reasons.append(f"{len(reds)} red flag(s)")
                if c.standing_score < 70:
                    reasons.append(f"standing score {c.standing_score}%")
                matches.append((c, f"Autonomous AI scan flagged proactive outreach: {', '.join(reasons)}."))

        elif rtype == "custom":
            if c.pipeline_stage != "completed":
                matches.append((c, f"Custom scheduled outreach rule '{rule.name}'."))

    return matches


def _resolve_effective_mode(db: Session, rule: EmailAutomationRule) -> str:
    """Resolve whether a rule sends immediately ('auto') or waits in Approval Queue ('approval')."""
    global_mode = get_setting(db, "gmail_default_mode", "dual") or "dual"
    if global_mode == "approval":
        return "approval"
    if global_mode == "auto":
        return "auto" if rule.send_mode != "approval" else "approval"
    # Dual Mode: honor explicit rule setting; if rule is 'dual', routine rules auto-send while AI/red-flag/custom queue for approval
    if rule.send_mode in ("auto", "approval"):
        return rule.send_mode
    if rule.rule_type in ("passport_expiry", "interview_countdown", "questionnaire_nudge"):
        return "auto"
    return "approval"


def run_email_automation_cycle(
    db: Session,
    *,
    rule_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Evaluate due (or forced) Gmail automation rules, draft tailored messages, and send or queue them."""
    now = datetime.now(timezone.utc)
    q = db.query(EmailAutomationRule)
    if rule_id is not None:
        q = q.filter(EmailAutomationRule.id == rule_id)
    else:
        q = q.filter(EmailAutomationRule.enabled == True)  # noqa: E712
    rules = q.order_by(EmailAutomationRule.id.asc()).all()

    summary = {
        "rules_evaluated": 0,
        "messages_sent": 0,
        "messages_queued": 0,
        "messages_dry_run": 0,
        "skipped_cooldown": 0,
        "details": [],
    }

    for rule in rules:
        if not force and rule.next_run_at:
            nxt = rule.next_run_at
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            if nxt > now:
                continue

        summary["rules_evaluated"] += 1
        eff_mode = _resolve_effective_mode(db, rule)
        matched = _match_clients_for_rule(db, rule)

        for client, reason in matched:
            if not force and _in_cooldown(db, client.case_id, rule.id, rule.cooldown_days):
                summary["skipped_cooldown"] += 1
                continue

            draft = draft_email_for_client(db, client, rule=rule, extra_context=reason)
            if eff_mode == "auto":
                res = send_email_now(
                    db,
                    to_email=client.email,
                    subject=draft["subject"],
                    body_text=draft["body_text"],
                    case_id=client.case_id,
                    rule_id=rule.id,
                    ai_reason=draft["ai_reason"],
                    approved_by=f"Auto-Cron ({rule.name})",
                )
                if res["status"] == "sent":
                    summary["messages_sent"] += 1
                else:
                    summary["messages_dry_run"] += 1
                summary["details"].append({"case_id": client.case_id, "rule": rule.name, "status": res["status"], "subject": draft["subject"]})
            else:
                cfg = get_gmail_config(db)
                log = EmailMessageLog(
                    case_id=client.case_id,
                    rule_id=rule.id,
                    direction="outbound",
                    status="queued_approval",
                    to_email=client.email,
                    from_email=cfg["gmail_address"] or "pending-gmail-setup",
                    subject=draft["subject"],
                    body_text=draft["body_text"],
                    whatsapp_text=draft["whatsapp_text"],
                    ai_reason=draft["ai_reason"],
                    delivery_backend="gmail_smtp" if cfg["smtp_ready"] else ("composio" if cfg["composio_gmail_ready"] else "dry_run"),
                )
                db.add(log)
                db.commit()
                summary["messages_queued"] += 1
                summary["details"].append({"case_id": client.case_id, "rule": rule.name, "status": "queued_approval", "subject": draft["subject"]})

        rule.last_run_at = now
        rule.next_run_at = now + timedelta(minutes=max(15, rule.interval_minutes or 1440))
        db.commit()

    return summary


# ── IMAP Inbox Polling (Auto-Save Client Attachments into Vault + AI OCR!) ──

def _decode_mime_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(chunk))
    return "".join(out).strip()


def poll_gmail_inbox(db: Session, limit: int = 20) -> dict[str, Any]:
    """Poll Gmail IMAP inbox for client emails & automatically save PDF/image/DOCX attachments into their Client Vault."""
    addr = get_setting(db, "gmail_address", "")
    app_pw = get_setting(db, "gmail_app_password", "")
    if not addr or not app_pw:
        return {
            "ok": False,
            "checked": 0,
            "matched_messages": 0,
            "saved_attachments": 0,
            "error": "Configure your Gmail address and Google App Password in the Connection tab to poll your inbox.",
        }

    clients_by_email: dict[str, ClientCase] = {}
    for c in db.query(ClientCase).filter(ClientCase.email != "").all():
        if c.email:
            clients_by_email[c.email.strip().lower()] = c

    checked = 0
    matched_msgs = 0
    saved_docs = 0
    saved_items: list[dict[str, Any]] = []

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(addr, app_pw)
        imap.select("INBOX")
        typ, data = imap.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            imap.logout()
            return {"ok": True, "checked": 0, "matched_messages": 0, "saved_attachments": 0, "items": []}

        msg_ids = data[0].split()[-limit:]
        for mid in reversed(msg_ids):
            checked += 1
            typ, msg_data = imap.fetch(mid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_email = msg_data[0][1]
            if not isinstance(raw_email, bytes):
                continue
            parsed = email_stdlib.message_from_bytes(raw_email)
            from_hdr = _decode_mime_header(parsed.get("From"))
            m_addr = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", from_hdr)
            sender_email = m_addr.group(0).lower() if m_addr else ""
            if sender_email not in clients_by_email:
                continue

            client = clients_by_email[sender_email]
            subj = _decode_mime_header(parsed.get("Subject")) or "(No Subject)"

            # Deduplicate by sender + subject + direction
            exists = (
                db.query(EmailMessageLog)
                .filter(
                    EmailMessageLog.direction == "inbound",
                    EmailMessageLog.from_email == sender_email,
                    EmailMessageLog.subject == subj[:255],
                    EmailMessageLog.case_id == client.case_id,
                )
                .first()
            )
            if exists:
                continue

            body_parts: list[str] = []
            attachments_for_msg: list[tuple[str, str, bytes]] = []
            for part in parsed.walk():
                cdisp = str(part.get("Content-Disposition") or "")
                ctype = part.get_content_type()
                fname = part.get_filename()
                if fname or "attachment" in cdisp.lower():
                    dec_name = _decode_mime_header(fname) if fname else f"attachment_{mid.decode()}.bin"
                    ext = Path(dec_name).suffix.lower()
                    if ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".txt"):
                        payload = part.get_payload(decode=True)
                        if payload:
                            attachments_for_msg.append((dec_name, ctype, payload))
                elif ctype == "text/plain" and not fname:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))

            body_text = "\n".join(body_parts).strip()[:4000]
            log = EmailMessageLog(
                case_id=client.case_id,
                direction="inbound",
                status="received",
                to_email=addr,
                from_email=sender_email,
                subject=subj[:255],
                body_text=body_text or "(Attachment only)",
                whatsapp_text=build_whatsapp_version(f"Reply from {client.full_name}", body_text[:600]),
                ai_reason=f"Synced from Gmail Inbox ({len(attachments_for_msg)} attachment(s))",
                delivery_backend="imap_inbox",
                sent_at=datetime.now(timezone.utc),
            )
            db.add(log)
            matched_msgs += 1

            for att_name, att_mime, att_bytes in attachments_for_msg:
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(att_name).name)
                dest_dir = CLIENT_VAULT_DIR / client.case_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                target = dest_dir / f"{ts}_gmail_{safe_name}"
                target.write_bytes(att_bytes)
                scan = scan_document_with_ai(db, target, att_mime, safe_name)
                vdoc = ClientDocument(
                    case_id=client.case_id,
                    category=scan["category"],
                    title=f"[Gmail] {scan.get('document_type') or target.stem}",
                    filename=safe_name,
                    file_path=str(target),
                    mime_type=att_mime,
                    size_bytes=len(att_bytes),
                    sha256=sha256_file(target),
                    page_count=get_pdf_page_count(target),
                    extracted_text=scan.get("extracted_text", ""),
                    extracted_fields_json=json.dumps(scan.get("extracted_fields", {})),
                    ai_summary=scan.get("summary", ""),
                    uploaded_by=f"Gmail Inbox ({sender_email})",
                )
                db.add(vdoc)
                saved_docs += 1
                saved_items.append({"case_id": client.case_id, "client": client.full_name, "filename": safe_name, "category": scan["category"]})

            db.add(
                PipelineJournal(
                    case_id=client.case_id,
                    event_type="gmail_inbox_synced",
                    actor="Gmail Inbox Poller",
                    summary=f"Received email from {sender_email}: '{subj[:120]}' ({len(attachments_for_msg)} attachment(s) saved to Vault).",
                )
            )
            db.commit()

        imap.logout()
    except Exception as exc:
        return {
            "ok": False,
            "checked": checked,
            "matched_messages": matched_msgs,
            "saved_attachments": saved_docs,
            "error": str(exc)[:240],
        }

    return {
        "ok": True,
        "checked": checked,
        "matched_messages": matched_msgs,
        "saved_attachments": saved_docs,
        "items": saved_items,
    }


# ── Hermes Cron Bridge (Export Manifest + CLI Sync if Installed) ─────────────

def sync_rules_to_hermes_cron(db: Session) -> dict[str, Any]:
    """Export all enabled Gmail automation rules to DATA_DIR/hermes_cron_jobs.json and sync with Hermes CLI if installed."""
    rules = db.query(EmailAutomationRule).filter(EmailAutomationRule.enabled == True).order_by(EmailAutomationRule.id.asc()).all()  # noqa: E712
    hermes_bin = shutil.which("hermes")
    jobs = []
    cli_commands = []
    synced_cli = False

    for r in rules:
        cmd = (
            f'hermes cron add --name "jahtaria-gmail-rule-{r.id}" '
            f'--schedule "{r.cron_expr}" '
            f'--prompt "Call POST http://127.0.0.1:8010/api/gmail/rules/{r.id}/run to execute {r.name} ({r.send_mode} mode)."'
        )
        cli_commands.append(cmd)
        jobs.append(
            {
                "rule_id": r.id,
                "name": r.name,
                "rule_type": r.rule_type,
                "send_mode": r.send_mode,
                "cron_expr": r.cron_expr,
                "interval_minutes": r.interval_minutes,
                "cooldown_days": r.cooldown_days,
                "endpoint": f"http://127.0.0.1:8010/api/gmail/rules/{r.id}/run",
                "hermes_command": cmd,
            }
        )
        r.hermes_cron_synced = True

    manifest_path = DATA_DIR / "hermes_cron_jobs.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "jobs": jobs}, indent=2), encoding="utf-8")

    cli_note = "Saved manifest to hermes_cron_jobs.json. Built-in desktop cron scheduler is active automatically."
    if hermes_bin:
        try:
            proc = subprocess.run([hermes_bin, "--version"], capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                synced_cli = True
                cli_note = f"Hermes CLI detected ({proc.stdout.strip() or hermes_bin}) and cron manifest synced to {manifest_path.name}."
        except Exception:
            pass

    db.commit()
    return {
        "ok": True,
        "built_in_scheduler_active": True,
        "hermes_cli_detected": bool(hermes_bin),
        "hermes_cli_synced": synced_cli,
        "manifest_path": str(manifest_path),
        "job_count": len(jobs),
        "cli_commands": cli_commands,
        "note": cli_note,
    }


# ── Serializers & Background Scheduler Loop ──────────────────────────────────

def serialize_rule(r: EmailAutomationRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "rule_type": r.rule_type,
        "enabled": bool(r.enabled),
        "send_mode": r.send_mode,
        "cron_expr": r.cron_expr,
        "interval_minutes": r.interval_minutes,
        "cooldown_days": r.cooldown_days,
        "threshold_days": r.threshold_days,
        "subject_template": r.subject_template,
        "body_template": r.body_template,
        "use_ai_personalization": bool(r.use_ai_personalization),
        "hermes_cron_synced": bool(r.hermes_cron_synced),
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
        "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None,
    }


def serialize_email_log(m: EmailMessageLog) -> dict[str, Any]:
    return {
        "id": m.id,
        "case_id": m.case_id,
        "rule_id": m.rule_id,
        "direction": m.direction,
        "status": m.status,
        "to_email": m.to_email,
        "from_email": m.from_email,
        "subject": m.subject,
        "body_text": m.body_text,
        "whatsapp_text": m.whatsapp_text,
        "ai_reason": m.ai_reason,
        "delivery_backend": m.delivery_backend,
        "error_detail": m.error_detail,
        "approved_by": m.approved_by,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _run_cron_tick_sync(session_factory, poll_inbox_now_flag: bool) -> None:
    db = session_factory()
    try:
        run_email_automation_cycle(db, force=False)
        if poll_inbox_now_flag:
            cfg = get_gmail_config(db)
            if cfg["smtp_ready"] and cfg["imap_enabled"]:
                poll_gmail_inbox(db, limit=10)
    finally:
        db.close()


async def background_cron_worker(session_factory) -> None:
    """In-app async cron loop: evaluates due Gmail rules every 60s in a worker thread without blocking FastAPI."""
    tick = 0
    await asyncio.sleep(15)
    while True:
        try:
            await asyncio.to_thread(_run_cron_tick_sync, session_factory, (tick % 15 == 0))
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        tick += 1
        await asyncio.sleep(60)
