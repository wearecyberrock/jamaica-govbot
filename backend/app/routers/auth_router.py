"""Authentication, One-Time CEO Setup, CEO->Staff Creation, Customer Self-Signup & Case Code Login."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, require_roles, verify_password
from app.database import get_db
from app.models import BrandingConfig, ClientCase, PipelineJournal, User
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions

router = APIRouter(prefix="/api", tags=["auth"])


class SetupCeoRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    agency_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class CaseCodeLoginRequest(BaseModel):
    access_code: str
    full_name: str = ""


class CustomerSignupRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone: str = ""
    visa_class: str = "B1/B2"
    parish: str = ""


class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "staff"  # staff | customer (only ONE CEO allowed)
    linked_case_id: str | None = None


def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "linked_case_id": u.linked_case_id,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


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
    """Check whether the single CEO account has been claimed yet."""
    ceo_exists = db.query(User).filter(User.role == "ceo", User.is_active == True).first() is not None  # noqa: E712
    staff_count = db.query(User).filter(User.role == "staff", User.is_active == True).count()  # noqa: E712
    customer_count = db.query(User).filter(User.role == "customer", User.is_active == True).count()  # noqa: E712
    return {
        "ceo_exists": ceo_exists,
        "staff_count": staff_count,
        "customer_count": customer_count,
    }


@router.post("/auth/setup-ceo")
def setup_single_ceo(req: SetupCeoRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    """One-time initialization to create the single Agency CEO account."""
    existing_ceo = db.query(User).filter(User.role == "ceo", User.is_active == True).first()  # noqa: E712
    if existing_ceo:
        raise HTTPException(
            status_code=403,
            detail="A CEO account already exists for this installation. Please sign in or contact the CEO.",
        )
    email_norm = req.email.strip().lower()
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=409, detail="Email is already registered.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    if req.agency_name.strip():
        b = db.query(BrandingConfig).first()
        if b:
            b.agency_name = req.agency_name.strip()

    ceo = User(
        email=email_norm,
        full_name=req.full_name.strip(),
        role="ceo",
        password_hash=hash_password(req.password),
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
    user = db.query(User).filter(User.email == req.email.strip().lower(), User.is_active == True).first()  # noqa: E712
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user)
    response.set_cookie("govbot_token", token, httponly=True, samesite="lax")
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}


@router.post("/auth/signup")
def customer_signup(req: CustomerSignupRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Clients can self-register their own Customer Portal account anytime."""
    email_norm = req.email.strip().lower()
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
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
        email=email_norm,
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
        email=email_norm,
        full_name=req.full_name.strip(),
        role="customer",
        password_hash=hash_password(req.password),
        linked_case_id=case_id,
    )
    db.add(user)
    db.add(
        PipelineJournal(
            case_id=case_id,
            event_type="customer_signup",
            actor=req.full_name.strip(),
            summary=f"New client created account ({email_norm}) with Case ID {case_id} and access code {access_code}.",
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
        guest_email = client.email or f"{client.case_id.lower()}@portal.jahtariatravel.com"
        user = User(
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
    """CEO creates Staff or Customer accounts. Strictly enforces only ONE CEO account."""
    if req.role not in ("staff", "customer"):
        raise HTTPException(status_code=400, detail="Only one CEO account is permitted. Create 'staff' or 'customer' accounts here.")
    email_norm = req.email.strip().lower()
    if db.query(User).filter(User.email == email_norm).first():
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = User(
        email=email_norm,
        full_name=req.full_name.strip(),
        role=req.role,
        password_hash=hash_password(req.password),
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
    if target.id == ceo.id or target.role == "ceo":
        raise HTTPException(status_code=400, detail="Cannot delete the primary CEO account.")
    db.delete(target)
    db.commit()
    return {"deleted": True, "user_id": user_id}
