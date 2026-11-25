"""End-to-end backend API tests for Jahtaria Visa Intelligence & Document Automation (Single-CEO + Agent-First)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Run against an isolated temp SQLite database so local desktop data is untouched
_TMP_DIR = tempfile.mkdtemp(prefix="jahtaria_test_")
os.environ["DATA_DIR"] = _TMP_DIR
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR, 'test.db').as_posix()}"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app


def test_full_backend_workflow():
    with TestClient(app) as client:
        # 1. Health, Branding & Initial Setup Status (no CEO yet!)
        assert client.get("/health").status_code == 200
        assert "Jahtaria" in client.get("/api/branding").json()["agency_name"]
        st = client.get("/api/auth/setup-status").json()
        assert st["ceo_exists"] is False

        # 2. First-run CEO creation succeeds
        ceo_res = client.post(
            "/api/auth/setup-ceo",
            json={
                "full_name": "Agency Director",
                "email": "director@jahtariatravel.com",
                "password": "StrongPassword2026!",
                "agency_name": "Jahtaria Travel Services",
            },
        )
        assert ceo_res.status_code == 200, ceo_res.text
        ceo_h = {"Authorization": f"Bearer {ceo_res.json()['access_token']}"}

        # 3. Second CEO creation MUST be blocked (strictly 1 CEO allowed!)
        ceo2 = client.post(
            "/api/auth/setup-ceo",
            json={
                "full_name": "Second CEO",
                "email": "second@jahtariatravel.com",
                "password": "AnotherPassword2026!",
            },
        )
        assert ceo2.status_code == 403

        # 4. CEO creates a Staff account (cannot create a second CEO via /users)
        bad_ceo = client.post(
            "/api/auth/users",
            headers=ceo_h,
            json={"full_name": "Fake CEO", "email": "fake@jahtaria.com", "password": "Password123!", "role": "ceo"},
        )
        assert bad_ceo.status_code == 400

        staff_create = client.post(
            "/api/auth/users",
            headers=ceo_h,
            json={"full_name": "Nadine Specialist", "email": "staff@jahtariatravel.com", "password": "StaffPassword2026!", "role": "staff"},
        )
        assert staff_create.status_code == 200
        staff_login = client.post("/api/auth/login", json={"email": "staff@jahtariatravel.com", "password": "StaffPassword2026!"})
        assert staff_login.status_code == 200
        staff_h = {"Authorization": f"Bearer {staff_login.json()['access_token']}"}

        # 5. Client self-registers an account (and Case Code login works)
        cust_signup = client.post(
            "/api/auth/signup",
            json={
                "full_name": "Andre Williams",
                "email": "andre@example.com",
                "password": "ClientPassword2026!",
                "parish": "St. Andrew",
                "visa_class": "B1/B2",
            },
        )
        assert cust_signup.status_code == 200
        cust_h = {"Authorization": f"Bearer {cust_signup.json()['access_token']}"}
        assert client.post("/api/auth/case-code", json={"access_code": "JAH-C034"}).status_code == 200

        # 6. Role isolation: Customer cannot list staff cases or CEO overview
        assert client.get("/api/clients", headers=cust_h).status_code == 403
        assert client.get("/api/ceo/overview", headers=staff_h).status_code == 403

        # 7. Unified Agent-First Command Endpoint (CEO -> Graphs, Staff -> Client Audit + Visual Roadmap, Customer -> Q&A)
        cmd_ceo = client.post(
            "/api/agent/command",
            headers=ceo_h,
            json={"message": "Show CEO analytics and graphs", "mode": "chat"},
        )
        assert cmd_ceo.status_code == 200
        assert cmd_ceo.json()["ui_panel"]["panel"] == "ceo_analytics"

        cmd_pdf = client.post(
            "/api/agent/command",
            headers=staff_h,
            json={"message": "Open PICA adult passport renewal PDF", "mode": "chat"},
        )
        assert cmd_pdf.status_code == 200
        assert cmd_pdf.json()["ui_panel"]["panel"] == "official_pdfs"
        assert cmd_pdf.json()["ui_panel"]["doc_key"] == "pica_adult_renewal_simplified"

        cmd_task = client.post(
            "/api/agent/command",
            headers=staff_h,
            json={"message": "Audit C034 and generate visual roadmap png", "mode": "task"},
        )
        assert cmd_task.status_code == 200
        assert len(cmd_task.json()["tool_trace"]) >= 2
        assert len(cmd_task.json()["created_assets"]) >= 1

        cmd_cust = client.post(
            "/api/agent/command",
            headers=cust_h,
            json={"message": "What is the April 2025 DS-160 barcode rule and MRV fee?"},
        )
        assert cmd_cust.status_code == 200
        assert "$185" in cmd_cust.json()["reply"] or "AA" in cmd_cust.json()["reply"]

        # 8. Grouped Model Catalog, Voice Config, Dynamic Questionnaire, Conversations & CEO Confirm/Undo Edit
        cat = client.get("/api/models/catalog", headers=ceo_h)
        assert cat.status_code == 200
        assert "Hermes" not in cat.text
        assert any(i["provider"] == "openai-codex" for i in cat.json()["groups"][0]["items"])

        vc = client.get("/api/voice/config", headers=cust_h)
        assert vc.status_code == 200
        assert vc.json()["engine"] == "edge"

        dq = client.post("/api/clients/C034/questionnaire/generate", headers=staff_h, json={"focus": "ties"})
        assert dq.status_code == 200
        assert len(dq.json()["questions_added"]) >= 1

        # CEO conversational edit -> Confirm -> Undo
        edit_cmd = client.post(
            "/api/agent/command",
            headers=ceo_h,
            json={"message": "Update C034 gross salary to 325000", "mode": "chat"},
        )
        assert edit_cmd.status_code == 200
        pa = edit_cmd.json()["pending_action"]
        assert pa is not None and pa["status"] == "pending"

        conf = client.post(f"/api/actions/{pa['id']}/confirm", headers=ceo_h)
        assert conf.status_code == 200 and conf.json()["status"] == "applied"
        assert client.get("/api/clients/C034", headers=ceo_h).json()["monthly_gross_jmd"] == 325000.0

        undo = client.post(f"/api/actions/{pa['id']}/undo", headers=ceo_h)
        assert undo.status_code == 200 and undo.json()["status"] == "undone"
        assert client.get("/api/clients/C034", headers=ceo_h).json()["monthly_gross_jmd"] == 285000.0

        convs = client.get("/api/conversations", headers=ceo_h)
        assert convs.status_code == 200 and len(convs.json()) >= 1

        # 9. Inbound /mcp endpoint works
        mcp_list = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert mcp_list.status_code == 200
        assert any(t["name"] == "jahtaria_audit_client" for t in mcp_list.json()["result"]["tools"])
