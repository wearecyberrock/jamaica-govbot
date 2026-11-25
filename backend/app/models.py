"""Database ORM models aligned with the JAHTARIA Visa Intelligence Engineering Schema."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="customer")  # ceo | staff | customer
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    linked_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClientCase(Base):
    """Core client & U.S. visa case record (supports pseudonymized + active full profiles)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    access_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    pseudonym: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    nationality: Mapped[str] = mapped_column(String(128), default="Jamaica")
    parish: Mapped[str] = mapped_column(String(128), default="")
    visa_class: Mapped[str] = mapped_column(String(64), default="B1/B2")
    pipeline_stage: Mapped[str] = mapped_column(String(64), default="new_intake")
    # new_intake | data_synced | risk_audit | questionnaire | review_approval | docs_ready | embassy_scheduled | completed
    standing_score: Mapped[int] = mapped_column(Integer, default=50)
    denial_risk_level: Mapped[str] = mapped_column(String(32), default="medium")  # low | medium | high | critical
    outcome: Mapped[str] = mapped_column(String(64), default="pending")  # pending | approved | refused | 221g | unknown
    outcome_evidence: Mapped[str] = mapped_column(String(128), default="pending")
    refusal_statute: Mapped[str] = mapped_column(String(64), default="")

    # Encrypted PII fields
    passport_number_enc: Mapped[str] = mapped_column(Text, default="")
    dob_enc: Mapped[str] = mapped_column(Text, default="")
    ds160_confirmation_id: Mapped[str] = mapped_column(String(64), default="")
    ais_appointment_barcode: Mapped[str] = mapped_column(String(64), default="")
    passport_expiry: Mapped[str] = mapped_column(String(32), default="")
    intended_travel_date: Mapped[str] = mapped_column(String(32), default="")
    intended_return_date: Mapped[str] = mapped_column(String(32), default="")
    purpose_of_trip: Mapped[str] = mapped_column(Text, default="")
    us_destination: Mapped[str] = mapped_column(String(255), default="")
    us_host_contact: Mapped[str] = mapped_column(Text, default="")
    occupation: Mapped[str] = mapped_column(String(255), default="")
    employer_name: Mapped[str] = mapped_column(String(255), default="")
    monthly_gross_jmd: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_net_jmd: Mapped[float | None] = mapped_column(Float, nullable=True)
    marital_status: Mapped[str] = mapped_column(String(64), default="")
    children_count: Mapped[int] = mapped_column(Integer, default=0)
    prior_us_refusals: Mapped[int] = mapped_column(Integer, default=0)
    has_us_relatives: Mapped[bool] = mapped_column(Boolean, default=False)
    us_relatives_details: Mapped[str] = mapped_column(Text, default="")
    travel_history_summary: Mapped[str] = mapped_column(Text, default="")

    # Engineering package metadata
    profile_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    predicted_themes_json: Mapped[str] = mapped_column(Text, default="[]")
    reported_actual_themes_json: Mapped[str] = mapped_column(Text, default="[]")
    predictions_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    predictions_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    predictions_frozen_by: Mapped[str] = mapped_column(String(128), default="")
    data_quality: Mapped[str] = mapped_column(String(128), default="intake_pending")
    open_verification_items: Mapped[str] = mapped_column(Text, default="")
    consent_status: Mapped[str] = mapped_column(String(64), default="not_documented")
    training_eligibility: Mapped[str] = mapped_column(String(64), default="review_required")
    service_package_usd: Mapped[float] = mapped_column(Float, default=250.0)
    embassy_interview_date: Mapped[str] = mapped_column(String(32), default="")
    assigned_staff: Mapped[str] = mapped_column(String(128), default="Staff Specialist")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    facts: Mapped[list["ProfileFact"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    predictions: Mapped[list["InterviewPrediction"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    interview_events: Mapped[list["InterviewEvent"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    risk_flags: Mapped[list["RiskFlag"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    journal_entries: Mapped[list["PipelineJournal"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    assets: Mapped[list["GeneratedAsset"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    documents: Mapped[list["ClientDocument"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class ProfileFact(Base):
    """Provenance-tracked client facts (DS-160 draft vs submitted vs screening vs document)."""

    __tablename__ = "profile_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True)
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[str] = mapped_column(String(32), default="")
    evidence_source: Mapped[str] = mapped_column(String(128), default="client_intake")
    confidence: Mapped[str] = mapped_column(String(32), default="medium")
    conflict_status: Mapped[str] = mapped_column(String(64), default="verified")  # verified | conflict | needs_review
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase"] = relationship(back_populates="facts")


class QuestionTaxonomy(Base):
    __tablename__ = "question_taxonomy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    sample_question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_or_profile_specific: Mapped[str] = mapped_column(String(64), nullable=False)


class InterviewPrediction(Base):
    """Pre-interview ranked predictions frozen with author + timestamp."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True)
    theme_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), default="profile_driven")  # profile_driven | policy_mandatory
    rank: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.75)
    rationale: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(128), default="system_rules")
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase"] = relationship(back_populates="predictions")


class InterviewEvent(Base):
    """Mock interview practice events & client-reported embassy events."""

    __tablename__ = "interview_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True)
    event_mode: Mapped[str] = mapped_column(String(32), default="embassy_reported")  # embassy_reported | mock_practice
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    theme: Mapped[str] = mapped_column(String(128), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    client_answer: Mapped[str] = mapped_column(Text, default="")
    discrepancy_type: Mapped[str] = mapped_column(String(128), default="")
    verified_resolution: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(64), default="user_recollection")
    pre_interview_predicted_theme: Mapped[bool] = mapped_column(Boolean, default=False)
    prediction_classification: Mapped[str] = mapped_column(String(64), default="unclassified")
    exact_wording_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase"] = relationship(back_populates="interview_events")


class RiskFlag(Base):
    """Deterministic & AI-detected Good Standing checks, contradictions, and follow-up questions."""

    __tablename__ = "risk_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # red | amber | green
    category: Mapped[str] = mapped_column(String(64), default="compliance")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_fix: Mapped[str] = mapped_column(Text, default="")
    follow_up_question: Mapped[str] = mapped_column(Text, default="")
    client_response: Mapped[str] = mapped_column(Text, default="")
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    source_citation: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    score_impact: Mapped[int] = mapped_column(Integer, default=0)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase"] = relationship(back_populates="risk_flags")


class PipelineJournal(Base):
    """Chronological timeline of all agent tool calls, staff actions, syncs, and approvals."""

    __tablename__ = "pipeline_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase"] = relationship(back_populates="journal_entries")


class GovSource(Base):
    """Official U.S. & Jamaican government web sources with live scrape status, hash & diff."""

    __tablename__ = "gov_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agency: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # us_embassy | us_dos | jamaica_passport | jamaica_civil | fees
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    verified_summary: Mapped[str] = mapped_column(Text, default="")
    scraped_excerpt: Mapped[str] = mapped_column(Text, default="")
    key_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    content_hash: Mapped[str] = mapped_column(String(128), default="")
    previous_hash: Mapped[str] = mapped_column(String(128), default="")
    diff_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    diff_summary: Mapped[str] = mapped_column(Text, default="")
    scrape_status: Mapped[str] = mapped_column(String(64), default="verified_seed")
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class OfficialDocument(Base):
    """Official downloaded government PDFs & editable agency blueprints visible directly in UI."""

    __tablename__ = "official_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    agency: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # official_pdf | agency_blueprint | instruction_sheet
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), default=".pdf")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(128), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    detected_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    is_blueprint: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceManifestItem(Base):
    """83 inventoried restricted original files from JAHTARIA_Visa_Intelligence_Engineer_Package."""

    __tablename__ = "source_manifest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(128), default="")
    extractable_characters: Mapped[int] = mapped_column(Integer, default=0)
    extraction_status: Mapped[str] = mapped_column(String(64), default="")
    handling: Mapped[str] = mapped_column(String(128), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class GeneratedAsset(Base):
    """Auto-filled client PDFs, DOCX packets, questionnaires, and visual roadmap cards with approval gate."""

    __tablename__ = "generated_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)  # ds160_worksheet_pdf | checklist_pdf | cover_letter_docx | visual_roadmap_png | pica_prep_pdf | questionnaire_docx
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    filled_fields_json: Mapped[str] = mapped_column(Text, default="{}")
    approval_status: Mapped[str] = mapped_column(String(32), default="pending_approval")  # pending_approval | approved | rejected
    approved_by: Mapped[str] = mapped_column(String(128), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visible_to_client: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase"] = relationship(back_populates="assets")


class ClientDocument(Base):
    """Per-client categorized Document & Image Vault with OCR extraction & version history."""

    __tablename__ = "client_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("clients.case_id", ondelete="CASCADE"), index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="photos_other")  # passport_id | financial_payslips | rgd_civil | embassy_forms | photos_other
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(128), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extracted_fields_json: Mapped[str] = mapped_column(Text, default="{}")
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    parent_doc_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    visible_to_client: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[str] = mapped_column(String(128), default="Staff")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped["ClientCase | None"] = relationship(back_populates="documents")


class AppSetting(Base):
    """Encrypted key-value store for AI providers, subscriptions, Composio, Company DB, MCP servers."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_enc: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(64), default="general")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BrandingConfig(Base):
    """White-label agency configuration editable by CEO for commercial resale."""

    __tablename__ = "branding_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_name: Mapped[str] = mapped_column(String(255), default="Jahtaria Travel Services")
    tagline: Mapped[str] = mapped_column(String(255), default="U.S. Visa Preparation & Consular Intelligence")
    logo_url: Mapped[str] = mapped_column(String(512), default="/jahtaria-logo.png")
    primary_color: Mapped[str] = mapped_column(String(32), default="#1a472a")
    gold_color: Mapped[str] = mapped_column(String(32), default="#d4a234")
    navy_color: Mapped[str] = mapped_column(String(32), default="#0b3c68")
    accent_red: Mapped[str] = mapped_column(String(32), default="#ce1126")
    contact_email: Mapped[str] = mapped_column(String(255), default="support@jahtariatravel.com")
    whatsapp_number: Mapped[str] = mapped_column(String(64), default="+1 (876) 555-0192")
    website_url: Mapped[str] = mapped_column(String(512), default="https://jahtariatravelservices.poweredbycyberrock.workers.dev/")
    compliance_notice: Mapped[str] = mapped_column(
        Text,
        default="Truthful application verification & interview readiness only. We never guarantee visa approval or coach concealment.",
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChatMessage(Base):
    """Persisted customer portal Q&A and staff Hermes agent sessions."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    user_role: Mapped[str] = mapped_column(String(32), default="customer")
    sender: Mapped[str] = mapped_column(String(32), nullable=False)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_trace_json: Mapped[str] = mapped_column(Text, default="[]")
    provider_used: Mapped[str] = mapped_column(String(64), default="consular-engine")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    """Saved multi-conversation threads displayed in the left sidebar."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New Conversation")
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PendingAction(Base):
    """CEO & Staff conversational edit proposals with 1-click Confirm & Undo audit trail."""

    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)  # update_client | update_branding | create_staff | update_obsidian | regenerate_doc
    target_ref: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | applied | undone | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

