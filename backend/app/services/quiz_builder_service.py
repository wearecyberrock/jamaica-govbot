"""Quiz Builder Relationship Engine, Hidden Pattern Miner & Printable Prep Sheet Generator.

Maps:
  Lane X: Generated / Predicted Questions (from client data & database)
  Lane Y: Client / Practice Answers mapped to X
  Lane Z: Official U.S. Embassy / Organization Questions entered into the database
  Lane A: Official / Outcome Answer Patterns mapped to Z
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.config import GENERATED_DIR
from app.models import (
    BrandingConfig,
    ClientCase,
    InterviewEvent,
    InterviewPrediction,
    OfficialQA,
    QuestionTaxonomy,
    RiskFlag,
)
from app.services.hermes_engine import COMPLIANCE_SYSTEM_PROMPT, call_llm_detailed

SEEDED_OFFICIAL_QA: list[dict[str, Any]] = [
    {
        "theme_id": "purpose_of_trip",
        "visa_class": "B1/B2",
        "question_text": "What is the exact purpose of your trip to the United States, and how long will you stay?",
        "answer_text": "Strong pattern (Approved): State a single concrete event or visit (e.g., 5-day hospitality conference in Miami + 2 days visiting family), exact city, and clear return date matching employer leave letter.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "easy",
        "frequency_count": 29,
        "profile_tags": ["first_time", "employed", "b1b2", "tourism"],
        "notes": "Almost every Kingston B1/B2 interview opens here. Vague 'just vacation / shopping' answers without dates or budget trigger follow-up probing.",
    },
    {
        "theme_id": "employment",
        "visa_class": "B1/B2",
        "question_text": "Where do you work in Jamaica, what is your exact role, and how long have you been there?",
        "answer_text": "Strong pattern (Approved): Name employer, job title, concrete daily responsibilities, and exact tenure matching DS-160 & job letter.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "medium",
        "frequency_count": 26,
        "profile_tags": ["employed", "first_time", "home_ties"],
        "notes": "Strongest 214(b) home-tie anchor for employed applicants. Short tenure (<6 months) often leads to funding & return-incentive follow-ups.",
    },
    {
        "theme_id": "monthly_income",
        "visa_class": "B1/B2",
        "question_text": "How much do you earn per month in JMD, and does that match what you wrote on your DS-160?",
        "answer_text": "Strong pattern (Approved): Quote exact monthly Gross JMD as entered on DS-160 and clarify Net take-home only if asked, backed by 3 recent payslips.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "hard",
        "frequency_count": 19,
        "profile_tags": ["employed", "self_employed", "income_check"],
        "notes": "Common trap: quoting net take-home when DS-160 lists gross without clarifying. Always state 'gross before deductions' clearly.",
    },
    {
        "theme_id": "funding_trip",
        "visa_class": "B1/B2",
        "question_text": "Who is paying for your flight, hotel, and expenses in the U.S.?",
        "answer_text": "Strong pattern (Approved): Self-funded from verified salary/savings with realistic budget, OR clearly documented sponsor (employer conference letter / parent with financial proof).",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "hard",
        "frequency_count": 17,
        "profile_tags": ["first_time", "student", "sponsor", "self_employed"],
        "notes": "Weak pattern (Refused 214b): Claiming a casual U.S. friend/boyfriend is paying everything while applicant has no steady Jamaican income.",
    },
    {
        "theme_id": "us_relatives",
        "visa_class": "B1/B2",
        "question_text": "Do you have any immediate relatives, a partner, or close family living in the United States?",
        "answer_text": "Strong pattern (Approved): Disclose truthfully every immediate relative listed on DS-160 (status, city, occupation) while clearly explaining your own independent life & return ties in Jamaica.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "hard",
        "frequency_count": 16,
        "profile_tags": ["us_relatives", "family_visit", "prior_refusal"],
        "notes": "Weak pattern (Refused / Credibility): Hiding a U.S.-based parent, child, sibling, or partner that conflicts with DS-160 or prior records.",
    },
    {
        "theme_id": "prior_refusal",
        "visa_class": "B1/B2",
        "question_text": "You were refused a U.S. visa previously — what specifically has changed in your life in Jamaica since then?",
        "answer_text": "Strong pattern (Approved): Calmly cite concrete, verifiable changes (longer employment tenure, promotion/higher verified income, completed degree, property/family obligations, or international travel returned on time).",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "hard",
        "frequency_count": 14,
        "profile_tags": ["prior_refusal", "reapplication"],
        "notes": "High-difficulty question. Reapplying quickly with zero material change in ties is the #1 repeat 214(b) pattern.",
    },
    {
        "theme_id": "business_income",
        "visa_class": "B1/B2",
        "question_text": "How is your Jamaican business registered, how long has it operated, and who runs it while you are away?",
        "answer_text": "Strong pattern (Approved): Name registered entity (COJ/TRN), years operating, verifiable monthly revenue/bank statements, and named manager/staff keeping operations running.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "hard",
        "frequency_count": 11,
        "profile_tags": ["self_employed", "business_owner"],
        "notes": "Weak pattern (Refused 214b): Informal cash-only side hustle with no business bank trail or clear coverage during travel.",
    },
    {
        "theme_id": "travel_history",
        "visa_class": "B1/B2",
        "question_text": "Have you travelled outside Jamaica before? Where did you go and how long did you stay?",
        "answer_text": "Strong pattern (Approved): Concisely list prior countries (e.g., UK, Canada, Barbados, Cayman, Panama), year, brief purpose, and on-time return.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "easy",
        "frequency_count": 15,
        "profile_tags": ["international_travel", "first_time"],
        "notes": "Demonstrated compliance with other countries' visas/entry limits strongly reinforces credibility.",
    },
    {
        "theme_id": "study_plan",
        "visa_class": "F-1",
        "question_text": "Why did you choose this specific U.S. university and program, and what will you do in Jamaica after graduation?",
        "answer_text": "Strong pattern (Approved): Connect exact curriculum to a specific career path in Jamaica/Caribbean, cite I-20 funding clearly, and explain why this program fits your academic background.",
        "answer_quality": "strong",
        "outcome_tag": "approved",
        "difficulty": "hard",
        "frequency_count": 10,
        "profile_tags": ["student", "f1"],
        "notes": "F-1 interviews heavily probe academic credibility, sponsor liquidity, and post-graduation return plans.",
    },
    {
        "theme_id": "home_country_safety",
        "visa_class": "B1/B2",
        "question_text": "Standard policy question: Are you comfortable returning to Jamaica after your visit, or do you have any safety concerns?",
        "answer_text": "Policy note: Answer truthfully and calmly. This is a universal mandatory consular screening item separated from profile-driven risk predictions.",
        "answer_quality": "strong",
        "outcome_tag": "policy",
        "difficulty": "medium",
        "frequency_count": 12,
        "profile_tags": ["policy_mandatory"],
        "notes": "Universal mandatory check — keep separated from individual denial predictions per Jahtaria compliance rules.",
    },
    {
        "theme_id": "purpose_of_trip",
        "visa_class": "B1/B2",
        "question_text": "Why do you want to stay in the U.S. for 3 months if you have a full-time job in Kingston?",
        "answer_text": "Weak pattern (Refused 214b): Answering 'my boss doesn't mind' or staying 2–3 months with no approved leave letter undermines claims of strong job ties.",
        "answer_quality": "weak",
        "outcome_tag": "refused",
        "difficulty": "hard",
        "frequency_count": 9,
        "profile_tags": ["long_stay", "employed", "214b_risk"],
        "notes": "Always align intended trip duration realistically with approved vacation leave (typically 5–14 days for employed applicants).",
    },
]


def _load_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _norm_outcome(outcome: str | None, outcome_evidence: str | None = None) -> str:
    txt = f"{outcome or ''} {outcome_evidence or ''}".lower()
    if any(k in txt for k in ("approv", "issued", "granted", "pass")):
        return "approved"
    if any(k in txt for k in ("refus", "214", "denied", "reject")):
        return "refused"
    if any(k in txt for k in ("221", "admin", "5535")):
        return "admin_processing"
    return "in_preparation"


def _client_outcome(c: ClientCase | None) -> str:
    if not c:
        return "in_preparation"
    return _norm_outcome(getattr(c, "outcome", None), getattr(c, "outcome_evidence", None))


def _theme_difficulty(theme_id: str, refusal_rate: float = 0.0) -> str:
    hard_themes = {
        "prior_refusal",
        "monthly_income",
        "business_income",
        "us_relatives",
        "us_partner",
        "funding_trip",
        "study_plan",
        "overstay_risk",
        "marital_status",
    }
    easy_themes = {"purpose_of_trip", "destination", "travel_history", "children"}
    if theme_id in hard_themes or refusal_rate >= 0.45:
        return "hard"
    if theme_id in easy_themes and refusal_rate < 0.25:
        return "easy"
    return "medium"


def _evaluate_answer_strength(answer_text: str) -> str:
    ans = (answer_text or "").strip()
    if not ans:
        return "unanswered"
    words = ans.split()
    lower = ans.lower()
    vague_markers = ("idk", "not sure", "maybe", "don't know", "whatever", "just going", "n/a", "none yet", "later")
    if len(words) < 4 or any(m in lower for m in vague_markers):
        return "weak"
    if len(words) > 75:
        return "weak"
    return "strong"


def ensure_official_qa_seeded(db: Session) -> None:
    """Seed OfficialQA from curated Kingston Embassy Q&As + real InterviewEvent records (idempotent)."""
    if db.query(OfficialQA).count() > 0:
        return

    for item in SEEDED_OFFICIAL_QA:
        db.add(
            OfficialQA(
                theme_id=item["theme_id"],
                visa_class=item["visa_class"],
                question_text=item["question_text"],
                answer_text=item["answer_text"],
                answer_quality=item["answer_quality"],
                outcome_tag=item["outcome_tag"],
                difficulty=item["difficulty"],
                frequency_count=item["frequency_count"],
                profile_tags_json=json.dumps(item["profile_tags"]),
                notes=item["notes"],
                added_by="Kingston Embassy Dataset",
            )
        )

    # Also promote unique real reported InterviewEvent questions from the 33 seeded cases
    case_map = {c.case_id: c for c in db.query(ClientCase).all()}
    events = (
        db.query(InterviewEvent)
        .filter(InterviewEvent.event_mode == "embassy_reported")
        .order_by(InterviewEvent.id.asc())
        .all()
    )
    seen_q: set[str] = {q["question_text"].strip().lower() for q in SEEDED_OFFICIAL_QA}
    theme_counts = Counter(e.theme for e in events)
    for ev in events:
        qtxt = (ev.question_text or "").strip()
        if not qtxt or qtxt.lower() in seen_q:
            continue
        seen_q.add(qtxt.lower())
        cl = case_map.get(ev.case_id)
        outcome = _client_outcome(cl)
        if outcome == "in_preparation":
            outcome = "approved"
        ans_hint = (
            f"Reported in {ev.case_id} ({cl.visa_class if cl else 'B1/B2'} · {outcome.upper()}): "
            f"{'Clear, specific answer aligned with DS-160 and supporting Jamaican documents.' if outcome == 'approved' else 'Probed under 214(b) — requires stronger documented ties and exact DS-160 alignment.'}"
        )
        db.add(
            OfficialQA(
                theme_id=ev.theme or "purpose_of_trip",
                visa_class=(cl.visa_class if cl else "B1/B2"),
                question_text=qtxt,
                answer_text=ans_hint,
                answer_quality="strong" if outcome == "approved" else "weak",
                outcome_tag=outcome,
                difficulty=_theme_difficulty(ev.theme or ""),
                frequency_count=max(2, theme_counts.get(ev.theme, 1) * 2),
                profile_tags_json=(cl.profile_tags_json if cl else "[]"),
                source_case_id=ev.case_id,
                notes=f"Imported from real reported Kingston interview event (Case {ev.case_id}, seq #{ev.sequence}).",
                added_by="Historical Interview Archive",
            )
        )
    db.commit()


def _client_matches_cohort(c: ClientCase, cohort: str) -> bool:
    if not cohort or cohort == "all":
        return True
    tags = set(t.lower() for t in _load_json_list(c.profile_tags_json))
    vc = (c.visa_class or "").upper()
    if cohort == "employed_b1b2":
        return "B1" in vc and ("employed" in tags or bool((c.employer_name or "").strip()))
    if cohort == "first_time":
        return "first_time" in tags or (c.prior_us_refusals or 0) == 0
    if cohort == "prior_refusal":
        return (c.prior_us_refusals or 0) > 0 or "prior_refusal" in tags
    if cohort == "self_employed":
        return "self_employed" in tags or "business" in (c.occupation or "").lower() or "owner" in (c.occupation or "").lower()
    if cohort == "us_relatives":
        return bool(c.has_us_relatives) or "us_relatives" in tags
    if cohort == "student_f1":
        return "F-1" in vc or "student" in tags
    return True


def compute_cohort_approval_stats(db: Session) -> list[dict[str, Any]]:
    """Compute transparent approval patterns across client types with explicit sample sizes (n)."""
    clients = db.query(ClientCase).all()
    events = db.query(InterviewEvent).filter(InterviewEvent.event_mode == "embassy_reported").all()
    events_by_case: dict[str, list[InterviewEvent]] = defaultdict(list)
    for e in events:
        events_by_case[e.case_id].append(e)

    cohorts = [
        ("employed_b1b2", "Employed Professionals (B1/B2)", "Steady Jamaican employer + verifiable gross JMD payslips"),
        ("first_time", "First-Time Applicants (No Prior Refusal)", "Clean U.S. history; focus on clear trip purpose & ties"),
        ("us_relatives", "Applicants With U.S. Relatives", "Must disclose truthfully & prove independent return ties"),
        ("self_employed", "Self-Employed / Business Owners", "Needs COJ/TRN registration, business bank trail & coverage"),
        ("prior_refusal", "Prior Refusal / Re-Applicants", "Must show concrete, verifiable life changes since refusal"),
        ("student_f1", "Students (F-1 / Academic)", "Needs clear curriculum fit, I-20 funding & return career plan"),
    ]

    results: list[dict[str, Any]] = []
    for key, label, summary in cohorts:
        matched = [c for c in clients if _client_matches_cohort(c, key)]
        approved = sum(1 for c in matched if _client_outcome(c) == "approved")
        refused = sum(1 for c in matched if _client_outcome(c) == "refused")
        decided = approved + refused
        avg_standing = round(sum(c.standing_score for c in matched) / len(matched), 1) if matched else 0.0
        theme_counter = Counter()
        for c in matched:
            for e in events_by_case.get(c.case_id, []):
                theme_counter[e.theme] += 1
            for t in _load_json_list(c.predicted_themes_json):
                theme_counter[t] += 1

        approval_rate = round((approved / decided) * 100, 1) if decided > 0 else None
        results.append(
            {
                "cohort_id": key,
                "label": label,
                "summary": summary,
                "total_clients": len(matched),
                "decided_cases": decided,
                "approved_count": approved,
                "refused_count": refused,
                "approval_rate_pct": approval_rate,
                "avg_standing_score": avg_standing,
                "top_themes": [t for t, _ in theme_counter.most_common(4)],
                "sample_label": f"n={decided} decided ({len(matched)} total)" if decided else f"n={len(matched)} in prep",
            }
        )

    # Include live agency custom cohorts built by Hermes
    from app.services.extensions_service import client_matches_custom_cohort, get_custom_cohorts

    for cc in get_custom_cohorts(db):
        matched = [c for c in clients if client_matches_custom_cohort(c, cc["config"])]
        approved = sum(1 for c in matched if _client_outcome(c) == "approved")
        refused = sum(1 for c in matched if _client_outcome(c) == "refused")
        decided = approved + refused
        avg_standing = round(sum(c.standing_score for c in matched) / len(matched), 1) if matched else 0.0
        results.append(
            {
                "cohort_id": cc["cohort_id"],
                "label": cc["label"],
                "summary": cc["summary"],
                "total_clients": len(matched),
                "decided_cases": decided,
                "approved_count": approved,
                "refused_count": refused,
                "approval_rate_pct": round((approved / decided) * 100, 1) if decided > 0 else None,
                "avg_standing_score": avg_standing,
                "top_themes": [],
                "sample_label": f"n={decided} decided ({len(matched)} total)" if decided else f"n={len(matched)} in prep",
            }
        )

    results.sort(key=lambda r: (r["approval_rate_pct"] is not None, r["approval_rate_pct"] or 0, r["total_clients"]), reverse=True)
    return results


def build_quiz_canvas(
    db: Session,
    case_id: str | None = None,
    cohort: str = "all",
    q_filter: str = "all",
    a_filter: str = "all",
    visa_class: str = "all",
    effective_mode: bool = False,
) -> dict[str, Any]:
    """Assemble the 4-lane (X, Y, Z, A) interactive relationship diagram & Effective pathway."""
    ensure_official_qa_seeded(db)

    all_clients = db.query(ClientCase).order_by(ClientCase.id.desc()).all()
    client_map = {c.case_id: c for c in all_clients}
    selected_client = client_map.get(case_id.upper()) if case_id and case_id.upper() != "ALL" else None

    if selected_client:
        scope_clients = [selected_client]
    else:
        scope_clients = [
            c
            for c in all_clients
            if _client_matches_cohort(c, cohort)
            and (visa_class == "all" or visa_class.upper() in (c.visa_class or "").upper())
        ]
    scope_ids = {c.case_id for c in scope_clients}

    # Global theme frequency & refusal correlation across ALL official events
    all_events = db.query(InterviewEvent).all()
    embassy_events = [e for e in all_events if e.event_mode == "embassy_reported"]
    theme_freq = Counter(e.theme for e in embassy_events)
    theme_refusals = Counter()
    theme_decided = Counter()
    for e in embassy_events:
        cl = client_map.get(e.case_id)
        out = _client_outcome(cl)
        if out in ("approved", "refused"):
            theme_decided[e.theme] += 1
            if out == "refused":
                theme_refusals[e.theme] += 1

    # Gather Official Q&A (Lanes Z & A)
    official_rows = db.query(OfficialQA).order_by(OfficialQA.frequency_count.desc(), OfficialQA.id.asc()).all()
    if visa_class != "all":
        official_rows = [r for r in official_rows if visa_class.upper() in (r.visa_class or "B1/B2").upper() or r.outcome_tag == "policy"]

    # Gather Generated Questions (Lane X) & Client Answers (Lane Y)
    pred_query = db.query(InterviewPrediction)
    flag_query = db.query(RiskFlag)
    practice_query = db.query(InterviewEvent).filter(InterviewEvent.event_mode == "mock_practice")

    if selected_client:
        pred_query = pred_query.filter(InterviewPrediction.case_id == selected_client.case_id)
        flag_query = flag_query.filter(RiskFlag.case_id == selected_client.case_id)
        practice_query = practice_query.filter(InterviewEvent.case_id == selected_client.case_id)

    predictions = pred_query.order_by(InterviewPrediction.rank.asc(), InterviewPrediction.id.desc()).all()
    flags = flag_query.order_by(RiskFlag.id.desc()).all()
    practice_rows = practice_query.order_by(InterviewEvent.id.desc()).all()

    practice_by_case_theme: dict[tuple[str, str], InterviewEvent] = {}
    for pr in practice_rows:
        key = (pr.case_id, pr.theme)
        if key not in practice_by_case_theme:
            practice_by_case_theme[key] = pr

    lane_x: list[dict[str, Any]] = []
    lane_y: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_x_keys: set[tuple[str, str]] = set()

    # Populate X from InterviewPredictions
    for p in predictions:
        if p.case_id not in scope_ids:
            continue
        cl = client_map.get(p.case_id)
        dedupe_key = (p.case_id if selected_client else "ALL", p.question_text.strip().lower()[:90])
        if dedupe_key in seen_x_keys:
            continue
        seen_x_keys.add(dedupe_key)

        theme = p.theme_id or "purpose_of_trip"
        ref_rate = (theme_refusals[theme] / theme_decided[theme]) if theme_decided[theme] else 0.2
        freq = max(1, theme_freq.get(theme, 1) + (5 if p.confidence >= 0.8 else 2))
        diff = _theme_difficulty(theme, ref_rate)

        pr = practice_by_case_theme.get((p.case_id, theme))
        ans_text = pr.client_answer if pr else ""
        strength = _evaluate_answer_strength(ans_text)
        x_id = f"X-P-{p.id}"
        y_id = f"Y-P-{p.id}"

        lane_x.append(
            {
                "id": x_id,
                "db_id": p.id,
                "source_type": "prediction",
                "case_id": p.case_id,
                "client_name": (cl.full_name or cl.pseudonym) if cl else p.case_id,
                "visa_class": cl.visa_class if cl else "B1/B2",
                "theme_id": theme,
                "question_text": p.question_text,
                "rationale": p.rationale,
                "confidence": round(float(p.confidence or 0.75), 2),
                "difficulty": diff,
                "frequency": freq,
                "is_weak": strength in ("weak", "unanswered"),
                "answer_strength": strength,
            }
        )
        lane_y.append(
            {
                "id": y_id,
                "x_id": x_id,
                "case_id": p.case_id,
                "theme_id": theme,
                "answer_text": ans_text or "No practice answer recorded yet — click to record client's answer.",
                "has_answer": bool(ans_text.strip()),
                "strength": strength,
                "feedback": pr.verified_resolution if pr else "",
                "usage_count": 1 if ans_text.strip() else 0,
            }
        )
        edges.append({"from": x_id, "to": y_id, "kind": "x_to_y", "theme_id": theme, "strength": strength})
        if len(lane_x) >= (24 if selected_client else 18):
            break

    # Populate X from RiskFlag follow-up questions (dynamic & compliance follow-ups!)
    for fl in flags:
        if fl.case_id not in scope_ids or not (fl.follow_up_question or "").strip():
            continue
        cl = client_map.get(fl.case_id)
        dedupe_key = (fl.case_id if selected_client else "ALL", fl.follow_up_question.strip().lower()[:90])
        if dedupe_key in seen_x_keys:
            continue
        seen_x_keys.add(dedupe_key)

        theme = _map_category_to_theme(fl.category, fl.code)
        ans_text = (fl.client_response or "").strip()
        strength = _evaluate_answer_strength(ans_text)
        diff = "hard" if fl.severity == "red" else ("medium" if fl.severity == "amber" else "easy")
        x_id = f"X-F-{fl.id}"
        y_id = f"Y-F-{fl.id}"

        lane_x.append(
            {
                "id": x_id,
                "db_id": fl.id,
                "source_type": "risk_followup",
                "case_id": fl.case_id,
                "client_name": (cl.full_name or cl.pseudonym) if cl else fl.case_id,
                "visa_class": cl.visa_class if cl else "B1/B2",
                "theme_id": theme,
                "question_text": fl.follow_up_question,
                "rationale": f"{fl.title}: {fl.detail[:140]}",
                "confidence": 0.92 if fl.severity == "red" else 0.78,
                "difficulty": diff,
                "frequency": max(3, theme_freq.get(theme, 2) + (4 if fl.severity == "red" else 1)),
                "is_weak": strength in ("weak", "unanswered") or fl.severity == "red",
                "answer_strength": strength,
            }
        )
        lane_y.append(
            {
                "id": y_id,
                "x_id": x_id,
                "case_id": fl.case_id,
                "theme_id": theme,
                "answer_text": ans_text or "Awaiting client clarification — answering gives +1 readiness (fix document/data to clear risk).",
                "has_answer": bool(ans_text),
                "strength": strength,
                "feedback": fl.suggested_fix,
                "usage_count": 1 if ans_text else 0,
            }
        )
        edges.append({"from": x_id, "to": y_id, "kind": "x_to_y", "theme_id": theme, "strength": strength})
        if len(lane_x) >= (34 if selected_client else 26):
            break

    # Build Lanes Z & A from OfficialQA
    lane_z: list[dict[str, Any]] = []
    lane_a: list[dict[str, Any]] = []
    for qa in official_rows[:24]:
        z_id = f"Z-{qa.id}"
        a_id = f"A-{qa.id}"
        lane_z.append(
            {
                "id": z_id,
                "db_id": qa.id,
                "theme_id": qa.theme_id,
                "visa_class": qa.visa_class,
                "question_text": qa.question_text,
                "difficulty": qa.difficulty,
                "frequency": qa.frequency_count,
                "outcome_tag": qa.outcome_tag,
                "profile_tags": _load_json_list(qa.profile_tags_json),
                "source_case_id": qa.source_case_id,
                "added_by": qa.added_by,
            }
        )
        lane_a.append(
            {
                "id": a_id,
                "z_id": z_id,
                "db_id": qa.id,
                "theme_id": qa.theme_id,
                "answer_text": qa.answer_text or "Verify truthful facts directly against Form DS-160 and supporting documents.",
                "answer_quality": qa.answer_quality,
                "outcome_tag": qa.outcome_tag,
                "usage_count": qa.frequency_count,
                "notes": qa.notes,
            }
        )
        edges.append({"from": z_id, "to": a_id, "kind": "z_to_a", "theme_id": qa.theme_id, "outcome_tag": qa.outcome_tag})

    # Apply Question Filters (most_common, hardest, weak, most_used)
    def _filter_q_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if q_filter == "most_common":
            return sorted(items, key=lambda x: x.get("frequency", 0), reverse=True)[:12]
        if q_filter == "hardest":
            hard = [x for x in items if x.get("difficulty") == "hard"]
            return (hard or sorted(items, key=lambda x: x.get("frequency", 0), reverse=True))[:12]
        if q_filter == "weak":
            weak = [x for x in items if x.get("is_weak") or x.get("outcome_tag") == "refused"]
            return (weak or items)[:12]
        if q_filter == "most_used":
            return sorted(items, key=lambda x: (x.get("frequency", 0) * (1.2 if x.get("difficulty") == "hard" else 1.0)), reverse=True)[:12]
        return items[:16]

    lane_x = _filter_q_list(lane_x)
    lane_z = _filter_q_list(lane_z)

    # Filter Y to match visible X + apply Answer Filter
    x_ids = {x["id"] for x in lane_x}
    lane_y = [y for y in lane_y if y["x_id"] in x_ids]
    if a_filter == "weak":
        lane_y = [y for y in lane_y if y["strength"] in ("weak", "unanswered")] or lane_y
    elif a_filter == "approved":
        lane_y = [y for y in lane_y if y["strength"] == "strong"] or lane_y

    # Filter A to match visible Z + apply Answer Filter
    z_ids = {z["id"] for z in lane_z}
    lane_a = [a for a in lane_a if a["z_id"] in z_ids]
    if a_filter == "most_common":
        lane_a = sorted(lane_a, key=lambda a: a.get("usage_count", 0), reverse=True)
    elif a_filter == "approved":
        lane_a = [a for a in lane_a if a["outcome_tag"] == "approved" or a["answer_quality"] == "strong"] or lane_a
    elif a_filter == "weak":
        lane_a = [a for a in lane_a if a["outcome_tag"] == "refused" or a["answer_quality"] == "weak"] or lane_a

    # Build Cross-Lane Relationship Edges: X ↔ Z (matched by theme_id or shared keywords!)
    z_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for z in lane_z:
        z_by_theme[z["theme_id"]].append(z)

    for x in lane_x:
        matched_zs = z_by_theme.get(x["theme_id"], [])
        if not matched_zs:
            # Fuzzy keyword fallback
            x_words = {w for w in x["question_text"].lower().split() if len(w) > 4}
            for z in lane_z:
                z_words = {w for w in z["question_text"].lower().split() if len(w) > 4}
                if len(x_words & z_words) >= 2:
                    matched_zs.append(z)
                    break
        for z in matched_zs[:2]:
            edges.append(
                {
                    "from": x["id"],
                    "to": z["id"],
                    "kind": "x_to_z",
                    "theme_id": x["theme_id"],
                    "weight": round(min(1.0, (x["confidence"] + (z["frequency"] / 30.0)) / 2.0), 2),
                }
            )

    # Prune edges whose endpoints were filtered out
    valid_nodes = {n["id"] for n in lane_x + lane_y + lane_z + lane_a}
    edges = [e for e in edges if e["from"] in valid_nodes and e["to"] in valid_nodes]

    # Effective Pathway & Cohort Approval Analysis
    cohort_stats = compute_cohort_approval_stats(db)
    pathway_steps: list[dict[str, Any]] = []
    pathway_node_ids: list[str] = []

    if effective_mode or selected_client:
        top_x = lane_x[:4]
        y_map = {y["x_id"]: y for y in lane_y}
        a_map = {a["z_id"]: a for a in lane_a}
        for x in top_x:
            y = y_map.get(x["id"])
            matched_z_id = next((e["to"] for e in edges if e["kind"] == "x_to_z" and e["from"] == x["id"]), None)
            z = next((item for item in lane_z if item["id"] == matched_z_id), None)
            a = a_map.get(z["id"]) if z else None
            pathway_node_ids.extend([nid for nid in (x["id"], y["id"] if y else None, z["id"] if z else None, a["id"] if a else None) if nid])
            pathway_steps.append(
                {
                    "theme_id": x["theme_id"],
                    "x_question": x["question_text"],
                    "y_answer": y["answer_text"] if y else "Not practiced yet",
                    "y_strength": y["strength"] if y else "unanswered",
                    "z_official_question": z["question_text"] if z else "No exact official match yet",
                    "a_winning_pattern": a["answer_text"] if a else "Align truthfully with DS-160 & supporting docs.",
                    "outcome_tag": a["outcome_tag"] if a else "approved",
                }
            )

    return {
        "scope": {
            "case_id": selected_client.case_id if selected_client else "ALL",
            "client_name": (selected_client.full_name or selected_client.pseudonym) if selected_client else f"All Matching Clients ({len(scope_clients)})",
            "standing_score": selected_client.standing_score if selected_client else None,
            "denial_risk_level": selected_client.denial_risk_level if selected_client else None,
            "cohort": cohort,
            "q_filter": q_filter,
            "a_filter": a_filter,
            "visa_class": visa_class,
        },
        "lane_x": lane_x,
        "lane_y": lane_y,
        "lane_z": lane_z,
        "lane_a": lane_a,
        "edges": edges,
        "effective": {
            "enabled": effective_mode,
            "pathway_node_ids": list(dict.fromkeys(pathway_node_ids)),
            "pathway_steps": pathway_steps,
            "cohort_stats": cohort_stats,
            "top_approving_profile": cohort_stats[0] if cohort_stats else None,
        },
        "clients_picker": [
            {
                "case_id": c.case_id,
                "full_name": c.full_name or c.pseudonym or c.case_id,
                "visa_class": c.visa_class,
                "standing_score": c.standing_score,
                "outcome": _client_outcome(c),
            }
            for c in all_clients
        ],
    }


def _map_category_to_theme(category: str | None, code: str | None) -> str:
    cat = f"{category or ''} {code or ''}".lower()
    if "income" in cat or "salary" in cat or "jmd" in cat:
        return "monthly_income"
    if "relative" in cat or "partner" in cat:
        return "us_relatives"
    if "refusal" in cat or "214" in cat:
        return "prior_refusal"
    if "business" in cat or "self" in cat:
        return "business_income"
    if "passport" in cat or "ds160" in cat or "barcode" in cat or "vault" in cat:
        return "purpose_of_trip"
    if "employ" in cat or "job" in cat:
        return "employment"
    return "purpose_of_trip"


def generate_relationship_questions(
    db: Session,
    case_id: str | None = None,
    count: int = 4,
    focus: str = "all",
    author: str = "Quiz Builder AI",
) -> dict[str, Any]:
    """Generate brand-new targeted interview questions based on client data + X↔Z relationships."""
    ensure_official_qa_seeded(db)
    target_client = (
        db.query(ClientCase).filter(ClientCase.case_id == case_id.upper()).first()
        if case_id and case_id.upper() != "ALL"
        else db.query(ClientCase).order_by(ClientCase.id.desc()).first()
    )
    if not target_client:
        return {"generated": [], "provider": "none", "case_id": None}

    existing_qs = {
        p.question_text.strip().lower()
        for p in db.query(InterviewPrediction).filter(InterviewPrediction.case_id == target_client.case_id).all()
    }
    official_z = db.query(OfficialQA).order_by(OfficialQA.frequency_count.desc()).limit(12).all()
    flags = db.query(RiskFlag).filter(RiskFlag.case_id == target_client.case_id).all()

    # Try connected AI LLM first for tailored dynamic questions
    generated_specs: list[dict[str, str]] = []
    provider_used = "relationship-rules"

    llm_prompt = (
        f"Generate {count} brand-new, realistic U.S. Embassy Kingston interview questions tailored to this client and our official question database.\n"
        f"Client: {target_client.full_name or target_client.pseudonym} ({target_client.visa_class}), "
        f"Occupation: {target_client.occupation or 'Unknown'}, Employer: {target_client.employer_name or 'Unknown'}, "
        f"Gross JMD: {target_client.monthly_gross_jmd or 'Unverified'}, Purpose: {target_client.purpose_of_trip or 'Unspecified'}, "
        f"Destination: {target_client.us_destination or 'Unspecified'}, Prior Refusals: {target_client.prior_us_refusals}, "
        f"U.S. Relatives: {'Yes - ' + (target_client.us_relatives_details or '') if target_client.has_us_relatives else 'No'}.\n"
        f"Focus filter: {focus}.\n"
        f"Active risk flags: {', '.join(f.title for f in flags if f.severity in ('red', 'amber')) or 'None'}.\n"
        f"Avoid repeating existing questions: {list(existing_qs)[:8]}.\n"
        "Return ONLY valid JSON array of objects: [{\"theme_id\": \"purpose_of_trip|employment|monthly_income|funding_trip|us_relatives|prior_refusal|business_income|travel_history|study_plan\", \"question_text\": \"...\", \"rationale\": \"...\"}]."
    )
    llm_res = call_llm_detailed(db, COMPLIANCE_SYSTEM_PROMPT, llm_prompt)
    if llm_res.get("text"):
        raw_txt = llm_res["text"].strip()
        start = raw_txt.find("[")
        end = raw_txt.rfind("]")
        if start != -1 and end != -1:
            try:
                parsed = json.loads(raw_txt[start : end + 1])
                if isinstance(parsed, list):
                    for item in parsed[:count]:
                        if isinstance(item, dict) and item.get("question_text"):
                            generated_specs.append(
                                {
                                    "theme_id": str(item.get("theme_id") or "purpose_of_trip"),
                                    "question_text": str(item["question_text"]).strip(),
                                    "rationale": str(item.get("rationale") or "Generated from client profile + Kingston Embassy relationships."),
                                }
                            )
                    if generated_specs:
                        provider_used = llm_res.get("provider", "ai")
            except Exception:
                pass

    # Deterministic relationship-aware generator (always fills remaining slots cleanly offline!)
    if len(generated_specs) < count:
        emp = target_client.employer_name or "your current employer"
        occ = target_client.occupation or "your role"
        dest = target_client.us_destination or "the United States"
        gross = f"JMD {target_client.monthly_gross_jmd:,.0f}" if target_client.monthly_gross_jmd else "your monthly income"
        pool = [
            {
                "theme_id": "employment",
                "question_text": f"Walk me through your actual daily duties as {occ} at {emp}, and who covers for you while you travel to {dest}?",
                "rationale": "Maps to high-frequency Kingston employment & home-ties official questions (Z).",
            },
            {
                "theme_id": "funding_trip",
                "question_text": f"Based on {gross} per month, what is your exact trip budget for flights, hotel, and daily expenses in {dest}?",
                "rationale": "Tests consistency between DS-160 gross salary, bank statements, and realistic travel costs.",
            },
            {
                "theme_id": "purpose_of_trip",
                "question_text": f"Why are you travelling to {dest} on these exact dates, and what specific commitment brings you straight back to Jamaica?",
                "rationale": "Directly mirrors top Kingston opening & return-incentive questions.",
            },
            {
                "theme_id": "us_relatives",
                "question_text": "If you have family or contacts in the U.S., what is their legal status and why are you not planning to stay with them long-term?",
                "rationale": "High-difficulty 214(b) follow-up triggered when U.S. contacts or relatives appear on DS-160.",
            },
            {
                "theme_id": "prior_refusal",
                "question_text": "If an officer asks what materially strengthens your ties to Jamaica today compared to a year ago, what two verifiable proofs will you state?",
                "rationale": "Builds concise, factual readiness for difficult re-application or low-tenure probing.",
            },
            {
                "theme_id": "monthly_income",
                "question_text": f"On your DS-160 you listed {gross} — is that gross before NIS/NHT/PAYE deductions, and do your last 3 payslips match?",
                "rationale": "Prevents the #1 Kingston gross-vs-net salary contradiction.",
            },
        ]
        # Also pull unmatched official Z questions into tailored X prompts
        for oz in official_z:
            if oz.question_text.strip().lower() not in existing_qs:
                pool.append(
                    {
                        "theme_id": oz.theme_id,
                        "question_text": oz.question_text,
                        "rationale": f"Directly mapped from official Embassy question ({oz.frequency_count}× frequency, {oz.difficulty} difficulty).",
                    }
                )
        for cand in pool:
            if len(generated_specs) >= count:
                break
            if cand["question_text"].strip().lower() not in existing_qs:
                existing_qs.add(cand["question_text"].strip().lower())
                generated_specs.append(cand)

    max_rank = (
        db.query(InterviewPrediction)
        .filter(InterviewPrediction.case_id == target_client.case_id)
        .count()
    )
    created: list[dict[str, Any]] = []
    for idx, spec in enumerate(generated_specs, start=1):
        row = InterviewPrediction(
            case_id=target_client.case_id,
            theme_id=spec["theme_id"],
            question_type="profile_driven",
            rank=max_rank + idx,
            confidence=0.86,
            question_text=spec["question_text"],
            rationale=spec["rationale"],
            author=author,
        )
        db.add(row)
        db.flush()
        created.append(
            {
                "id": f"X-P-{row.id}",
                "db_id": row.id,
                "case_id": target_client.case_id,
                "theme_id": row.theme_id,
                "question_text": row.question_text,
                "rationale": row.rationale,
            }
        )
    db.commit()
    return {"case_id": target_client.case_id, "provider": provider_used, "generated": created}


def analyze_hidden_patterns(db: Session, case_id: str | None = None) -> dict[str, Any]:
    """Mine hidden statistical, sequential, and profile patterns across the entire visa database."""
    ensure_official_qa_seeded(db)
    clients = db.query(ClientCase).all()
    client_map = {c.case_id: c for c in clients}
    events = db.query(InterviewEvent).filter(InterviewEvent.event_mode == "embassy_reported").order_by(InterviewEvent.case_id, InterviewEvent.sequence).all()
    flags = db.query(RiskFlag).all()
    official_qa = db.query(OfficialQA).all()

    approved_cases = [c for c in clients if _client_outcome(c) == "approved"]
    refused_cases = [c for c in clients if _client_outcome(c) == "refused"]

    # 1. Hidden Profile Tag Lift (which traits appear FAR more in Approved vs Refused?)
    app_tags = Counter()
    ref_tags = Counter()
    for c in approved_cases:
        for t in set(x.lower() for x in _load_json_list(c.profile_tags_json)):
            app_tags[t] += 1
    for c in refused_cases:
        for t in set(x.lower() for x in _load_json_list(c.profile_tags_json)):
            ref_tags[t] += 1

    tag_insights: list[dict[str, Any]] = []
    for tag in set(app_tags.keys()) | set(ref_tags.keys()):
        a_cnt = app_tags[tag]
        r_cnt = ref_tags[tag]
        tot = a_cnt + r_cnt
        if tot < 2:
            continue
        app_pct = round((a_cnt / tot) * 100, 1)
        tag_insights.append(
            {
                "trait": tag.replace("_", " ").title(),
                "approved": a_cnt,
                "refused": r_cnt,
                "total": tot,
                "approval_rate_pct": app_pct,
                "signal": "positive_driver" if app_pct >= 65 else ("risk_driver" if app_pct <= 40 else "neutral"),
            }
        )
    tag_insights.sort(key=lambda x: (x["total"], x["approval_rate_pct"]), reverse=True)

    # 2. Hidden Embassy Question Sequence Chains (When officers ask Theme A -> what Theme B comes next?)
    by_case: dict[str, list[InterviewEvent]] = defaultdict(list)
    for ev in events:
        by_case[ev.case_id].append(ev)
    transitions = Counter()
    for evs in by_case.values():
        for i in range(len(evs) - 1):
            t1, t2 = evs[i].theme, evs[i + 1].theme
            if t1 and t2 and t1 != t2:
                transitions[(t1, t2)] += 1

    question_chains = [
        {
            "from_theme": t1,
            "to_theme": t2,
            "occurrences": cnt,
            "insight": f"When Kingston officers probe '{t1.replace('_', ' ')}', they frequently pivot immediately to '{t2.replace('_', ' ')}' ({cnt} recorded transitions).",
        }
        for (t1, t2), cnt in transitions.most_common(6)
    ]

    # 3. Co-occurring Risk Flag Patterns across clients
    flags_by_case: dict[str, list[RiskFlag]] = defaultdict(list)
    for f in flags:
        if f.severity in ("red", "amber"):
            flags_by_case[f.case_id].append(f)
    pair_counts = Counter()
    for flist in flags_by_case.values():
        titles = sorted({f.code for f in flist})
        for i in range(len(titles)):
            for j in range(i + 1, len(titles)):
                pair_counts[(titles[i], titles[j])] += 1

    co_risk_patterns = [
        {
            "flag_a": a,
            "flag_b": b,
            "cases_affected": cnt,
            "insight": f"{cnt} cases carry BOTH {a} and {b} simultaneously — fixing documents & personal data resolves both risk drivers at once.",
        }
        for (a, b), cnt in pair_counts.most_common(5)
    ]

    # 4. Blind Spots & Hidden Anomalies
    anomalies: list[str] = []
    high_score_refused = [c for c in refused_cases if c.standing_score >= 75]
    if high_score_refused:
        anomalies.append(
            f"Hidden Anomaly: {len(high_score_refused)} refused case(s) ({', '.join(c.case_id for c in high_score_refused[:4])}) had Good Standing ≥75% — proving strong documents MUST be paired with concise, confident interview delivery on 214(b) ties."
        )
    unanswered_hard = [
        f for f in flags if f.severity == "red" and not (f.client_response or "").strip()
    ]
    if unanswered_hard:
        anomalies.append(
            f"Training Gap: {len(unanswered_hard)} high-severity red flags across active cases have zero recorded practice clarifications yet."
        )
    avg_app_score = round(sum(c.standing_score for c in approved_cases) / len(approved_cases), 1) if approved_cases else 0
    avg_ref_score = round(sum(c.standing_score for c in refused_cases) / len(refused_cases), 1) if refused_cases else 0
    anomalies.append(
        f"Score Separation: Approved cases average {avg_app_score}% Document/Data Standing vs. {avg_ref_score}% for refused cases (n={len(approved_cases)} approved, n={len(refused_cases)} refused)."
    )

    # 5. Optional AI Deep Synthesis (falls back cleanly offline!)
    ai_summary = ""
    ai_provider = "statistical-miner"
    target_note = ""
    if case_id and case_id.upper() in client_map:
        tc = client_map[case_id.upper()]
        target_note = f" Also highlight 2 tailored takeaways for active client {tc.case_id} ({tc.full_name or tc.pseudonym}, {tc.visa_class}, standing {tc.standing_score}%)."

    summary_prompt = (
        f"Analyze these mined U.S. Embassy Kingston visa interview patterns ({len(clients)} cases, {len(events)} embassy questions, {len(official_qa)} official Q&As):\n"
        f"- Top approval/refusal traits: {json.dumps(tag_insights[:6])}\n"
        f"- Question transition chains: {json.dumps(question_chains[:4])}\n"
        f"- Co-occurring risk pairs: {json.dumps(co_risk_patterns[:4])}\n"
        f"- Anomalies: {json.dumps(anomalies)}\n"
        f"Write 4 punchy bullet points summarizing the hidden patterns staff should act on.{target_note}"
    )
    llm_res = call_llm_detailed(db, COMPLIANCE_SYSTEM_PROMPT, summary_prompt)
    if llm_res.get("text"):
        ai_summary = llm_res["text"].strip()
        ai_provider = llm_res.get("provider", "ai")
    else:
        top_pos = [t["trait"] for t in tag_insights if t["signal"] == "positive_driver"][:3]
        top_risk = [t["trait"] for t in tag_insights if t["signal"] == "risk_driver"][:3]
        ai_summary = (
            f"• **Strongest Approval Drivers:** {', '.join(top_pos) or 'Verified employment, clear trip purpose & prior travel'} show the highest approval rates across decided Kingston cases.\n"
            f"• **Primary 214(b) Risk Clusters:** {', '.join(top_risk) or 'Prior refusals, unverified income & weak return ties'} require verified Vault documentation BEFORE interview training.\n"
            f"• **Dominant Embassy Pivot Chain:** {question_chains[0]['insight'] if question_chains else 'Purpose of Trip → Employment → Monthly Gross JMD Salary.'}\n"
            f"• **Core Takeaway:** Fix Documents & Personal Data first (~90% of risk), then drill the Top 5 Hardest + Most Common questions in Quiz Builder."
        )

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "provider_used": ai_provider,
        "dataset_summary": {
            "total_cases": len(clients),
            "approved_cases": len(approved_cases),
            "refused_cases": len(refused_cases),
            "embassy_events": len(events),
            "official_qa_count": len(official_qa),
            "avg_approved_standing": avg_app_score,
            "avg_refused_standing": avg_ref_score,
        },
        "cohort_stats": compute_cohort_approval_stats(db),
        "trait_patterns": tag_insights[:10],
        "question_chains": question_chains,
        "co_occurring_risks": co_risk_patterns,
        "anomalies": anomalies,
        "executive_summary": ai_summary,
    }


def generate_printable_quiz_pdf(
    db: Session,
    case_id: str | None = None,
    q_filter: str = "all",
    include_answers: bool = True,
) -> Path:
    """Generate a clean, branded printable Interview Training & Question Sheet PDF."""
    canvas = build_quiz_canvas(db, case_id=case_id, q_filter=q_filter, effective_mode=True)
    branding = db.query(BrandingConfig).first()
    agency = branding.agency_name if branding else "Jahtaria Travel Services"

    scope = canvas["scope"]
    safe_id = scope["case_id"].replace(" ", "_")
    out_path = GENERATED_DIR / f"Quiz_Prep_Sheet_{safe_id}_{q_filter}.pdf"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    styles = getSampleStyleSheet()
    title_st = ParagraphStyle("QTitle", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#111318"), spaceAfter=4)
    sub_st = ParagraphStyle("QSub", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#4B5563"), spaceAfter=12)
    h2_st = ParagraphStyle("QH2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0B3C68"), spaceBefore=10, spaceAfter=6)
    body_st = ParagraphStyle("QBody", parent=styles["Normal"], fontSize=9.5, leading=13.5, textColor=colors.HexColor("#111827"))
    meta_st = ParagraphStyle("QMeta", parent=styles["Normal"], fontSize=8.2, leading=11, textColor=colors.HexColor("#4B5563"))

    story: list[Any] = [
        Paragraph(f"{agency} — Interview Question & Training Sheet", title_st),
        Paragraph(
            f"Target: <b>{scope['client_name']}</b> ({scope['case_id']}) &nbsp;|&nbsp; "
            f"Filter: <b>{q_filter.replace('_', ' ').title()}</b> &nbsp;|&nbsp; "
            f"Printed: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            sub_st,
        ),
    ]

    if scope["case_id"] != "ALL" and scope.get("standing_score") is not None:
        story.append(
            Paragraph(
                f"<b>Document &amp; Profile Standing:</b> {scope['standing_score']}% ({str(scope.get('denial_risk_level') or '').upper()} RISK) — "
                "Verify physical documents &amp; DS-160 fields first; use these questions for truthful, concise verbal readiness.",
                meta_st,
            )
        )
        story.append(Spacer(1, 8))

    # Section 1: Generated Questions (X) & Client Answers (Y)
    story.append(Paragraph("Part 1 — Tailored Client Questions (X) &amp; Recorded Answers (Y)", h2_st))
    y_by_x = {y["x_id"]: y for y in canvas["lane_y"]}
    rows_xy = [["#", "Theme / Difficulty", "Question to Ask Client (X)", "Recorded Answer / Live Staff Notes (Y)"]]
    for idx, x in enumerate(canvas["lane_x"], start=1):
        y = y_by_x.get(x["id"])
        ans_cell = (
            y["answer_text"]
            if (include_answers and y and y.get("has_answer"))
            else "________________________________________\n________________________________________"
        )
        rows_xy.append(
            [
                str(idx),
                Paragraph(f"<b>{x['theme_id'].replace('_', ' ').title()}</b><br/>{x['difficulty'].upper()}", meta_st),
                Paragraph(x["question_text"], body_st),
                Paragraph(ans_cell, meta_st),
            ]
        )

    tbl1 = Table(rows_xy, colWidths=[0.35 * inch, 1.25 * inch, 2.9 * inch, 2.75 * inch], repeatRows=1)
    tbl1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111318")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl1)
    story.append(Spacer(1, 14))

    # Section 2: Official U.S. Embassy / Organization Questions (Z) & Winning Proof Points (A)
    story.append(Paragraph("Part 2 — Official Embassy Questions (Z) &amp; Winning Proof Points (A)", h2_st))
    a_by_z = {a["z_id"]: a for a in canvas["lane_a"]}
    rows_za = [["#", "Freq / Risk", "Official Embassy Question (Z)", "Winning Proof Pattern / Caution (A)"]]
    for idx, z in enumerate(canvas["lane_z"], start=1):
        a = a_by_z.get(z["id"])
        rows_za.append(
            [
                str(idx),
                Paragraph(f"<b>{z['frequency']}×</b><br/>{z['difficulty'].upper()}<br/>{z['outcome_tag'].upper()}", meta_st),
                Paragraph(z["question_text"], body_st),
                Paragraph((a["answer_text"] if (include_answers and a) else "Truthful, concise answer matching DS-160."), meta_st),
            ]
        )

    tbl2 = Table(rows_za, colWidths=[0.35 * inch, 1.05 * inch, 2.85 * inch, 3.0 * inch], repeatRows=1)
    tbl2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3C68")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl2)
    story.append(Spacer(1, 10))
    from app.services.extensions_service import get_custom_pdf_notes

    for note in get_custom_pdf_notes(db):
        story.append(Paragraph(f"<b>Agency Note:</b> {note.replace('&', '&amp;').replace('<', '&lt;')}", meta_st))
        story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            "<i>Compliance Notice: Truthful interview readiness &amp; factual verification only. Never memorize scripted falsehoods — final decisions rest solely with the U.S. Consular Officer.</i>",
            meta_st,
        )
    )

    doc.build(story)
    return out_path


def handle_quiz_builder_chat(
    db: Session,
    message: str,
    current_case_id: str | None = None,
    current_cohort: str = "all",
    current_q_filter: str = "all",
    current_a_filter: str = "all",
    current_visa_class: str = "all",
    current_effective_mode: bool = False,
    author: str = "Quiz Builder Chat",
) -> dict[str, Any]:
    """Natural-language controller for the simplified Zoomable Quiz Builder Canvas + Chat panel."""
    import re
    from app.services import hermes_engine

    ensure_official_qa_seeded(db)
    raw = (message or "").strip()
    low = raw.lower()

    all_clients = db.query(ClientCase).all()
    client_ids = {c.case_id.upper(): c for c in all_clients}

    # 1. Detect explicit case ID (C034, co34, case 34) or client name mention
    next_case = current_case_id or "ALL"
    if any(k in low for k in ("all clients", "general bank", "everyone", "reset canvas", "show all")):
        next_case = "ALL"
    else:
        m_cid = re.search(r"\b[cC][oO0]?(\d{1,3})\b", raw)
        if m_cid:
            cand = f"C{int(m_cid.group(1)):03d}"
            if cand in client_ids:
                next_case = cand
        else:
            for c in all_clients:
                nm = (c.full_name or "").strip().lower()
                if nm and len(nm) >= 5 and nm in low:
                    next_case = c.case_id
                    break

    next_cohort = current_cohort
    next_q_filter = current_q_filter
    next_a_filter = current_a_filter
    next_visa = current_visa_class
    next_effective = current_effective_mode

    # 2. Detect filter / cohort / visa commands
    if any(k in low for k in ("reset", "clear filter", "show all")):
        next_cohort = "all"
        next_q_filter = "all"
        next_a_filter = "all"
        next_visa = "all"
        next_effective = False

    if any(k in low for k in ("hardest", "hard question", "toughest", "difficult")):
        next_q_filter = "hardest"
    elif any(k in low for k in ("weak", "risky", "unanswered", "gap")):
        next_q_filter = "weak"
    elif any(k in low for k in ("most common", "common", "frequent")):
        next_q_filter = "most_common"
    elif any(k in low for k in ("most used", "popular", "top used")):
        next_q_filter = "most_used"

    if "weak answer" in low or "refused answer" in low:
        next_a_filter = "weak"
    elif "strong answer" in low or "approved answer" in low or "winning answer" in low:
        next_a_filter = "strong"
    elif "common answer" in low:
        next_a_filter = "most_common"

    for vc in ("B1/B2", "F-1", "H-2B", "J-1"):
        if vc.lower() in low or vc.replace("-", "").lower() in low:
            next_visa = vc
            break

    if "prior refusal" in low or "re-applicant" in low:
        next_cohort = "prior_refusal"
    elif "self-employed" in low or "business owner" in low:
        next_cohort = "self_employed"
    elif "first-time" in low or "first time" in low:
        next_cohort = "first_time"
    elif "u.s. relative" in low or "us relative" in low:
        next_cohort = "us_relatives"
    elif "employed" in low:
        next_cohort = "employed_b1b2"
    elif "student" in low:
        next_cohort = "student_f1"

    canvas_state: dict[str, Any] = {
        "case_id": next_case,
        "cohort": next_cohort,
        "q_filter": next_q_filter,
        "a_filter": next_a_filter,
        "visa_class": next_visa,
        "effective_mode": next_effective,
    }
    output_questions: list[dict[str, Any]] = []
    print_pdf_url: str | None = None
    refresh_canvas = False
    trigger_flow = False

    # 3. Intent: Add Official Q&A (Z / A)
    if any(k in low for k in ("add official", "new official", "save official", "enter official")):
        # Parse "question ... answer ..." if provided
        q_part = raw
        a_part = ""
        m_qa = re.search(r"(?:question|q)[:\-]\s*(.+?)(?:\s+(?:answer|a)[:\-]\s*(.+))?$", raw, re.IGNORECASE | re.DOTALL)
        if m_qa:
            q_part = (m_qa.group(1) or "").strip()
            a_part = (m_qa.group(2) or "").strip()
        else:
            q_part = re.sub(r"^(?:please\s+)?(?:add|new|save|enter)\s+official\s+(?:question|q&a|qa)?[:\-\s]*", "", raw, flags=re.IGNORECASE).strip()
        if q_part:
            row = OfficialQA(
                theme_id="purpose_of_trip",
                visa_class=next_visa if next_visa != "all" else "B1/B2",
                question_text=q_part,
                answer_text=a_part or "Truthful, concise answer aligned with DS-160 and supporting documents.",
                answer_quality="strong",
                outcome_tag="approved",
                difficulty="medium",
                frequency_count=1,
                profile_tags_json="[]",
                added_by=author,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            refresh_canvas = True
            trigger_flow = True
            return {
                "reply": f"Added Official Question **`Z-{row.id}`** and Answer **`A-{row.id}`** onto the canvas:\n- **Q:** {row.question_text}\n- **A:** {row.answer_text}",
                "canvas_state": canvas_state,
                "refresh_canvas": refresh_canvas,
                "trigger_flow": trigger_flow,
                "output_questions": output_questions,
                "print_pdf_url": None,
            }

    # 4. Intent: Print / Export PDF
    if any(k in low for k in ("print", "pdf", "export sheet", "handout", "worksheet")):
        pdf_case = next_case if next_case and next_case != "ALL" else "ALL"
        print_pdf_url = f"/api/quiz-builder/print-pdf?case_id={pdf_case}&q_filter={next_q_filter}&include_answers=true"
        scope_label = f"Case **{pdf_case}**" if pdf_case != "ALL" else "**General Agency Question Bank**"
        return {
            "reply": f"Prepared the printable interview question sheet for {scope_label} (filter: `{next_q_filter}`). Opening PDF now — you can also click the button below to reprint anytime.",
            "canvas_state": canvas_state,
            "refresh_canvas": False,
            "trigger_flow": False,
            "output_questions": [],
            "print_pdf_url": print_pdf_url,
        }

    # 5. Intent: Analyze Hidden Patterns
    if any(k in low for k in ("pattern", "hidden", "analyz", "analys", "mine ", "anomaly", "cluster")):
        pat = analyze_hidden_patterns(db=db, case_id=None if next_case == "ALL" else next_case)
        canvas_state["effective_mode"] = True
        lines = [
            f"### Hidden Patterns Across {pat['dataset_summary']['total_cases']} Cases ({pat['dataset_summary']['embassy_events']} Embassy Qs)",
            pat["executive_summary"],
            "",
            "**Top Approving Client Types:**",
        ]
        for co in pat["cohort_stats"][:4]:
            rate = f"{co['approval_rate_pct']}%" if co["approval_rate_pct"] is not None else "In Prep"
            lines.append(f"- **{co['label']}**: {rate} ({co['sample_label']}) · Avg Docs/Data Standing `{co['avg_standing_score']}%`")
        if pat["question_chains"]:
            lines.append("")
            lines.append("**Embassy Follow-Up Pivot Chains (`Z1 → Z2`):**")
            for ch in pat["question_chains"][:3]:
                lines.append(f"- `{ch['from_theme']} → {ch['to_theme']}` ({ch['occurrences']}×)")
        if pat["co_occurring_risks"]:
            lines.append("")
            lines.append("**Co-Occurring Risk Clusters:**")
            for cr in pat["co_occurring_risks"][:3]:
                lines.append(f"- `{cr['flag_a']}` + `{cr['flag_b']}` ({cr['cases_affected']} cases)")
        if pat["anomalies"]:
            lines.append("")
            lines.append("**Blind Spots & Anomalies:**")
            for an in pat["anomalies"][:3]:
                lines.append(f"- {an}")
        return {
            "reply": "\n".join(lines),
            "canvas_state": canvas_state,
            "refresh_canvas": True,
            "trigger_flow": True,
            "output_questions": [],
            "print_pdf_url": None,
        }

    # 6. Intent: Generate Questions (Propagation Flow -> Output Nodes!)
    if any(k in low for k in ("generat", "new question", "create question", "predict", "build quiz", "make question", "propagat")):
        m_cnt = re.search(r"\b(\d+)\b", raw)
        cnt = max(1, min(8, int(m_cnt.group(1)))) if m_cnt else 4
        focus = next_q_filter if next_q_filter != "all" else "all"
        gen = generate_relationship_questions(
            db=db,
            case_id=None if next_case == "ALL" else next_case,
            count=cnt,
            focus=focus,
            author=author,
        )
        output_questions = gen["generated"]
        canvas_state["case_id"] = gen["case_id"]
        canvas_state["effective_mode"] = True
        lines = [
            f"Propagated **{len(output_questions)} new questions** into the **Output** column for **{gen['case_id']}** (via `{gen['provider']}`):",
            "",
        ]
        for idx, q in enumerate(output_questions, start=1):
            lines.append(f"{idx}. **{q['question_text']}** (`{q['theme_id'].replace('_', ' ')}`)")
        lines.append("\nRight-click any node on the canvas or click its dropdown arrow (`▾`) to inspect rationale, play voice, or record answers.")
        return {
            "reply": "\n".join(lines),
            "canvas_state": canvas_state,
            "refresh_canvas": True,
            "trigger_flow": True,
            "output_questions": output_questions,
            "print_pdf_url": None,
        }

    # 7. Intent: Effective Pathway / Who Gets Approved Most
    if any(k in low for k in ("effective", "pathway", "trace", "who gets", "get through", "approval rate", "approved most", "best client")):
        canvas_state["effective_mode"] = True
        cohorts = compute_cohort_approval_stats(db)
        lines = [
            f"**Effective Pathway ON** — tracing `X → Y → Z → A → Output` for **{next_case if next_case != 'ALL' else 'All Matching Clients'}**.",
            "",
            "**Client Types Getting Through Most:**",
        ]
        for co in cohorts:
            rate = f"**{co['approval_rate_pct']}%**" if co["approval_rate_pct"] is not None else "In Prep"
            lines.append(f"- {co['label']}: {rate} ({co['sample_label']}) · Avg Docs/Data `{co['avg_standing_score']}%`")
        return {
            "reply": "\n".join(lines),
            "canvas_state": canvas_state,
            "refresh_canvas": True,
            "trigger_flow": True,
            "output_questions": [],
            "print_pdf_url": None,
        }

    # 8. Filter / Scope-Only Command
    state_changed = (
        next_case != (current_case_id or "ALL")
        or next_cohort != current_cohort
        or next_q_filter != current_q_filter
        or next_a_filter != current_a_filter
        or next_visa != current_visa_class
        or next_effective != current_effective_mode
    )
    if state_changed:
        parts = [f"Scope: **{next_case}**"]
        if next_q_filter != "all":
            parts.append(f"Questions: `{next_q_filter.replace('_', ' ')}`")
        if next_a_filter != "all":
            parts.append(f"Answers: `{next_a_filter.replace('_', ' ')}`")
        if next_visa != "all":
            parts.append(f"Visa: `{next_visa}`")
        if next_cohort != "all":
            parts.append(f"Cohort: `{next_cohort.replace('_', ' ')}`")
        return {
            "reply": f"Updated canvas — {' · '.join(parts)}.\nClick any node's `▾` dropdown or right-click to inspect, speak, or trace its flow.",
            "canvas_state": canvas_state,
            "refresh_canvas": True,
            "trigger_flow": True,
            "output_questions": [],
            "print_pdf_url": None,
        }

    # 9. General Conversational Coaching / Q&A (delegates cleanly to configured LLM or offline advisor)
    ctx_note = ""
    if next_case != "ALL" and next_case in client_ids:
        cl = client_ids[next_case]
        ctx_note = f"[Active Quiz Builder Client: {cl.case_id} ({cl.full_name or cl.pseudonym}), {cl.visa_class}, Docs/Data Standing {cl.standing_score}%, Occupation: {cl.occupation or 'N/A'}] "
    ans = hermes_engine.answer_customer_question(db, f"{ctx_note}{raw}")
    return {
        "reply": ans.get("reply") or "Ask me to **generate questions**, **filter hardest/weak**, **trace effective pathway**, **find hidden patterns**, or **print PDF**.",
        "canvas_state": canvas_state,
        "refresh_canvas": False,
        "trigger_flow": False,
        "output_questions": [],
        "print_pdf_url": None,
    }

