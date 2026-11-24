"""Database Explorer Window, Official Scraped Sources & Source Manifest Router."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import (
    ClientCase,
    GeneratedAsset,
    GovSource,
    InterviewEvent,
    InterviewPrediction,
    OfficialDocument,
    PipelineJournal,
    ProfileFact,
    QuestionTaxonomy,
    RiskFlag,
    SourceManifestItem,
    User,
)
from app.services.connectors import import_clients_from_csv
from app.services.scraper import scrape_all_sources, scrape_single_source

router = APIRouter(prefix="/api", tags=["database"])

TABLE_REGISTRY = {
    "clients": (ClientCase, ["case_id", "full_name", "visa_class", "pipeline_stage", "standing_score", "denial_risk_level", "outcome", "parish", "ds160_confirmation_id", "passport_expiry"]),
    "gov_sources": (GovSource, ["source_key", "name", "agency", "category", "url", "scrape_status", "diff_alert", "last_scraped_at"]),
    "official_documents": (OfficialDocument, ["doc_key", "title", "agency", "category", "filename", "file_format", "size_bytes", "source_url"]),
    "source_manifest": (SourceManifestItem, ["source_id", "filename", "doc_type", "file_format", "size_bytes", "extractable_characters", "extraction_status", "handling"]),
    "question_taxonomy": (QuestionTaxonomy, ["theme_id", "sample_question", "category", "policy_or_profile_specific"]),
    "interview_events": (InterviewEvent, ["case_id", "event_mode", "sequence", "theme", "question_text", "pre_interview_predicted_theme", "prediction_classification", "source_type"]),
    "predictions": (InterviewPrediction, ["case_id", "rank", "question_type", "theme_id", "question_text", "confidence", "author", "frozen_at"]),
    "risk_flags": (RiskFlag, ["case_id", "code", "severity", "category", "title", "resolved", "source_citation"]),
    "profile_facts": (ProfileFact, ["case_id", "fact_key", "value", "evidence_source", "confidence", "conflict_status"]),
    "generated_assets": (GeneratedAsset, ["case_id", "asset_type", "title", "filename", "approval_status", "approved_by", "visible_to_client"]),
    "pipeline_journal": (PipelineJournal, ["case_id", "event_type", "actor", "summary", "created_at"]),
}


class CsvImportRequest(BaseModel):
    csv_text: str


class CreateSourceRequest(BaseModel):
    name: str
    agency: str
    category: str = "us_embassy"
    url: str
    verified_summary: str = ""


class ScrapeRequest(BaseModel):
    use_browser_fallback: bool = False


@router.get("/database/tables")
def list_database_tables(
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    summary = []
    for table_name, (model_cls, cols) in TABLE_REGISTRY.items():
        summary.append({"table": table_name, "count": db.query(model_cls).count(), "columns": cols})
    return summary


@router.get("/database/tables/{table_name}")
def browse_database_table(
    table_name: str,
    search: str = "",
    limit: int = 100,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if table_name not in TABLE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown table '{table_name}'.")
    model_cls, cols = TABLE_REGISTRY[table_name]
    rows = db.query(model_cls).order_by(model_cls.id.desc()).limit(min(limit, 250)).all()
    q = search.strip().lower()
    records = []
    for r in rows:
        item = {"id": r.id}
        for c in cols:
            val = getattr(r, c, None)
            if isinstance(val, datetime):
                val = val.isoformat()
            item[c] = val
        if q and not any(q in str(v).lower() for v in item.values()):
            continue
        records.append(item)
    return {"table": table_name, "columns": cols, "total_in_table": db.query(model_cls).count(), "rows": records}


@router.post("/database/import-csv")
def import_csv_rows(
    req: CsvImportRequest,
    user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return import_clients_from_csv(db, req.csv_text, actor=user.full_name)


@router.get("/sources")
def list_gov_sources(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = db.query(GovSource).order_by(GovSource.id).all()
    out = []
    for s in rows:
        rules = []
        try:
            rules = json.loads(s.key_rules_json or "[]")
        except Exception:
            pass
        out.append(
            {
                "id": s.id,
                "source_key": s.source_key,
                "name": s.name,
                "agency": s.agency,
                "category": s.category,
                "url": s.url,
                "verified_summary": s.verified_summary,
                "scraped_excerpt": s.scraped_excerpt,
                "key_rules": rules,
                "content_hash": (s.content_hash or "")[:16],
                "diff_alert": s.diff_alert,
                "diff_summary": s.diff_summary,
                "scrape_status": s.scrape_status,
                "last_scraped_at": s.last_scraped_at.isoformat() if s.last_scraped_at else None,
                "enabled": s.enabled,
            }
        )
    return out


@router.post("/sources")
def add_gov_source(
    req: CreateSourceRequest,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    key = re.sub(r"[^a-z0-9_]+", "_", req.name.lower()).strip("_")[:60]
    if db.query(GovSource).filter(GovSource.source_key == key).first():
        key = f"{key}_{int(datetime.now(timezone.utc).timestamp())}"
    src = GovSource(
        source_key=key,
        name=req.name.strip(),
        agency=req.agency.strip(),
        category=req.category.strip(),
        url=req.url.strip(),
        verified_summary=req.verified_summary.strip() or f"Custom official source added for {req.agency}.",
        content_hash=hashlib.sha256(req.url.encode("utf-8")).hexdigest(),
        scrape_status="pending_scrape",
    )
    db.add(src)
    db.commit()
    res = scrape_single_source(db, src)
    return {"source_key": src.source_key, "scrape_result": res}


@router.post("/sources/{source_key}/scrape")
def refresh_single_source(
    source_key: str,
    req: ScrapeRequest = ScrapeRequest(),
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    src = db.query(GovSource).filter(GovSource.source_key == source_key).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")
    return scrape_single_source(db, src, use_browser_fallback=req.use_browser_fallback)


@router.post("/sources/scrape-all")
def refresh_all_sources(
    req: ScrapeRequest = ScrapeRequest(),
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    results = scrape_all_sources(db, use_browser_fallback=req.use_browser_fallback)
    return {"total_checked": len(results), "changed_count": sum(1 for r in results if r.get("changed")), "results": results}


@router.post("/sources/{source_key}/acknowledge-diff")
def acknowledge_source_diff(
    source_key: str,
    _user: User = Depends(require_roles("staff", "ceo")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    src = db.query(GovSource).filter(GovSource.source_key == source_key).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")
    src.diff_alert = False
    src.diff_summary = ""
    db.commit()
    return {"source_key": source_key, "diff_alert": False}
