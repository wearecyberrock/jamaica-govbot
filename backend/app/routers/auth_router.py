"""Authentication, Username Sign-In, Forgot Password (PIN + CEO + Gmail OTP), One-Time CEO Setup & All-Tier Test Account."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, require_roles, verify_password
from app.database import get_db
from app.models import BrandingConfig, ClientCase, PipelineJournal, User
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions

router = APIRouter(prefix="/api", tags=["auth"])


def _normalize_username(raw: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "", (raw or "").strip().lower())
    return clean[:64]


class SetupCeoRequest(BaseModel):
    full_name: str
    username: str = ""
    email: str = ""
    password: str
    recovery_pin: str = ""
    agency_name: str = ""


class LoginRequest(BaseModel):
    username: str = ""
    email: str = ""
    password: str


class CaseCodeLoginRequest(BaseModel):
    access_code: str
    full_name: str = ""


class CustomerSignupRequest(BaseModel):
    full_name: str
    username: str = ""
    email: str = ""
    password: str
    recovery_pin: str = ""
    phone: str = ""
    visa_class: str = "B1/B2"
    parish: str = ""


class CreateUserRequest(BaseModel):
    full_name: str
    username: str = ""
    email: str = ""
    password: str
    recovery_pin: str = ""
    role: str = "staff"  # staff | customer (only ONE CEO allowed)
    linked_case_id: str | None = None


class ForgotPasswordRequest(BaseModel):
    identifier: str  # username or email


class ResetPasswordConfirmRequest(BaseModel):
    identifier: str  # username or email
    new_password: str
    recovery_pin: str = ""
    reset_code: str = ""


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = ""
    new_username: str = ""
    recovery_pin: str = ""


class CeoResetUserPasswordRequest(BaseModel):
    new_password: str
    new_recovery_pin: str = ""


def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username or (u.email.split("@")[0] if u.email else f"user{u.id}"),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "all_tiers": bool(getattr(u, "all_tiers", False)),
        "has_recovery_pin": bool(getattr(u, "recovery_pin_hash", "")),
        "linked_case_id": u.linked_case_id,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _find_user_by_identifier(db: Session, identifier: str) -> User | None:
    ident = (identifier or "").strip().lower()
    if not ident:
        return None
    return (
        db.query(User)
        .filter(
            User.is_active == True,  # noqa: E712
            or_(User.username == ident, User.email == ident),
        )
        .first()
    )


@router.get("/branding")
def get_public_branding(db: Session = Depends(get_db)) -> dict[str, Any]:
    b = db.query(BrandingConfig).first()
    if not b:
        b = BrandingConfig()
        db.add(b)
        db.commit()
    return {
        "agency_name": b.agency_name,
        "tagline": b.tagline,
        "logo_url": b.logo_url,
        "primary_color": b.primary_color,
        "gold_color": b.gold_color,
        "navy_color": b.navy_color,
        "accent_red": b.accent_red,
        "contact_email": b.contact_email,
        "whatsapp_number": b.whatsapp_number,
        "website_url": b.website_url,
        "compliance_notice": b.compliance_notice,
    }


@router.get("/auth/setup-status")
def get_setup_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Check whether the primary agency owner CEO account has been claimed yet (excludes built-in all-tier testaccount)."""
    ceo_exists = db.query(User).filter(User.role == "ceo", User.all_tiers == False, User.is_active == True).first() is not None  # noqa: E712
    staff_count = db.query(User).filter(User.role == "staff", User.is_active == True).count()  # noqa: E712
    customer_count = db.query(User).filter(User.role == "customer", User.is_active == True).count()  # noqa: E712
    return {
        "ceo_exists": ceo_exists,
        "staff_count": staff_count,
        "customer_count": customer_count,
    }


@router.post("/auth/setup-ceo")
def setup_single_ceo(req: SetupCeoRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    """One-time initialization to create the Agency CEO account."""
    existing_ceo = db.query(User).filter(User.role == "ceo", User.all_tiers == False, User.is_active == True).first()  # noqa: E712
    if existing_ceo:
        raise HTTPException(
            status_code=403,
            detail="A CEO account already exists for this installation. Please sign in or use Forgot Password.",
        )
    uname = _normalize_username(req.username or (req.email.split("@")[0] if req.email else req.full_name))
    if len(uname) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters (letters, numbers, ., _, -).")
    email_norm = (req.email or "").strip().lower() or f"{uname}@local.jahtariatravel.com"
    if db.query(User).filter(or_(User.username == uname, User.email == email_norm)).first():
        raise HTTPException(status_code=409, detail="Username or email is already registered.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    if req.agency_name.strip():
        b = db.query(BrandingConfig).first()
        if b:
            b.agency_name = req.agency_name.strip()

    ceo = User(
        username=uname,
        email=email_norm,
        full_name=req.full_name.strip(),
        role="ceo",
        password_hash=hash_password(req.password),
        recovery_pin_hash=hash_password(req.recovery_pin.strip()) if req.recovery_pin.strip() else "",
        is_active=True,
    )
    db.add(ceo)
    db.commit()
    db.refresh(ceo)

    token = create_access_token(ceo)
    response.set_cookie("govbot_token", token, httponly=True, samesite="lax")
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(ceo)}


@router.post("/auth/login")
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    identifier = (req.username or req.email or "").strip().lower()
    user = _find_user_by_identifier(db, identifier)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = create_access_token(user)
    response.set_cookie("govbot_token", token, httponly=True, samesite="lax")
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}


@router.post("/auth/forgot-password/request")
def request_password_reset(req: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Check recovery options for a username/email and optionally send a 6-digit Gmail OTP."""
    user = _find_user_by_identifier(db, req.identifier)
    if not user:
        raise HTTPException(status_code=404, detail="No active account found with that username.")

    has_pin = bool(getattr(user, "recovery_pin_hash", ""))
    email_sent = False
    email_note = ""

    # If user has a real email (not synthetic @local) and Gmail is configured, send a 6-digit OTP
    if user.email and "@local." not in user.email and "@portal." not in user.email:
        try:
            from app.services.gmail_service import is_gmail_configured, send_email_now

            if is_gmail_configured(db):
                code = f"{secrets.randbelow(900000) + 100000}"
                user.reset_code_hash = hash_password(code)
                user.reset_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
                db.commit()
                res = send_email_now(
                    db,
                    to_email=user.email,
                    subject="Jahtaria Visa Intelligence — Password Reset Code",
                    body_text=(
                        f"Hello {user.full_name},\n\n"
                        f"Your 6-digit password reset code for username '{user.username}' is:\n\n"
                        f"    {code}\n\n"
                        "This code expires in 15 minutes. If you did not request a reset, you can safely ignore this email."
                    ),
                    case_id=user.linked_case_id,
                    ai_reason="Password reset OTP",
                )
                if res.get("status") == "sent":
                    email_sent = True
                    email_note = f"Sent 6-digit reset code to {user.email[:3]}***@{user.email.split('@')[-1]}."
        except Exception:
            pass

    return {
        "found": True,
        "username": user.username,
        "has_recovery_pin": has_pin,
        "email_code_sent": email_sent,
        "email_note": email_note,
        "message": (
            "Enter your Recovery PIN"
            + (" or the 6-digit code sent to your email" if email_sent else "")
            + " to set a new password."
            if (has_pin or email_sent)
            else "No Recovery PIN is set and Gmail is not connected yet. Ask your Agency CEO to reset your password from the Team panel."
        ),
    }


@router.post("/auth/forgot-password/reset")
def confirm_password_reset(req: ResetPasswordConfirmRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Reset password using either the offline Recovery PIN or the 6-digit Gmail OTP code."""
    user = _find_user_by_identifier(db, req.identifier)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    if len(req.new_password or "") < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    verified = False
    if req.recovery_pin.strip() and getattr(user, "recovery_pin_hash", ""):
        if verify_password(req.recovery_pin.strip(), user.recovery_pin_hash):
            verified = True

    if not verified and req.reset_code.strip() and getattr(user, "reset_code_hash", ""):
        exp = user.reset_code_expires_at
        now = datetime.now(timezone.utc)
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp >= now and verify_password(req.reset_code.strip(), user.reset_code_hash):
            verified = True

    if not verified:
        raise HTTPException(status_code=400, detail="Invalid Recovery PIN or expired 6-digit reset code.")

    user.password_hash = hash_password(req.new_password)
    user.reset_code_hash = ""
    user.reset_code_expires_at = None
    db.commit()
    return {"reset": True, "username": user.username, "message": "Password updated successfully! You can now sign in."}


@router.post("/auth/change-password")
def change_own_password(
    req: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Allow any logged-in user to change their password, username, or Recovery PIN."""
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if req.new_username.strip():
        new_u = _normalize_username(req.new_username)
        if len(new_u) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
        conflict = db.query(User).filter(User.username == new_u, User.id != user.id).first()
        if conflict:
            raise HTTPException(status_code=409, detail="That username is already taken.")
        was_test = (user.username or "").lower() == "testaccount"
        user.username = new_u
        if was_test and new_u != "testaccount":
            # Promote out of dev test-switcher mode into a clean commercial CEO account
            user.all_tiers = False

    if req.new_password.strip():
        if len(req.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
        user.password_hash = hash_password(req.new_password)

    if req.recovery_pin.strip():
        if len(req.recovery_pin.strip()) < 4:
            raise HTTPException(status_code=400, detail="Recovery PIN must be at least 4 characters.")
        user.recovery_pin_hash = hash_password(req.recovery_pin.strip())

    db.commit()
    db.refresh(user)
    token = create_access_token(user)
    response.set_cookie("govbot_token", token, httponly=True, samesite="lax")
    return {"updated": True, "access_token": token, "user": _user_dict(user)}


@router.post("/auth/users/{user_id}/reset-password")
def ceo_reset_user_password(
    user_id: int,
    req: CeoResetUserPasswordRequest,
    _ceo: User = Depends(require_roles("ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """CEO admin reset for any Staff or Client user password & recovery PIN."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if len(req.new_password or "") < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    target.password_hash = hash_password(req.new_password)
    if req.new_recovery_pin.strip():
        target.recovery_pin_hash = hash_password(req.new_recovery_pin.strip())
    db.commit()
    return {"reset": True, "user_id": target.id, "username": target.username}


@router.post("/auth/signup")
def customer_signup(req: CustomerSignupRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Clients can self-register their own Customer Portal account anytime using a username."""
    uname = _normalize_username(req.username or (req.email.split("@")[0] if req.email else req.full_name))
    if len(uname) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    email_norm = (req.email or "").strip().lower() or f"{uname}@portal.jahtariatravel.com"
    if db.query(User).filter(or_(User.username == uname, User.email == email_norm)).first():
        raise HTTPException(status_code=409, detail="An account with this username or email already exists.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    next_num = db.query(ClientCase).count() + 1
    case_id = f"C{next_num:03d}"
    while db.query(ClientCase).filter(ClientCase.case_id == case_id).first():
        next_num += 1
        case_id = f"C{next_num:03d}"

    access_code = f"JAH-{case_id}"
    client = ClientCase(
        case_id=case_id,
        access_code=access_code,
        pseudonym=req.full_name.strip(),
        full_name=req.full_name.strip(),
        email=req.email.strip().lower() if req.email.strip() else "",
        phone=req.phone.strip(),
        parish=req.parish.strip(),
        visa_class=req.visa_class.strip() or "B1/B2",
        pipeline_stage="new_intake",
        data_quality="self_signup_intake",
        consent_status="portal_signup",
    )
    db.add(client)
    db.flush()

    user = User(
        username=uname,
        email=email_norm,
        full_name=req.full_name.strip(),
        role="customer",
        password_hash=hash_password(req.password),
        recovery_pin_hash=hash_password(req.recovery_pin.strip()) if req.recovery_pin.strip() else "",
        linked_case_id=case_id,
    )
    db.add(user)
    db.add(
        PipelineJournal(
            case_id=case_id,
            event_type="customer_signup",
            actor=req.full_name.strip(),
            summary=f"New client created account (@{uname}) with Case ID {case_id} and access code {access_code}.",
        )
    )
    db.commit()
    db.refresh(user)

    evaluate_client_standing(db, client)
    generate_ranked_predictions(db, client, author="system_rules")

    token = create_access_token(user)
    response.set_cookie("govbot_token", token, httponly=True, samesite="lax")
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user), "case_id": case_id, "access_code": access_code}


@router.post("/auth/case-code")
def login_with_case_code(req: CaseCodeLoginRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    code = req.access_code.strip().upper()
    client = db.query(ClientCase).filter(ClientCase.access_code == code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Case access code '{code}' not found. Example: JAH-C034")

    user = db.query(User).filter(User.linked_case_id == client.case_id, User.role == "customer").first()
    if not user:
        uname = f"client_{client.case_id.lower()}"
        guest_email = client.email or f"{client.case_id.lower()}@portal.jahtariatravel.com"
        user = User(
            username=uname,
            email=guest_email,
            full_name=req.full_name.strip() or client.full_name or client.pseudonym,
            role="customer",
            password_hash=hash_password(secrets.token_hex(16)),
            linked_case_id=client.case_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user)
    response.set_cookie("govbot_token", token, httponly=True, samesite="lax")
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user), "case_id": client.case_id}


@router.get("/auth/me")
def get_me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": _user_dict(user)}


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("govbot_token")
    return {"status": "logged_out"}


@router.get("/auth/users")
def list_users(_ceo: User = Depends(require_roles("ceo")), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    users = db.query(User).order_by(User.id).all()
    return [_user_dict(u) for u in users]


@router.post("/auth/users")
def create_user(req: CreateUserRequest, _ceo: User = Depends(require_roles("ceo")), db: Session = Depends(get_db)) -> dict[str, Any]:
    """CEO creates Staff or Customer accounts using username (email optional)."""
    if req.role not in ("staff", "customer"):
        raise HTTPException(status_code=400, detail="Only one CEO account is permitted. Create 'staff' or 'customer' accounts here.")
    uname = _normalize_username(req.username or (req.email.split("@")[0] if req.email else req.full_name))
    if len(uname) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    email_norm = (req.email or "").strip().lower() or f"{uname}@local.jahtariatravel.com"
    if db.query(User).filter(or_(User.username == uname, User.email == email_norm)).first():
        raise HTTPException(status_code=409, detail="Username or email already registered.")
    user = User(
        username=uname,
        email=email_norm,
        full_name=req.full_name.strip(),
        role=req.role,
        password_hash=hash_password(req.password),
        recovery_pin_hash=hash_password(req.recovery_pin.strip()) if req.recovery_pin.strip() else "",
        linked_case_id=req.linked_case_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.delete("/auth/users/{user_id}")
def delete_user(user_id: int, ceo: User = Depends(require_roles("ceo")), db: Session = Depends(get_db)) -> dict[str, Any]:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == ceo.id or (target.role == "ceo" and not target.all_tiers):
        raise HTTPException(status_code=400, detail="Cannot delete the primary CEO account.")
    db.delete(target)
    db.commit()
    return {"deleted": True, "user_id": user_id}
