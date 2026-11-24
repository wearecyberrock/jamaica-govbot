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

    raise ValueError(f"Unknown MCP tool: {name}")
