"""Quiz Builder API router: X/Y/Z/A relationship canvas, Generator, Effective Pathway, Hidden Patterns & Printable PDF."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import ClientCase, InterviewEvent, OfficialQA, PipelineJournal, RiskFlag, User
from app.services.quiz_builder_service import (
    analyze_hidden_patterns,
    build_quiz_canvas,
    ensure_official_qa_seeded,
    generate_printable_quiz_pdf,
    generate_relationship_questions,
)
from app.services.risk_engine import evaluate_client_standing

router = APIRouter(prefix="/api/quiz-builder", tags=["Quiz Builder"])


class GenerateQuizRequest(BaseModel):
    case_id: str | None = None
    count: int = 4
    focus: str = "all"


class OfficialQACreateRequest(BaseModel):
    theme_id: str = "purpose_of_trip"
    visa_class: str = "B1/B2"
    question_text: str
    answer_text: str = ""
    answer_quality: str = "strong"
    outcome_tag: str = "approved"
    difficulty: str = "medium"
    frequency_count: int = 1
    profile_tags: list[str] = []
    source_case_id: str | None = None
    notes: str = ""


class SaveQuizAnswerRequest(BaseModel):
    case_id: str
    source_type: str = "prediction"  # prediction | risk_followup
    db_id: int
    theme_id: str = "purpose_of_trip"
    question_text: str = ""
    answer_text: str


class AnalyzePatternsRequest(BaseModel):
    case_id: str | None = None


@router.get("/canvas")
def get_quiz_builder_canvas(
    case_id: str | None = Query(default=None),
    cohort: str = Query(default="all"),
    q_filter: str = Query(default="all"),
    a_filter: str = Query(default="all"),
    visa_class: str = Query(default="all"),
    effective_mode: bool = Query(default=False),
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return build_quiz_canvas(
        db=db,
        case_id=case_id,
        cohort=cohort,
        q_filter=q_filter,
        a_filter=a_filter,
        visa_class=visa_class,
        effective_mode=effective_mode,
    )


@router.post("/generate")
def generate_quiz_questions(
    req: GenerateQuizRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return generate_relationship_questions(
        db=db,
        case_id=req.case_id,
        count=max(1, min(10, req.count)),
        focus=req.focus,
        author=user.full_name,
    )


@router.post("/official-qa")
def create_official_qa(
    req: OfficialQACreateRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_official_qa_seeded(db)
    qtxt = req.question_text.strip()
    if not qtxt:
        raise HTTPException(status_code=400, detail="Official question text is required.")
    row = OfficialQA(
        theme_id=req.theme_id.strip() or "purpose_of_trip",
        visa_class=req.visa_class.strip() or "B1/B2",
        question_text=qtxt,
        answer_text=req.answer_text.strip(),
        answer_quality=req.answer_quality,
        outcome_tag=req.outcome_tag,
        difficulty=req.difficulty,
        frequency_count=max(1, req.frequency_count),
        profile_tags_json=json.dumps(req.profile_tags),
        source_case_id=req.source_case_id,
        notes=req.notes.strip(),
        added_by=user.full_name,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "z_id": f"Z-{row.id}",
        "a_id": f"A-{row.id}",
        "question_text": row.question_text,
        "answer_text": row.answer_text,
        "theme_id": row.theme_id,
    }


@router.delete("/official-qa/{qa_id}")
def delete_official_qa(
    qa_id: int,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    row = db.query(OfficialQA).filter(OfficialQA.id == qa_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Official Q&A not found.")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/save-answer")
def save_quiz_client_answer(
    req: SaveQuizAnswerRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save a client's practice/clarification answer on Lane Y (contributes small capped practice bump only)."""
    client = db.query(ClientCase).filter(ClientCase.case_id == req.case_id.upper()).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client case not found.")

    ans = req.answer_text.strip()
    if req.source_type == "risk_followup":
        flag = db.query(RiskFlag).filter(RiskFlag.id == req.db_id, RiskFlag.case_id == client.case_id).first()
        if flag:
            flag.client_response = ans
            flag.resolved = bool(ans)
            db.commit()
    else:
        db.add(
            InterviewEvent(
                case_id=client.case_id,
                event_mode="mock_practice",
                sequence=db.query(InterviewEvent).filter(InterviewEvent.case_id == client.case_id).count() + 1,
                theme=req.theme_id,
                question_text=req.question_text,
                client_answer=ans,
                verified_resolution="Recorded via Quiz Builder training session.",
                source_type="quiz_builder",
            )
        )
        db.commit()

    db.add(
        PipelineJournal(
            case_id=client.case_id,
            event_type="quiz_answer_recorded",
            actor=user.full_name,
            summary=f"Recorded Quiz Builder answer for theme '{req.theme_id}' (practice readiness only — docs/personal data remain primary risk weight).",
        )
    )
    db.commit()
    audit = evaluate_client_standing(db, client)
    return {
        "saved": True,
        "case_id": client.case_id,
        "standing_score": audit["standing_score"],
        "score_breakdown": audit.get("score_breakdown", {}),
    }


@router.post("/analyze-patterns")
def run_hidden_pattern_analysis(
    req: AnalyzePatternsRequest,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return analyze_hidden_patterns(db=db, case_id=req.case_id)


@router.get("/print-pdf")
def download_printable_quiz_pdf(
    case_id: str | None = Query(default=None),
    q_filter: str = Query(default="all"),
    include_answers: bool = Query(default=True),
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> FileResponse:
    pdf_path = generate_printable_quiz_pdf(
        db=db,
        case_id=case_id,
        q_filter=q_filter,
        include_answers=include_answers,
    )
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
    )
