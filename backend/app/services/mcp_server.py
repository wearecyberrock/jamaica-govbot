"""Built-in Inbound MCP Server (/mcp) — JSON-RPC 2.0 Streamable HTTP endpoint.

Allows Claude Desktop, ChatGPT Connectors, Antigravity, and Assimilis to call
Jahtaria Visa Intelligence tools directly using the owner's existing subscriptions!
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import ClientCase, GovSource, OfficialDocument
from app.services.doc_generator import generate_ds160_worksheet_pdf
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions

MCP_TOOLS = [
    {
        "name": "jahtaria_list_clients",
        "description": "List U.S. visa preparation client cases with pipeline stage, Good Standing score, and denial risk level.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "Optional pipeline stage filter"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "jahtaria_audit_client",
        "description": "Run the deterministic U.S. Embassy Kingston Good Standing & Denial Risk audit for a case_id (e.g. C001).",
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "jahtaria_predict_interview",
        "description": "Generate ranked profile-driven interview predictions + separate mandatory policy questions for a case_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "jahtaria_search_gov_sources",
        "description": "Search official scraped U.S. Embassy Kingston, Dept. of State, PICA Jamaica, and RGD rules & reference links.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "jahtaria_list_official_pdfs",
        "description": "List all official downloaded Jamaican passport (PICA), RGD, and U.S. visa (DS-157, DS-5535, DS-156E) PDFs and blueprints.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "jahtaria_draft_ds160_worksheet",
        "description": "Generate a draft DS-160 Preparation Worksheet PDF for a case_id (queued for staff human approval).",
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "jahtaria_query_clients_table",
        "description": "Query, filter, and sort the client spreadsheet by stage, visa_class, parish, risk, outcome, standing range, or sort field.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "stage": {"type": "string"},
                "visa_class": {"type": "string"},
                "parish": {"type": "string"},
                "risk": {"type": "string", "description": "low | medium | high | critical"},
                "outcome": {"type": "string"},
                "min_standing": {"type": "integer"},
                "max_standing": {"type": "integer"},
                "sort_by": {"type": "string", "default": "standing_score"},
                "sort_dir": {"type": "string", "default": "desc"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "jahtaria_create_client",
        "description": "Create a new U.S. visa client case in the Jahtaria spreadsheet/database and run initial Good Standing audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string"},
                "visa_class": {"type": "string", "default": "B1/B2"},
                "parish": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "occupation": {"type": "string"},
                "employer_name": {"type": "string"},
                "monthly_gross_jmd": {"type": "number"},
                "monthly_net_jmd": {"type": "number"},
                "us_destination": {"type": "string"},
                "purpose_of_trip": {"type": "string"},
            },
            "required": ["full_name"],
        },
    },
    {
        "name": "jahtaria_update_client",
        "description": "Update any fields on an existing client case (e.g. gross/net JMD salary, passport_expiry, ds160_confirmation_id, employer_name, stage) and re-audit Good Standing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["case_id", "fields"],
        },
    },
    {
        "name": "jahtaria_list_client_documents",
        "description": "List all uploaded documents, images, and OCR-extracted fields inside a client's Document Vault.",
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "jahtaria_fill_official_pdf",
        "description": "Auto-fill an official government PDF (e.g. pica_adult_renewal_simplified, us_dos_ds5535, rgd_birth_cert_birreq) with a client's profile into their Document Vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "doc_key": {"type": "string"},
            },
            "required": ["case_id", "doc_key"],
        },
    },
]


def handle_mcp_jsonrpc(db: Session, body: dict[str, Any]) -> dict[str, Any]:
    req_id = body.get("id", 1)
    method = body.get("method", "")
    params = body.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "serverInfo": {"name": "jahtaria-jamaica-govbot", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            result_data = _execute_tool(db, tool_name, args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result_data, indent=2, default=str)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error executing {tool_name}: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _execute_tool(db: Session, name: str, args: dict[str, Any]) -> Any:
    if name == "jahtaria_list_clients":
        q = db.query(ClientCase)
        if args.get("stage"):
            q = q.filter(ClientCase.pipeline_stage == args["stage"])
        rows = q.order_by(ClientCase.updated_at.desc()).limit(int(args.get("limit", 20))).all()
        return [
            {
                "case_id": c.case_id,
                "name": c.full_name or c.pseudonym,
                "visa_class": c.visa_class,
                "stage": c.pipeline_stage,
                "standing_score": c.standing_score,
                "denial_risk_level": c.denial_risk_level,
                "outcome": c.outcome,
            }
            for c in rows
        ]

    if name == "jahtaria_audit_client":
        case_id = str(args.get("case_id", "")).upper()
        client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first()
        if not client:
            raise ValueError(f"Case {case_id} not found.")
        return evaluate_client_standing(db, client)

    if name == "jahtaria_predict_interview":
        case_id = str(args.get("case_id", "")).upper()
        client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first()
        if not client:
            raise ValueError(f"Case {case_id} not found.")
        preds = generate_ranked_predictions(db, client, author="mcp_client")
        return [
            {
                "rank": p.rank,
                "type": p.question_type,
                "theme": p.theme_id,
                "question": p.question_text,
                "confidence": p.confidence,
                "rationale": p.rationale,
            }
            for p in preds
        ]

    if name == "jahtaria_search_gov_sources":
        query = str(args.get("query", "")).lower()
        sources = db.query(GovSource).all()
        matches = []
        for s in sources:
            haystack = f"{s.name} {s.agency} {s.verified_summary} {s.scraped_excerpt} {s.key_rules_json}".lower()
            if not query or any(tok in haystack for tok in query.split()):
                matches.append(
                    {
                        "source_key": s.source_key,
                        "name": s.name,
                        "agency": s.agency,
                        "url": s.url,
                        "verified_summary": s.verified_summary,
                        "scrape_status": s.scrape_status,
                    }
                )
        return matches

    if name == "jahtaria_list_official_pdfs":
        docs = db.query(OfficialDocument).all()
        return [
            {
                "doc_key": d.doc_key,
                "title": d.title,
                "agency": d.agency,
                "filename": d.filename,
                "source_url": d.source_url,
                "size_bytes": d.size_bytes,
            }
            for d in docs
        ]

    if name == "jahtaria_draft_ds160_worksheet":
        case_id = str(args.get("case_id", "")).upper()
        client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first()
        if not client:
            raise ValueError(f"Case {case_id} not found.")
        path, _ = generate_ds160_worksheet_pdf(client, client.risk_flags)
        return {"status": "draft_created_pending_approval", "filename": path.name, "case_id": case_id}

    if name == "jahtaria_query_clients_table":
        from app.services.smart_paste import query_clients_structured

        return query_clients_structured(
            db,
            search=str(args.get("search") or ""),
            stage=str(args.get("stage") or ""),
            visa_class=str(args.get("visa_class") or ""),
            parish=str(args.get("parish") or ""),
            risk=str(args.get("risk") or ""),
            outcome=str(args.get("outcome") or ""),
            min_standing=args.get("min_standing"),
            max_standing=args.get("max_standing"),
            sort_by=str(args.get("sort_by") or "standing_score"),
            sort_dir=str(args.get("sort_dir") or "desc"),
            limit=int(args.get("limit") or 50),
        )

    if name == "jahtaria_create_client":
        import secrets
        from app.services.obsidian import sync_client_to_obsidian

        full_name = str(args.get("full_name") or "").strip()
        if not full_name:
            raise ValueError("full_name is required.")
        count = db.query(ClientCase).count()
        cid = f"C{count + 1:03d}"
        while db.query(ClientCase).filter(ClientCase.case_id == cid).first():
            count += 1
            cid = f"C{count + 1:03d}"
        client = ClientCase(
            case_id=cid,
            access_code=f"JAH-{cid}-{secrets.token_hex(2).upper()}",
            pseudonym=full_name,
            full_name=full_name,
            visa_class=str(args.get("visa_class") or "B1/B2"),
            parish=str(args.get("parish") or "Kingston & St. Andrew"),
            email=str(args.get("email") or ""),
            phone=str(args.get("phone") or ""),
            occupation=str(args.get("occupation") or ""),
            employer_name=str(args.get("employer_name") or ""),
            monthly_gross_jmd=args.get("monthly_gross_jmd"),
            monthly_net_jmd=args.get("monthly_net_jmd"),
            us_destination=str(args.get("us_destination") or ""),
            purpose_of_trip=str(args.get("purpose_of_trip") or ""),
            pipeline_stage="new_intake",
        )
        db.add(client)
        db.commit()
        audit = evaluate_client_standing(db, client)
        sync_client_to_obsidian(client, client.risk_flags, client.journal_entries)
        return {"case_id": cid, "full_name": full_name, "standing_score": audit["standing_score"]}

    if name == "jahtaria_update_client":
        from app.config import encrypt_value
        from app.services.obsidian import sync_client_to_obsidian

        case_id = str(args.get("case_id", "")).upper()
        client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first()
        if not client:
            raise ValueError(f"Case {case_id} not found.")
        fields = args.get("fields") or {}
        for k, v in fields.items():
            if k == "passport_number":
                client.passport_number_enc = encrypt_value(str(v))
            elif k == "dob":
                client.dob_enc = encrypt_value(str(v))
            elif hasattr(client, k):
                setattr(client, k, v)
        db.commit()
        audit = evaluate_client_standing(db, client)
        sync_client_to_obsidian(client, client.risk_flags, client.journal_entries)
        return {"case_id": case_id, "updated_fields": list(fields.keys()), "standing_score": audit["standing_score"]}

    if name == "jahtaria_list_client_documents":
        from app.models import ClientDocument

        case_id = str(args.get("case_id", "")).upper()
        docs = db.query(ClientDocument).filter(ClientDocument.case_id == case_id).order_by(ClientDocument.id.desc()).all()
        return [
            {
                "id": d.id,
                "category": d.category,
                "title": d.title,
                "filename": d.filename,
                "version": d.version_number,
                "ai_summary": d.ai_summary,
                "extracted_fields": json.loads(d.extracted_fields_json or "{}"),
            }
            for d in docs
        ]

    if name == "jahtaria_fill_official_pdf":
        from pathlib import Path
        from app.config import CLIENT_VAULT_DIR
        from app.models import ClientDocument
        from app.services.doc_generator import sha256_file
        from app.services.doc_intelligence import ai_autofill_official_pdf, get_pdf_page_count

        case_id = str(args.get("case_id", "")).upper()
        doc_key = str(args.get("doc_key", "")).strip()
        client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first()
        official = db.query(OfficialDocument).filter(OfficialDocument.doc_key == doc_key).first()
        if not client or not official:
            raise ValueError("Case or official document not found.")
        out_path, fields = ai_autofill_official_pdf(Path(official.file_path), client, CLIENT_VAULT_DIR / case_id)
        doc = ClientDocument(
            case_id=case_id,
            category="embassy_forms",
            title=f"Auto-Filled: {official.title}",
            filename=out_path.name,
            file_path=str(out_path),
            mime_type="application/pdf" if out_path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=out_path.stat().st_size,
            sha256=sha256_file(out_path),
            page_count=get_pdf_page_count(out_path),
            extracted_fields_json=json.dumps(fields),
            ai_summary=f"Auto-filled via MCP from {case_id}'s profile.",
            uploaded_by="MCP Agent",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return {"document_id": doc.id, "title": doc.title, "filename": doc.filename, "case_id": case_id}

    raise ValueError(f"Unknown MCP tool: {name}")
