"""Deterministic U.S. Visa (Kingston, Jamaica) Good Standing & Denial Risk Engine.

Follows the JAHTARIA Visa Intelligence compliance rules:
- Assists truthful application verification and accurate, spontaneous answers.
- Never coaches concealment, invents ties, infers officer motives as fact, or guarantees approval.
- Separates policy-mandatory questions (e.g. home_country_safety) from profile-driven predictions.
- Flags contradictions (gross vs net JMD income, U.S. relatives, marital legal status, DS-160 barcode, passport validity).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import ClientCase, ClientDocument, InterviewEvent, InterviewPrediction, QuestionTaxonomy, RiskFlag


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def _load_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def evaluate_client_standing(db: Session, client: ClientCase) -> dict[str, Any]:
    """Run deterministic Kingston Embassy & Jahtaria compliance checks and persist RiskFlags.

    Scoring Policy (v2.4.0 Correction):
    - Documents & Verified Personal Data drive ~90% of Good Standing / Risk Score.
    - Answering follow-up or mock practice questions NEVER erases a missing document or
      personal-data contradiction; it contributes ONLY a small readiness bump (+1 pt per
      answered question/practice item, strictly capped at +6 pts total).
    """

    # Keep client responses from existing flags if re-auditing
    existing_responses: dict[str, tuple[str, bool]] = {}
    for old_flag in db.query(RiskFlag).filter(RiskFlag.case_id == client.case_id).all():
        existing_responses[old_flag.code] = (old_flag.client_response, old_flag.resolved)

    db.query(RiskFlag).filter(RiskFlag.case_id == client.case_id).delete()

    flags: list[dict[str, Any]] = []
    # 94 pts come from Documents & Verified Personal Data; up to +6 pts come from Practice Questions (total 100)
    score = 94
    answered_clarifications = 0
    tags = set(t.lower() for t in _load_json_list(client.profile_tags_json))

    def add_flag(
        code: str,
        severity: str,
        category: str,
        title: str,
        detail: str,
        suggested_fix: str,
        follow_up_question: str,
        source_citation: str,
        source_url: str,
        penalty: int,
    ) -> None:
        nonlocal score, answered_clarifications
        prev_resp, prev_resolved = existing_responses.get(code, ("", False))
        # Answering a text question does NOT wipe out a real document/data risk penalty!
        # Only fixing the underlying client data or document removes the penalty.
        has_answer = bool((prev_resp or "").strip()) or bool(prev_resolved)
        if has_answer and penalty > 0:
            answered_clarifications += 1
        # Keep full data/document penalty (tiny 1-pt recognition handled in capped practice_bonus below)
        effective_penalty = penalty
        score -= effective_penalty
        flags.append(
            {
                "code": code,
                "severity": severity,
                "category": category,
                "title": title,
                "detail": detail,
                "suggested_fix": suggested_fix,
                "follow_up_question": follow_up_question,
                "client_response": prev_resp,
                "source_citation": source_citation,
                "source_url": source_url,
                "score_impact": -effective_penalty if effective_penalty else 0,
                "resolved": prev_resolved,
            }
        )

    # 1. Passport validity (6-month rule beyond intended stay/entry)
    exp_date = _parse_date(client.passport_expiry)
    travel_date = _parse_date(client.intended_travel_date) or (date.today() + timedelta(days=45))
    if not exp_date:
        add_flag(
            code="PASSPORT_EXPIRY_MISSING",
            severity="amber",
            category="passport_pica",
            title="Passport Expiration Date Not Verified",
            detail="Passport validity has not been verified yet. U.S. Embassy Kingston requires an unexpired passport valid for at least 6 months beyond intended U.S. stay.",
            suggested_fix="Confirm passport biographic page and expiration date; if under 6 months remaining, renew via PICA Simplified Adult Renewal before booking interview.",
            follow_up_question="What is the exact expiration date printed on your current Jamaican passport?",
            source_citation="U.S. Embassy Kingston / PICA Jamaica",
            source_url="https://www.pica.gov.jm/passport/renew",
            penalty=12,
        )
    elif exp_date < travel_date + timedelta(days=180):
        add_flag(
            code="PASSPORT_UNDER_6_MONTHS",
            severity="red",
            category="passport_pica",
            title="Passport Expires Within 6 Months of Intended Travel",
            detail=f"Passport expires on {exp_date.isoformat()}, which is less than 6 months after intended travel ({travel_date.isoformat()}). This risks turn-away or visa issuance delay.",
            suggested_fix="Submit a PICA Jamaican Passport Renewal (Simplified Adult Renewal Form 1) immediately before locking DS-160 and AIS appointment.",
            follow_up_question="Have you initiated a Jamaican passport renewal with PICA yet, and do you have your current passport undamaged?",
            source_citation="U.S. Dept. of State — Kingston Post Supplement & PICA",
            source_url="https://www.pica.gov.jm/sites/default/files/Forms/Adult%20Renewal%20Form%20%28Simplified%29.pdf",
            penalty=25,
        )
    else:
        add_flag(
            code="PASSPORT_VALID",
            severity="green",
            category="passport_pica",
            title="Passport Validity Meets 6-Month Requirement",
            detail=f"Passport expires {exp_date.isoformat()}, safely exceeding 6 months past intended travel.",
            suggested_fix="Bring both current passport and any expired passports containing prior U.S. visas to Kingston Embassy.",
            follow_up_question="",
            source_citation="U.S. Embassy Kingston",
            source_url="https://jm.usembassy.gov/visas/",
            penalty=0,
        )

    # 2. DS-160 Barcode Match Rule (Effective April 1, 2025 — Kingston Embassy mandatory rule!)
    ds160 = (client.ds160_confirmation_id or "").strip().upper()
    ais_code = (client.ais_appointment_barcode or "").strip().upper()
    if not ds160:
        add_flag(
            code="DS160_MISSING",
            severity="amber",
            category="ds160_barcode",
            title="DS-160 Confirmation Number (AA...) Not Recorded",
            detail="Form DS-160 must be submitted via CEAC before the interview. Starting April 1, 2025, Kingston Embassy refuses entry if the DS-160 barcode does not match the AIS booking.",
            suggested_fix="Complete DS-160 draft verification, submit on ceac.state.gov, and record the exact AA confirmation barcode.",
            follow_up_question="Have you already created or submitted a Form DS-160 on ceac.state.gov? If yes, please share the AA confirmation code.",
            source_citation="U.S. Embassy Kingston — April 1, 2025 Barcode Rule",
            source_url="https://jm.usembassy.gov/correct-ds-160-barcodes-are-required-for-all-appointments/",
            penalty=10,
        )
    elif not ds160.startswith("AA"):
        add_flag(
            code="DS160_INVALID_PREFIX",
            severity="red",
            category="ds160_barcode",
            title="Invalid DS-160 Confirmation Barcode Format",
            detail=f"Recorded DS-160 ID '{ds160}' does not start with 'AA'. Valid CEAC DS-160 confirmation barcodes always begin with AA.",
            suggested_fix="Verify the printed CEAC DS-160 confirmation page and enter the exact 10-character AA code.",
            follow_up_question="Can you double-check the 10-character code starting with 'AA' on your DS-160 confirmation page?",
            source_citation="U.S. Embassy Kingston — DS-160 Barcode Policy",
            source_url="https://jm.usembassy.gov/correct-ds-160-barcodes-are-required-for-all-appointments/",
            penalty=18,
        )
    elif ais_code and ds160 != ais_code:
        add_flag(
            code="DS160_AIS_MISMATCH",
            severity="red",
            category="ds160_barcode",
            title="CRITICAL: DS-160 Barcode Does Not Match AIS Appointment Barcode",
            detail=f"DS-160 barcode ({ds160}) differs from AIS appointment barcode ({ais_code}). Under the April 1, 2025 Kingston Embassy rule, applicants with mismatched barcodes will NOT be allowed to interview.",
            suggested_fix="Update the DS-160 number inside ais.usvisa-info.com/en-jm/niv at least 48 hours before interview, or reschedule with the matching DS-160 barcode.",
            follow_up_question="Did you submit a newer DS-160 after booking your AIS appointment? We must sync the exact AA barcode before your interview date.",
            source_citation="U.S. Embassy Kingston — Mandatory Barcode Match",
            source_url="https://jm.usembassy.gov/correct-ds-160-barcodes-are-required-for-all-appointments/",
            penalty=28,
        )
    else:
        add_flag(
            code="DS160_BARCODE_MATCH",
            severity="green",
            category="ds160_barcode",
            title="DS-160 & AIS Appointment Barcodes Verified",
            detail=f"DS-160 barcode {ds160} matches official AA format and appointment record.",
            suggested_fix="Print the DS-160 confirmation page with clear barcode for Old Hope Road check-in.",
            follow_up_question="",
            source_citation="U.S. Embassy Kingston",
            source_url="https://jm.usembassy.gov/correct-ds-160-barcodes-are-required-for-all-appointments/",
            penalty=0,
        )

    # 3. Gross vs Net Monthly JMD Income Consistency (Jahtaria C001 real-world trap!)
    gross = client.monthly_gross_jmd
    net = client.monthly_net_jmd
    if gross is not None and net is not None and net > gross:
        add_flag(
            code="INCOME_GROSS_NET_INVERTED",
            severity="red",
            category="financial_consistency",
            title="Contradiction: Net Take-Home Income Exceeds Gross Monthly Salary",
            detail=f"Net income (JMD {net:,.0f}) is recorded higher than Gross income (JMD {gross:,.0f}). DS-160 asks for monthly gross income; officers frequently compare spoken answers to DS-160.",
            suggested_fix="Verify latest pay slip and employer letter; separate gross monthly salary (for DS-160) from net take-home pay so the client explains both accurately.",
            follow_up_question="Can you confirm your exact monthly GROSS salary (before NIS/NHT/PAYE deductions) versus your NET take-home pay on your latest payslip?",
            source_citation="JAHTARIA Compliance Audit (Case C001 Income Trap)",
            source_url="https://ceac.state.gov/",
            penalty=18,
        )
    elif "salary_gross_net" in tags or (gross is not None and net is None) or (net is not None and gross is None):
        add_flag(
            code="INCOME_GROSS_NET_REVIEW",
            severity="amber",
            category="financial_consistency",
            title="Verify Gross vs. Net JMD Salary Distinction Before Interview",
            detail="Only one income figure or a known gross-vs-net discrepancy flag is present. A gross vs. net difference is a normal distinction, NOT automatically false, but must be reconciled cleanly.",
            suggested_fix="Confirm gross monthly JMD on DS-160 matches employment letter/payslips and coach client to state clearly whether a figure is gross or take-home.",
            follow_up_question="Do your recent Jamaican payslips show both your gross monthly pay and net take-home pay clearly?",
            source_citation="JAHTARIA Visa Intelligence Engineering Handoff",
            source_url="https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application.html",
            penalty=8,
        )
    elif gross is None and net is None:
        add_flag(
            code="INCOME_UNVERIFIED",
            severity="amber",
            category="financial_consistency",
            title="Monthly Income & Financial Support Not Documented",
            detail="No monthly JMD income or funding source is entered yet. Consular officers routinely assess economic ties to Jamaica under INA 214(b).",
            suggested_fix="Record verified gross & net monthly JMD salary (or business net personal drawings / sponsor funding) supported by pay slips or bank statements.",
            follow_up_question="What is your current monthly gross salary (or personal monthly earnings from your business) in JMD, and who is paying for this trip?",
            source_citation="U.S. Dept. of State — Visitor Visa (INA 214(b))",
            source_url="https://travel.state.gov/content/travel/en/us-visas/tourism-visit/visitor.html",
            penalty=10,
        )
    else:
        add_flag(
            code="INCOME_CONSISTENT",
            severity="green",
            category="financial_consistency",
            title="Gross & Net JMD Income Figures Reconciled",
            detail=f"Gross JMD {gross:,.0f} / Net JMD {net:,.0f} documented cleanly for truthful DS-160 alignment.",
            suggested_fix="Bring 3 months of matching pay slips and employment verification letter to the interview.",
            follow_up_question="",
            source_citation="JAHTARIA Verification Standard",
            source_url="https://travel.state.gov/content/travel/en/us-visas/tourism-visit/visitor.html",
            penalty=0,
        )

    # 4. U.S. Relatives / Partner / Fiancé(e) Truthful Disclosure (C002, C003, C004 traps)
    has_us_partner_tag = any(t in tags for t in ("us_fiancee_lpr", "us_spouse", "us_family", "us_mother", "us_mother_lpr", "us_citizen_children"))
    if (client.has_us_relatives or has_us_partner_tag) and not (client.us_relatives_details or "").strip():
        add_flag(
            code="US_RELATIVES_DETAILS_MISSING",
            severity="red",
            category="family_disclosure",
            title="U.S. Relatives / Partner Indicated Without Verified Details",
            detail="Case indicates U.S.-based relatives or partner, but exact legal relationship and immigration status are not documented. Omitting immediate U.S. relatives on DS-160 causes severe credibility/misrepresentation risk.",
            suggested_fix="Document every immediate relative in the U.S. (parent, sibling, spouse, fiancé(e), child) and confirm exact status (USC, LPR, NIV) matches DS-160 truthfully.",
            follow_up_question="Please list every immediate relative or partner living in the U.S. (relationship, city/state, and whether they are a U.S. citizen, green card holder, or visa holder).",
            source_citation="JAHTARIA Compliance Rules (Cases C002/C004)",
            source_url="https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application.html",
            penalty=16,
        )
    elif "legally_married_separated" in tags or (client.marital_status or "").lower() in ("separated", "legally married - separated"):
        add_flag(
            code="MARITAL_LEGAL_STATUS_CHECK",
            severity="amber",
            category="family_disclosure",
            title="Legal Marital Status (Separated) Must Match RGD & DS-160",
            detail="Applicant is legally married but separated. U.S. Embassy Kingston requires truthful legal marital status (never list 'Single' if no final decree absolute exists).",
            suggested_fix="Confirm whether a Decree Absolute exists; if still legally married, reflect exact status truthfully on DS-160 and prepare a clear, concise answer on spouse's status/employment.",
            follow_up_question="Are you legally divorced with a final Decree Absolute, or still legally married and living separately?",
            source_citation="U.S. Embassy Kingston / RGD Civil Status Guidance",
            source_url="https://travel.state.gov/content/travel/en/us-visas/Supplements/Supplements_by_Post/KNG-Kingston.html",
            penalty=9,
        )

    # 5. Prior Refusals / Prior Immigration History (C001, C005, C006, C007)
    prior_refusals = client.prior_us_refusals or (1 if ("previous_refusal" in tags or "prior_refusal" in tags or "multiple_refusals" in tags) else 0)
    if prior_refusals > 0 or any(t in tags for t in ("unfinished_us_studies", "visa_cancelled", "former_h2b", "former_f1", "prior_petition")):
        sev = "red" if (prior_refusals >= 2 or "visa_cancelled" in tags or "unfinished_us_studies" in tags) else "amber"
        pen = 16 if sev == "red" else 10
        add_flag(
            code="PRIOR_IMMIGRATION_HISTORY",
            severity=sev,
            category="immigration_history",
            title=f"Prior U.S. Visa History / Refusals ({prior_refusals} recorded) Requires Chronology Verification",
            detail="Prior refusals, cancelled visas, unfinished F-1 studies, or prior H-2B stays MUST be disclosed truthfully on DS-160. Do not infer refusal grounds without the refusal notice.",
            suggested_fix="Verify exact refusal dates, prior visa types, and any refusal letter (e.g., INA 214(b) or 221(g)); prepare clear truthful explanation of current ties and changes since last application.",
            follow_up_question="What were the exact dates and visa types of all prior U.S. (or Canadian/UK) visa refusals or stays, and what has genuinely changed in your work or family ties since then?",
            source_citation="U.S. Dept. of State — Visa Denials (INA 214(b) / 221(g))",
            source_url="https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/visa-denials.html",
            penalty=pen,
        )

    # 6. Employment & Trip Purpose Completeness
    missing_core = []
    if not (client.purpose_of_trip or "").strip():
        missing_core.append("purpose of trip")
    if not (client.us_destination or "").strip():
        missing_core.append("U.S. destination city/state")
    if not (client.occupation or "").strip():
        missing_core.append("current occupation")
    if missing_core:
        add_flag(
            code="CORE_PROFILE_INCOMPLETE",
            severity="amber",
            category="intake_completeness",
            title=f"Incomplete Intake Fields: {', '.join(missing_core)}",
            detail="Consular interviews in Kingston typically last 2–3 minutes and open with trip purpose, destination, and occupation.",
            suggested_fix="Complete all missing client intake fields before generating DS-160 worksheets or freezing interview predictions.",
            follow_up_question=f"Please provide clear, specific details for: {', '.join(missing_core)}.",
            source_citation="JAHTARIA Intake Standard",
            source_url="https://jm.usembassy.gov/visas/",
            penalty=min(15, 5 * len(missing_core)),
        )
    else:
        add_flag(
            code="CORE_PROFILE_COMPLETE",
            severity="green",
            category="intake_completeness",
            title="Core Trip, Destination & Occupation Details Complete",
            detail=f"Trip purpose ({client.purpose_of_trip[:60]}), destination ({client.us_destination}), and occupation ({client.occupation}) documented.",
            suggested_fix="Cross-check dates against employer leave letter and travel itinerary.",
            follow_up_question="",
            source_citation="JAHTARIA Intake Standard",
            source_url="https://jm.usembassy.gov/visas/",
            penalty=0,
        )

    # 7. RGD 92% Photocopy Advisory (Jamaican civil documents — official KNG Post Supplement rule)
    add_flag(
        code="RGD_92_PERCENT_RULE",
        severity="green",
        category="jamaica_civil",
        title="Kingston Embassy Advisory: Jamaican RGD 92% Photocopy Rule",
        detail="Jamaican RGD birth/marriage certificates are slightly longer than U.S. Letter paper and carry serial numbers at top and bottom. Any photocopy MUST be reduced to 92% scale so serial numbers are never cut off.",
        suggested_fix="Verify every RGD certificate copy (birth, marriage, children's certificates) shows both top and bottom serial numbers clearly.",
        follow_up_question="",
        source_citation="U.S. Embassy Kingston Post Supplement (travel.state.gov)",
        source_url="https://travel.state.gov/content/travel/en/us-visas/Supplements/Supplements_by_Post/KNG-Kingston.html",
        penalty=0,
    )

    # 8. Vault Documents & Practice Readiness Split (Documents + Data = 94 pts, Practice Questions = up to +6 pts)
    vault_docs = db.query(ClientDocument).filter(ClientDocument.case_id == client.case_id).all()
    vault_categories = {d.category for d in vault_docs if d.category}
    doc_bonus = min(4, len(vault_categories) * 2) if vault_docs else 0
    if not vault_docs and (client.outcome_evidence or "").lower() in ("in_preparation", "intake", ""):
        add_flag(
            code="VAULT_DOCS_MISSING",
            severity="amber",
            category="documents_vault",
            title="Supporting Evidence Documents Not Yet Uploaded to Vault",
            detail="Documents & verified personal data are the primary risk drivers. Upload passport scan, payslips/employment letter, bank statements, and 92% RGD copies to the Client Vault.",
            suggested_fix="Upload supporting PDFs/images into the client's Vault so staff can verify figures directly against DS-160.",
            follow_up_question="Which supporting documents (passport scan, payslips, employment letter, bank statement, RGD certificates) are ready to upload?",
            source_citation="U.S. Embassy Kingston — Supporting Evidence Standard",
            source_url="https://jm.usembassy.gov/visas/",
            penalty=6,
        )

    # 8b. Live Agency Custom Risk Rules (AI-Mutable Layer — safely isolated)
    from app.services.extensions_service import evaluate_custom_risk_rules

    evaluate_custom_risk_rules(db, client, add_flag)

    has_active_risk = any(f["severity"] in ("red", "amber") for f in flags)
    max_data_cap = 92 if has_active_risk else 94
    data_and_docs_score = max(5, min(max_data_cap, score + doc_bonus))

    # Count mock interview practice answers + answered follow-up clarifications — VERY small capped lift!
    practice_events = (
        db.query(InterviewEvent)
        .filter(InterviewEvent.case_id == client.case_id, InterviewEvent.event_mode == "mock_practice")
        .count()
    )
    total_practice_answered = answered_clarifications + practice_events
    # Max +6 pts total from answering questions — NEVER overrides missing docs or data contradictions!
    practice_bonus = min(6, total_practice_answered)

    score = max(5, min(100, data_and_docs_score + practice_bonus))
    if score >= 80:
        risk_level = "low"
    elif score >= 60:
        risk_level = "medium"
    elif score >= 40:
        risk_level = "high"
    else:
        risk_level = "critical"

    for item in flags:
        db.add(RiskFlag(case_id=client.case_id, **item))

    client.standing_score = score
    client.denial_risk_level = risk_level
    db.commit()

    return {
        "case_id": client.case_id,
        "standing_score": score,
        "denial_risk_level": risk_level,
        "red_count": sum(1 for f in flags if f["severity"] == "red"),
        "amber_count": sum(1 for f in flags if f["severity"] == "amber"),
        "green_count": sum(1 for f in flags if f["severity"] == "green"),
        "flags": flags,
        "score_breakdown": {
            "data_and_docs_score": data_and_docs_score,
            "practice_bonus": practice_bonus,
            "practice_bonus_cap": 6,
            "practice_answered_count": total_practice_answered,
            "vault_doc_count": len(vault_docs),
        },
        "compliance_note": "Good Standing is driven primarily by verified Documents & Personal Data (~90%). Practice questions contribute only a small readiness lift (max +6 pts) and never guarantee visa approval.",
    }


def generate_ranked_predictions(
    db: Session,
    client: ClientCase,
    author: str = "system_rules",
    replace_unfrozen: bool = True,
) -> list[InterviewPrediction]:
    """Generate ranked profile-driven predictions + separate mandatory policy checklist."""

    if client.predictions_frozen:
        return (
            db.query(InterviewPrediction)
            .filter(InterviewPrediction.case_id == client.case_id)
            .order_by(InterviewPrediction.question_type, InterviewPrediction.rank)
            .all()
        )

    if replace_unfrozen:
        db.query(InterviewPrediction).filter(
            InterviewPrediction.case_id == client.case_id,
            InterviewPrediction.frozen_at.is_(None),
        ).delete()

    taxonomy = {t.theme_id: t for t in db.query(QuestionTaxonomy).all()}
    tags = set(t.lower() for t in _load_json_list(client.profile_tags_json))
    seeded_themes = _load_json_list(client.predicted_themes_json)

    candidates: list[tuple[str, float, str]] = []

    def add_candidate(theme_id: str, conf: float, rationale: str) -> None:
        if any(c[0] == theme_id for c in candidates):
            return
        candidates.append((theme_id, conf, rationale))

    # Standard core questions
    add_candidate("purpose_of_trip", 0.94, "Primary opening question at U.S. Embassy Kingston for nonimmigrant interviews.")
    add_candidate("employment", 0.92, "Consular officers assess economic ties to Jamaica under INA 214(b).")

    # Profile-triggered high-priority themes
    if client.monthly_gross_jmd or client.monthly_net_jmd or "salary_gross_net" in tags or "employed" in tags:
        add_candidate("monthly_income", 0.88, "Income verification & gross-vs-net alignment with DS-160.")
    if "business_owner" in tags or "self_employed" in tags or "hardware_business" in tags:
        add_candidate("business_income", 0.89, "Self-employed/business owners are frequently asked personal earnings vs gross revenue.")
    if client.prior_us_refusals > 0 or any(t in tags for t in ("previous_refusal", "prior_refusal", "multiple_refusals")):
        add_candidate("prior_refusal", 0.91, "Prior refusal history triggers questions on what changed since last application.")
    if "former_h2b" in tags:
        add_candidate("h2b_history", 0.90, "Former H-2B work history requires verifying timely departure and compliance.")
    if "unfinished_us_studies" in tags or "former_f1" in tags or client.visa_class.upper() == "F1":
        add_candidate("unfinished_us_studies", 0.90, "F-1 study history / status continuity is closely scrutinized.")
        add_candidate("funding", 0.86, "Student & sponsored applicants must clearly explain tuition/trip funding.")
    if client.has_us_relatives or any(t in tags for t in ("us_spouse", "us_fiancee_lpr", "us_partner", "us_family")):
        add_candidate("us_contact", 0.87, "U.S. host/contact relationship and itinerary verification.")
        add_candidate("us_relatives", 0.85, "Immediate U.S. relatives disclosure consistency with DS-160.")
    if any(t in tags for t in ("us_fiancee_lpr", "us_spouse", "relationship")):
        add_candidate("us_partner", 0.86, "U.S. partner status and truthful nonimmigrant return intent.")
        add_candidate("marriage_plans", 0.80, "Clarifies honest short-term visit vs immigrant intent.")
    if client.marital_status or "legally_married_separated" in tags:
        add_candidate("marital_status", 0.84, "Marital legal status verification against DS-160 and civil records.")
        if "legally_married_separated" in tags or (client.marital_status or "").lower() in ("married", "legally married - separated"):
            add_candidate("spouse_employment", 0.78, "Follow-up on spouse's location and occupation.")
    if client.children_count > 0 or "children" in tags or "children_jamaica" in tags or "us_citizen_children" in tags:
        add_candidate("children", 0.84, "Family ties in Jamaica or U.S.-citizen children disclosure.")
    if "first_time" in tags:
        add_candidate("first_time_application", 0.82, "First-time applicant baseline screening.")
    if client.us_destination:
        add_candidate("destination", 0.83, "Verifies specific U.S. destination city, lodging, and duration.")
    if client.travel_history_summary or "international_travel" in tags or "travel_canada_uk" in tags:
        add_candidate("travel_history", 0.81, "Prior international travel history and length of prior trips.")

    # Include any seeded pre-interview themes from JAHTARIA package
    for theme in seeded_themes:
        if theme != "home_country_safety":
            add_candidate(theme, 0.79, "Seeded profile theme from Jahtaria historical screening package.")

    # Sort profile-driven predictions by confidence desc
    candidates.sort(key=lambda x: x[1], reverse=True)

    created: list[InterviewPrediction] = []
    for idx, (theme_id, conf, rationale) in enumerate(candidates[:10], start=1):
        tax = taxonomy.get(theme_id)
        q_text = tax.sample_question if tax else f"Follow-up regarding {theme_id.replace('_', ' ')}?"
        pred = InterviewPrediction(
            case_id=client.case_id,
            theme_id=theme_id,
            question_text=q_text,
            question_type="profile_driven",
            rank=idx,
            confidence=round(conf, 2),
            rationale=rationale,
            author=author,
        )
        db.add(pred)
        created.append(pred)

    # Mandatory Policy Question tracked SEPARATELY per engineering_handoff.docx!
    safety_tax = taxonomy.get("home_country_safety")
    policy_pred = InterviewPrediction(
        case_id=client.case_id,
        theme_id="home_country_safety",
        question_text=safety_tax.sample_question if safety_tax else "Do you feel safe returning to Jamaica / have you experienced harm?",
        question_type="policy_mandatory",
        rank=1,
        confidence=1.0,
        rationale="Universal policy-driven Kingston consular question — tracked separately from profile ranking to avoid inflating predictive metrics.",
        author=author,
    )
    db.add(policy_pred)
    created.append(policy_pred)
    db.commit()
    return created
