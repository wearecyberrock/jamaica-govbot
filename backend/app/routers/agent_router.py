"""Customer Portal AI Q&A Chat & Staff Autonomous Hermes Agent ("Hands") Router."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import ChatMessage, ClientCase, User
from app.services.hermes_engine import answer_customer_question, run_staff_agent_loop

router = APIRouter(prefix="/api/agent", tags=["agent"])


class CustomerChatRequest(BaseModel):
    message: str
    session_id: str = "portal-default"


class StaffAgentRequest(BaseModel):
    instruction: str
    case_id: str | None = None
    session_id: str = "staff-hermes"


@router.post("/customer-chat")
def customer_chat(
    req: CustomerChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cid = user.linked_case_id or "C034"
    client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()
    sess = f"customer-{user.id}-{req.session_id}"

    db.add(ChatMessage(session_id=sess, case_id=cid, user_role=user.role, sender="user", content=req.message.strip()))
    res = answer_customer_question(db, req.message.strip(), client)
    db.add(
        ChatMessage(
            session_id=sess,
            case_id=cid,
            user_role=user.role,
            sender="assistant",
            content=res["reply"],
            tool_trace_json=json.dumps(res.get("citations", [])),
            provider_used=res["provider_used"],
        )
    )
    db.commit()
    return res


@router.post("/staff-run")
def staff_agent_run(
    req: StaffAgentRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sess = f"staff-{req.case_id or 'global'}-{req.session_id}"
    db.add(ChatMessage(session_id=sess, case_id=req.case_id, user_role=user.role, sender="user", content=req.instruction.strip()))
    res = run_staff_agent_loop(db, req.instruction.strip(), case_id=req.case_id, actor=f"Hermes ({user.full_name})")
    db.add(
        ChatMessage(
            session_id=sess,
            case_id=res.get("case_id"),
            user_role=user.role,
            sender="assistant",
            content=res["reply"],
            tool_trace_json=json.dumps(res.get("tool_trace", [])),
            provider_used=res["provider_used"],
        )
    )
    db.commit()
    return res


@router.get("/history")
def get_chat_history(
    case_id: str | None = None,
    mode: str = "customer",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    q = db.query(ChatMessage)
    if mode == "customer":
        cid = user.linked_case_id or "C034"
        q = q.filter(ChatMessage.case_id == cid, ChatMessage.session_id.like(f"customer-{user.id}-%"))
    elif case_id:
        q = q.filter(ChatMessage.case_id == case_id.upper(), ChatMessage.session_id.like("staff-%"))
    else:
        q = q.filter(ChatMessage.session_id.like("staff-%"))

    rows = q.order_by(ChatMessage.id.asc()).limit(60).all()
    out = []
    for m in rows:
        trace = []
        try:
            trace = json.loads(m.tool_trace_json or "[]")
        except Exception:
            pass
        out.append(
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content,
                "trace": trace,
                "provider_used": m.provider_used,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return out
