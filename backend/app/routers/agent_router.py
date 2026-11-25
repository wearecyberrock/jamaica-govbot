"""Unified Agent-First Command Router — drives both the Chat/Task Canvas AND the Right Artifact Side Panel."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import ChatMessage, ClientCase, GeneratedAsset, OfficialDocument, User
from app.services.hermes_engine import answer_customer_question, run_staff_agent_loop

router = APIRouter(prefix="/api/agent", tags=["agent"])


class CustomerChatRequest(BaseModel):
    message: str
    session_id: str = "portal-default"


class StaffAgentRequest(BaseModel):
    instruction: str
    case_id: str | None = None
    session_id: str = "staff-hermes"


class UnifiedCommandRequest(BaseModel):
    message: str
    mode: str = "chat"  # chat | task
    case_id: str | None = None
    session_id: str = "main"


def _detect_case_id(db: Session, text: str, fallback: str | None) -> str | None:
    m = re.search(r"\b(C\d{3})\b", text.upper())
    if m:
        return m.group(1)
    low = text.lower()
    # Match by client name (e.g. "marcus", "campbell")
    if len(low) >= 4:
        for c in db.query(ClientCase).all():
            nm = (c.full_name or "").lower()
            if nm and not nm.startswith("reference case"):
                parts = [p for p in nm.split() if len(p) >= 4]
                if any(p in low for p in parts):
                    return c.case_id
    return fallback


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
    for d in docs:
        if any(w in d.title.lower() for w in low.split() if len(w) > 4):
            return d.doc_key
    return docs[0].doc_key if docs else None


@router.post("/command")
def unified_agent_command(
    req: UnifiedCommandRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Unified Agent-First command endpoint: runs chat or autonomous Hermes task and returns UI side-panel directives."""
    msg = req.message.strip()
    low = msg.lower()
    role = user.role
    sess = f"{role}-{user.id}-{req.session_id}"

    db.add(ChatMessage(session_id=sess, case_id=req.case_id or user.linked_case_id, user_role=role, sender="user", content=msg))

    ui_panel: dict[str, Any] | None = None
    tool_trace: list[dict[str, Any]] = []
    citations: list[dict[str, str]] = []
    created_assets: list[dict[str, Any]] = []
    reply = ""
    provider = "hermes-local-knowledge"

    # ── CUSTOMER ROLE FLOW ───────────────────────────────────────────────────
    if role == "customer":
        cid = user.linked_case_id or "C034"
        client = db.query(ClientCase).filter(ClientCase.case_id == cid).first()

        if any(k in low for k in ("my status", "good standing", "standing", "my case", "progress", "flag", "score")):
            ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "overview", "title": f"My Case Status ({cid})"}
        elif any(k in low for k in ("intake", "form", "questionnaire", "my detail", "update my", "edit my")):
            ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "intake", "title": "My Details & Questionnaire"}
        elif any(k in low for k in ("mock", "practice", "interview", "simulate", "question")):
            ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "practice", "title": "Practice Mock Interview"}
        elif any(k in low for k in ("doc", "roadmap", "checklist", "pdf", "download", "file", "image")):
            ui_panel = {"panel": "customer_case", "case_id": cid, "subview": "docs", "title": "My Approved Docs & Roadmap"}
        elif any(k in low for k in ("pica", "official", "embassy", "link", "source")):
            ui_panel = {"panel": "gov_sources", "title": "Official U.S. Embassy & PICA Links"}

        res = answer_customer_question(db, msg, client)
        reply = res["reply"]
        citations = res.get("citations", [])
        provider = res["provider_used"]

    # ── CEO / STAFF ROLE FLOW ────────────────────────────────────────────────
    else:
        target_cid = _detect_case_id(db, msg, req.case_id)
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
            and not any(k in low for k in ("ceo", "analytics", "graph", "chart", "recall"))
        )

        # Determine which visual artifact panel to open in the Right Side Panel
        if role == "ceo" and any(k in low for k in ("ceo", "analytics", "graph", "chart", "kpi", "revenue", "approval rate", "recall", "metrics", "overview", "executive")):
            ui_panel = {"panel": "ceo_analytics", "title": "CEO Executive Analytics & Graphs"}
        elif role == "ceo" and any(k in low for k in ("staff", "team", "create account", "new user", "add staff", "manage user", "logins")):
            ui_panel = {"panel": "team", "title": "Team & Staff Account Manager"}
        elif any(k in low for k in ("setting", "setup", "api key", "ollama", "claude", "chatgpt", "composio", "mcp", "brand", "white-label", "white label")):
            ui_panel = {"panel": "settings", "title": "Easy Setup, Providers & MCP"}
        elif any(k in low for k in ("obsidian", "vault", "wikilink", "note")):
            note_path = f"Clients/{target_cid}.md" if target_cid and "client" in low else "Index.md"
            ui_panel = {"panel": "obsidian", "path": note_path, "title": f"Obsidian Vault — {note_path}"}
        elif any(k in low for k in ("database", "sql", "table", "manifest", "csv", "spreadsheet", "import")):
            tbl = "source_manifest" if "manifest" in low else ("gov_sources" if "source" in low else "clients")
            ui_panel = {"panel": "database", "table": tbl, "title": f"Database Explorer ({tbl})"}
        elif any(k in low for k in ("pdf", "pica", "ds-5535", "ds5535", "ds-157", "ds157", "ds-156", "birreq", "passport form", "blueprint")) and not any(k in low for k in ("generate", "draft", "create")):
            doc_key = _match_official_pdf(db, low)
            ui_panel = {"panel": "official_pdfs", "doc_key": doc_key, "title": "Official Government PDF Viewer"}
        elif any(k in low for k in ("source", "scrape", "embassy link", "gov link", "website", "fees")):
            ui_panel = {"panel": "gov_sources", "title": "Official Scraped Gov Sources"}
        elif any(k in low for k in ("all client", "list client", "pipeline", "kanban", "all case", "show case")):
            ui_panel = {"panel": "clients_list", "title": "Client Pipeline & Cases"}
        elif target_cid:
            sub = "overview"
            if any(k in low for k in ("intake", "edit", "form", "questionnaire", "rename")):
                sub = "intake"
            elif any(k in low for k in ("interview", "mock", "predict", "freeze")):
                sub = "interview"
            elif any(k in low for k in ("roadmap", "image", "worksheet", "checklist", "letter", "docx", "generate", "draft", "approve", "asset", "file")):
                sub = "blueprints"
            elif any(k in low for k in ("journal", "history", "timeline", "log")):
                sub = "journal"
            ui_panel = {"panel": "client", "case_id": target_cid, "subview": sub, "title": f"Case {target_cid} Workspace"}

        # Execute Hermes Autonomous Loop if task mode or action verbs detected
        if is_action_task:
            res = run_staff_agent_loop(db, msg, case_id=target_cid, actor=f"Hermes ({user.full_name})")
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
            # Fast Chat Mode with contextual summary + automatic side-panel opening
            if ui_panel and ui_panel["panel"] == "ceo_analytics":
                total = db.query(ClientCase).count()
                approved = db.query(ClientCase).filter(ClientCase.outcome == "approved").count()
                refused = db.query(ClientCase).filter(ClientCase.outcome == "refused").count()
                reply = (
                    f"Opened your **CEO Executive Analytics & Graphs** in the side panel.\n\n"
                    f"- **Total Cases:** {total} ({approved} approved, {refused} refused)\n"
                    f"- Interactive charts for **Pipeline Distribution**, **Denial-Risk Tiers**, **Good Standing**, and **Compliant Interview Prediction Recall** are live on the right.\n\n"
                    f"Ask me to drill into any case (e.g. *\"Audit C005\"*) or manage team logins (*\"Create a staff account\"*)."
                )
            elif ui_panel and ui_panel["panel"] == "client" and target_cid:
                c = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first()
                if c:
                    red_n = sum(1 for f in c.risk_flags if f.severity == "red" and not f.resolved)
                    amber_n = sum(1 for f in c.risk_flags if f.severity == "amber" and not f.resolved)
                    reply = (
                        f"Opened **{c.case_id} — {c.full_name or c.pseudonym}** (`{c.visa_class}`) in the side panel.\n\n"
                        f"- **Good Standing Score:** `{c.standing_score}%` ({c.denial_risk_level.upper()} risk — {red_n} Red, {amber_n} Amber)\n"
                        f"- **Stage:** `{c.pipeline_stage.replace('_', ' ').title()}` | **DS-160:** `{c.ds160_confirmation_id or 'Pending'}`\n\n"
                        f"Switch to **Task** mode (or say *\"Generate visual roadmap & DS-160 worksheet for {c.case_id}\"*) and I'll draft the full packet for your approval."
                    )
                else:
                    reply = f"I couldn't find case `{target_cid}`. Opened the Client Pipeline so you can pick or create one."
                    ui_panel = {"panel": "clients_list", "title": "Client Pipeline & Cases"}
            elif ui_panel and ui_panel["panel"] == "official_pdfs":
                reply = "Opened the **Official Government PDF Viewer** in the side panel (PICA Jamaica Passport forms, U.S. Dept. of State DS-5535/DS-157/DS-156E, RGD Birth Certificate BIRREQ & blueprints). You can view inline, download, verify the official URL, or upload new blueprints."
            elif ui_panel and ui_panel["panel"] == "gov_sources":
                reply = "Opened **Official Scraped Government Sources** in the side panel with live clickable links to U.S. Embassy Kingston, travel.state.gov, AIS Jamaica, PICA, and RGD/NIRA. Click **Scrape & Verify All** anytime to detect rule changes."
            elif ui_panel and ui_panel["panel"] == "database":
                reply = "Opened the **Live Database Table Explorer** in the side panel. You can search every table (`clients`, `source_manifest`, `gov_sources`, `interview_events`, `question_taxonomy`) or batch-import client CSV spreadsheets."
            elif ui_panel and ui_panel["panel"] == "obsidian":
                reply = "Opened your **Local Obsidian Vault** in the side panel (`data/obsidian-vault/`). Edit Markdown notes, click `[[wikilinks]]`, or sync any client dossier directly."
            elif ui_panel and ui_panel["panel"] == "team":
                reply = "Opened **Team & Staff Account Management** in the side panel. As the agency CEO, you can create new Staff accounts or manage existing logins here."
            elif ui_panel and ui_panel["panel"] == "settings":
                reply = "Opened **Easy Setup, AI Subscriptions & MCP Hub** in the side panel. Connect Antigravity, Ollama, Claude, ChatGPT, Grok, Composio (Gmail/Sheets/Docs), or white-label agency branding."
            elif ui_panel and ui_panel["panel"] == "clients_list":
                reply = "Opened the **Client Pipeline** in the side panel. Click any client to inspect their Good Standing bar, or say *\"Audit C005\"* / *\"Show C034\"*."
            else:
                client = db.query(ClientCase).filter(ClientCase.case_id == target_cid).first() if target_cid else None
                res = answer_customer_question(db, msg, client)
                reply = res["reply"]
                citations = res.get("citations", [])
                provider = res["provider_used"]

    db.add(
        ChatMessage(
            session_id=sess,
            case_id=req.case_id or user.linked_case_id,
            user_role=role,
            sender="assistant",
            content=reply,
            tool_trace_json=json.dumps(tool_trace or citations),
            provider_used=provider,
        )
    )
    db.commit()

    return {
        "reply": reply,
        "provider_used": provider,
        "mode": req.mode,
        "tool_trace": tool_trace,
        "citations": citations,
        "created_assets": created_assets,
        "ui_panel": ui_panel,
    }


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
