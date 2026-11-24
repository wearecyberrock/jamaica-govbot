"""End-to-end backend API tests for Jahtaria Visa Intelligence & Document Automation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import SEED_CEO_EMAIL, SEED_CEO_PASSWORD, SEED_CLIENT_EMAIL, SEED_CLIENT_PASSWORD, SEED_STAFF_EMAIL, SEED_STAFF_PASSWORD
from app.main import app


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_full_backend_workflow():
    with TestClient(app) as client:
        # 1. Health & Public Branding
        r = client.get("/health")
        assert r.status_code == 200
        b = client.get("/api/branding")
        assert b.status_code == 200
        assert "Jahtaria" in b.json()["agency_name"]

        # 2. Role Logins (CEO, Staff, Customer + Case Code)
        ceo_h = _login(client, SEED_CEO_EMAIL, SEED_CEO_PASSWORD)
        staff_h = _login(client, SEED_STAFF_EMAIL, SEED_STAFF_PASSWORD)
        cust_h = _login(client, SEED_CLIENT_EMAIL, SEED_CLIENT_PASSWORD)

        code_r = client.post("/api/auth/case-code", json={"access_code": "JAH-C034"})
        assert code_r.status_code == 200
        assert code_r.json()["case_id"] == "C034"

        # 3. Verify all 33 seeded cases + C034 exist and Staff can list them
        cases = client.get("/api/clients", headers=staff_h)
        assert cases.status_code == 200
        assert len(cases.json()) >= 34

        # Verify Customer cannot access Staff endpoints
        forbidden = client.get("/api/clients", headers=cust_h)
        assert forbidden.status_code == 403

        # 4. Verify C005 barcode mismatch Red Blocker detected cleanly
        c5 = client.get("/api/clients/C005", headers=staff_h)
        assert c5.status_code == 200
        c5_flags = [f["code"] for f in c5.json()["risk_flags"]]
        assert "DS160_AIS_MISMATCH" in c5_flags

        # 5. Customer Portal Own Case & Q&A Chat
        my_case = client.get("/api/portal/my-case", headers=cust_h)
        assert my_case.status_code == 200
        assert my_case.json()["case_id"] == "C034"
        assert len(my_case.json()["assets"]) >= 3  # Approved PDFs & visual roadmap!

        chat = client.post(
            "/api/agent/customer-chat",
            headers=cust_h,
            json={"message": "What is the April 2025 DS-160 barcode rule and MRV fee at Kingston Embassy?"},
        )
        assert chat.status_code == 200
        assert "$185" in chat.json()["reply"] or "AA" in chat.json()["reply"]

        # 6. Official Documents & Inline PDF Viewer
        docs = client.get("/api/documents/official", headers=staff_h)
        assert docs.status_code == 200
        doc_list = docs.json()
        assert len(doc_list) >= 10
        pdf_doc = next(d for d in doc_list if d["file_format"] == ".pdf")
        pdf_resp = client.get(pdf_doc["view_url"])
        assert pdf_resp.status_code == 200
        assert pdf_resp.content[:4] == b"%PDF"

        # 7. Database Explorer & Official Gov Sources
        tables = client.get("/api/database/tables", headers=staff_h)
        assert tables.status_code == 200
        tmap = {t["table"]: t["count"] for t in tables.json()}
        assert tmap["source_manifest"] == 83
        assert tmap["question_taxonomy"] >= 19
        assert tmap["gov_sources"] >= 12

        sources = client.get("/api/sources", headers=staff_h)
        assert sources.status_code == 200
        assert any("pica.gov.jm" in s["url"] for s in sources.json())

        # 8. Generate Draft Asset + Human Approval Gate (PDF, DOCX, Visual Roadmap PNG)
        gen_png = client.post(
            "/api/clients/C034/assets/generate",
            headers=staff_h,
            json={"asset_type": "visual_roadmap_png"},
        )
        assert gen_png.status_code == 200
        asset_id = gen_png.json()["id"]
        assert gen_png.json()["approval_status"] == "pending_approval"

        approve = client.post(
            f"/api/assets/{asset_id}/approve",
            headers=staff_h,
            json={"decision": "approved", "visible_to_client": True},
        )
        assert approve.status_code == 200
        assert approve.json()["approval_status"] == "approved"

        png_file = client.get(f"/api/assets/{asset_id}/file")
        assert png_file.status_code == 200
        assert png_file.content[:4] == b"\x89PNG"

        # 9. Staff Autonomous Hermes Loop ("Hands")
        hermes = client.post(
            "/api/agent/staff-run",
            headers=staff_h,
            json={"case_id": "C034", "instruction": "Audit C034, check official PICA PDFs, and sync Obsidian dossier"},
        )
        assert hermes.status_code == 200
        tools_ran = [t["tool"] for t in hermes.json()["tool_trace"]]
        assert "run_good_standing_audit" in tools_ran
        assert "sync_obsidian_dossier" in tools_ran

        # 10. Obsidian Vault Read/Write & Backlinks
        vault = client.get("/api/obsidian/notes", headers=staff_h)
        assert vault.status_code == 200
        assert any(n["path"] == "Index.md" for n in vault.json()["notes"])
        note = client.get("/api/obsidian/note", params={"path": "Gov-Rules/US-Embassy-Kingston-Rules.md"}, headers=staff_h)
        assert note.status_code == 200
        assert "142 Old Hope Road" in note.json()["content"]

        # 11. CEO Executive Overview & Prediction Evaluation
        ceo_ov = client.get("/api/ceo/overview", headers=ceo_h)
        assert ceo_ov.status_code == 200
        assert ceo_ov.json()["kpis"]["total_cases"] >= 34
        assert ceo_ov.json()["prediction_evaluation"]["policy_questions_tracked_separately"] >= 1

        # 12. Inbound /mcp JSON-RPC Server
        mcp_list = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert mcp_list.status_code == 200
        tool_names = [t["name"] for t in mcp_list.json()["result"]["tools"]]
        assert "jahtaria_audit_client" in tool_names

        mcp_call = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "jahtaria_audit_client", "arguments": {"case_id": "C005"}},
            },
        )
        assert mcp_call.status_code == 200
        assert "DS160_AIS_MISMATCH" in mcp_call.json()["result"]["content"][0]["text"]
