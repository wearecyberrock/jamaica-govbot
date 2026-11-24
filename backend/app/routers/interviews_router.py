"""Interview Predictions, Pre-Interview Freeze, Mock Interview Simulator & Embassy Outcome Recording."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import ClientCase, InterviewEvent, InterviewPrediction, PipelineJournal, User
from app.services.hermes_engine import COMPLIANCE_SYSTEM_PROMPT, call_llm
from app.services.risk_engine import generate_ranked_predictions

router = APIRouter(prefix="/api", tags=["interviews"])


class MockAnswerRequest(BaseModel):
    theme: str
    question_text: str
    client_answer: str


class EmbassyOutcomeRequest(BaseModel):
    outcome: str  # approved | refused | 221g | pending
    refusal_statute: str = ""
    outcome_evidence: str = "user_reported"
    reported_questions: list[dict[str, str]] = []


@router.post("/clients/{case_id}/predictions/generate")
def regenerate_predictions(
    case_id: str,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if c.predictions_frozen:
        raise HTTPException(
            status_code=400,
            detail="Predictions are FROZEN pre-interview per Jahtaria compliance rules. Do not retroactively alter frozen predictions.",
        )
    preds = generate_ranked_predictions(db, c, author=user.full_name, replace_unfrozen=True)
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="predictions_generated",
            actor=user.full_name,
            summary=f"Generated {len(preds)} ranked profile + policy interview predictions.",
        )
    )
    db.commit()
    return {"case_id": c.case_id, "count": len(preds), "frozen": c.predictions_frozen}


@router.post("/clients/{case_id}/predictions/freeze")
def freeze_predictions(
    case_id: str,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Freeze predictions before embassy attendance with author + UTC timestamp."""
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if not c.predictions:
        generate_ranked_predictions(db, c, author=user.full_name)
    now = datetime.now(timezone.utc)
    c.predictions_frozen = True
    c.predictions_frozen_at = now
    c.predictions_frozen_by = user.full_name
    for p in c.predictions:
        if not p.frozen_at:
            p.frozen_at = now
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="predictions_frozen",
            actor=user.full_name,
            summary=f"FROZE {len(c.predictions)} pre-interview predictions at {now.isoformat()} for compliant evaluation.",
        )
    )
    db.commit()
    return {"case_id": c.case_id, "frozen": True, "frozen_at": now.isoformat(), "frozen_by": user.full_name}


@router.post("/clients/{case_id}/mock-practice")
def practice_mock_interview(
    case_id: str,
    req: MockAnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Evaluate a client's practice interview answer for truthfulness, conciseness & DS-160 consistency."""
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")
    if user.role == "customer" and user.linked_case_id != c.case_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    ans = req.client_answer.strip()
    if not ans:
        raise HTTPException(status_code=400, detail="Please enter an answer to evaluate.")

    # Deterministic discrepancy checks + optional LLM coaching
    discrepancy = ""
    coaching_points: list[str] = []
    word_count = len(ans.split())

    if word_count > 65:
        coaching_points.append("Keep consular answers concise (15–40 words). Long speeches can introduce unintended confusion in a 2-minute Kingston interview.")
    if word_count < 4:
        coaching_points.append("Provide a clear, complete factual answer (e.g., exact job title + employer, or exact travel dates + city).")

    if req.theme in ("monthly_income", "business_income") and c.monthly_gross_jmd:
        coaching_points.append(
            f"State clearly whether you are quoting your Gross monthly salary (JMD {c.monthly_gross_jmd:,.0f}, as on DS-160) "
            f"or Net take-home (JMD {c.monthly_net_jmd:,.0f} if applicable) so it matches your payslip."
            if c.monthly_net_jmd
            else f"Ensure your spoken income aligns cleanly with your DS-160 gross salary (JMD {c.monthly_gross_jmd:,.0f})."
        )
    if req.theme in ("us_relatives", "us_contact", "us_partner") and c.has_us_relatives and any(w in ans.lower() for w in ("no one", "nobody", "no relatives")):
        discrepancy = "us_relatives_contradiction"
        coaching_points.append("COMPLIANCE ALERT: Your profile indicates U.S. relatives/contacts. Always disclose U.S. relatives truthfully to match Form DS-160.")
    if req.theme == "marital_status" and "separated" in (c.marital_status or "").lower() and "single" in ans.lower():
        discrepancy = "marital_legal_status_contradiction"
        coaching_points.append("COMPLIANCE ALERT: If legally married without a final Decree Absolute, state 'Legally married, currently separated' rather than 'Single'.")

    llm_feedback, provider = call_llm(
        db,
        COMPLIANCE_SYSTEM_PROMPT,
        f"Client Profile: {c.visa_class}, Occupation={c.occupation}, Gross JMD={c.monthly_gross_jmd}, Net JMD={c.monthly_net_jmd}, "
        f"Destination={c.us_destination}, Purpose={c.purpose_of_trip}.\n"
        f"Consular Question ({req.theme}): {req.question_text}\n"
        f"Client's Practice Answer: {ans}\n\n"
        "Give 2-3 brief, warm, strictly truthful coaching notes checking clarity, conciseness, and alignment with DS-160. Never coach concealment.",
    )

    feedback = llm_feedback or (
        " ".join(coaching_points)
        if coaching_points
        else "Clear, direct, and consistent with your documented profile. Keep your tone calm, factual, and natural at the Embassy window."
    )

    ev = InterviewEvent(
        case_id=c.case_id,
        event_mode="mock_practice",
        sequence=db.query(InterviewEvent).filter(InterviewEvent.case_id == c.case_id).count() + 1,
        theme=req.theme,
        question_text=req.question_text,
        client_answer=ans,
        discrepancy_type=discrepancy,
        verified_resolution=feedback,
        source_type="mock_interview_simulator",
    )
    db.add(ev)
    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="mock_interview",
            actor=user.full_name,
            summary=f"Completed mock practice for theme '{req.theme}' ({'DISCREPANCY FLAGGED' if discrepancy else 'aligned'}).",
        )
    )
    db.commit()

    return {
        "event_id": ev.id,
        "theme": req.theme,
        "discrepancy_type": discrepancy,
        "feedback": feedback,
        "provider_used": provider,
    }


@router.post("/clients/{case_id}/embassy-outcome")
def record_embassy_outcome(
    case_id: str,
    req: EmbassyOutcomeRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found.")

    c.outcome = req.outcome
    c.refusal_statute = req.refusal_statute.strip()
    c.outcome_evidence = req.outcome_evidence.strip()
    if req.outcome in ("approved", "refused"):
        c.pipeline_stage = "completed"

    predicted_set = {p.theme_id for p in c.predictions}
    reported_themes: list[str] = []
    for idx, q in enumerate(req.reported_questions, start=1):
        theme = q.get("theme", "other").strip()
        text = q.get("question_text", "").strip()
        if not theme:
            continue
        reported_themes.append(theme)
        matched = theme in predicted_set
        db.add(
            InterviewEvent(
                case_id=c.case_id,
                event_mode="embassy_reported",
                sequence=idx,
                theme=theme,
                question_text=text,
                source_type="user_recollection",
                pre_interview_predicted_theme=matched,
                prediction_classification="theme_match" if matched else "unpredicted_theme",
                exact_wording_verified=False,
            )
        )

    if reported_themes:
        c.reported_actual_themes_json = json.dumps(reported_themes)

    db.add(
        PipelineJournal(
            case_id=c.case_id,
            event_type="embassy_outcome",
            actor=user.full_name,
            summary=f"Recorded embassy outcome '{c.outcome}' (evidence={c.outcome_evidence}, statute={c.refusal_statute or 'N/A'}, {len(reported_themes)} reported questions).",
        )
    )
    db.commit()
    return {"case_id": c.case_id, "outcome": c.outcome, "reported_questions_logged": len(reported_themes)}
