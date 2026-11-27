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
for _env_key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "OPENROUTER_API_KEY",
    "QWEN_API_KEY",
    "MINIMAX_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
):
    os.environ.pop(_env_key, None)

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

        dq = client.post("/api/clients/C034/questionnaire/generate", headers=staff_h, json={"focus": "ties", "count": 25})
        assert dq.status_code == 200
        assert len(dq.json()["questions_added"]) == 25
        assert len(dq.json()["questionnaire"]["items"]) >= 25
        assert len(dq.json()["questionnaire"]["items"][0]["options"]) >= 2
        q_get = client.get("/api/clients/C034/questionnaire", headers=staff_h)
        assert q_get.status_code == 200 and q_get.json()["total_count"] >= 25

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

        # 9. Inbound /mcp endpoint works (all 11 v2.1.0 tools!)
        mcp_list = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert mcp_list.status_code == 200
        tool_names = {t["name"] for t in mcp_list.json()["result"]["tools"]}
        assert {"jahtaria_audit_client", "jahtaria_query_clients_table", "jahtaria_create_client", "jahtaria_update_client", "jahtaria_list_client_documents", "jahtaria_fill_official_pdf"}.issubset(tool_names)

        # 10. v2.1.0 Smart Paste (API key redaction + ClawLink + MCP URL + Undo)
        fake_gem_key = "AIzaSyTestKey12345678901234567890123456"
        sp_key = client.post("/api/agent/command", headers=ceo_h, json={"message": f"use this key {fake_gem_key}"})
        assert sp_key.status_code == 200
        assert sp_key.json()["provider_used"] == "smart-paste-engine"
        assert sp_key.json()["pending_action"]["status"] == "applied"
        # Verify key was redacted from saved chat history!
        conv_msgs = client.get(f"/api/conversations/{sp_key.json()['conversation_id']}/messages", headers=ceo_h).json()
        assert all(fake_gem_key not in m["content"] for m in conv_msgs)
        # Undo key change
        assert client.post(f"/api/actions/{sp_key.json()['pending_action']['id']}/undo", headers=ceo_h).status_code == 200

        # Smart Paste Official URL -> GovSource auto-add + Undo
        sp_url = client.post("/api/agent/command", headers=ceo_h, json={"message": "https://jis.gov.jm/ add this as resource"})
        assert sp_url.status_code == 200 and sp_url.json()["provider_used"] == "smart-paste-engine"
        assert any("jis.gov.jm" in s["url"] for s in client.get("/api/sources", headers=ceo_h).json())
        assert client.post(f"/api/actions/{sp_url.json()['pending_action']['id']}/undo", headers=ceo_h).status_code == 200

        # 11. Client Vault upload + 92% RGD Converter + Document Studio Burn-In + Embassy Packet + Excel Export
        from PIL import Image
        import io as _io

        img_buf = _io.BytesIO()
        Image.new("RGB", (400, 600), "#ffffff").save(img_buf, format="PNG")
        up = client.post(
            "/api/clients/C034/documents/upload",
            headers=staff_h,
            files={"file": ("rgd_birth_cert.png", img_buf.getvalue(), "image/png")},
            data={"category": "rgd_civil", "auto_scan": "false"},
        )
        assert up.status_code == 200, up.text
        vdoc_id = up.json()["document"]["id"]

        rgd = client.post(f"/api/documents/vault/{vdoc_id}/rgd-92", headers=staff_h)
        assert rgd.status_code == 200 and rgd.json()["document"]["mime_type"] == "application/pdf"
        rgd_doc_id = rgd.json()["document"]["id"]

        # Document Studio render page + burn text annotation into new version
        rp = client.get(f"/api/documents/render-page?source_type=vault&source_id={rgd_doc_id}&page=0")
        assert rp.status_code == 200 and rp.headers["content-type"] == "image/png"

        saved = client.post(
            "/api/documents/studio/save",
            headers=staff_h,
            json={
                "source_type": "vault",
                "source_id": str(rgd_doc_id),
                "case_id": "C034",
                "annotations": [{"type": "text", "page": 0, "x": 0.2, "y": 0.2, "text": "Verified by Staff"}],
            },
        )
        assert saved.status_code == 200 and saved.json()["document"]["version_number"] >= 2

        # Embassy Packet export & Excel .xlsx export & Dynamic In-Chat Table
        pkt = client.post("/api/clients/C034/embassy-packet", headers=staff_h, json={"bundle_format": "pdf"})
        assert pkt.status_code == 200 and pkt.json()["included_count"] >= 1
        xlsx = client.get("/api/clients/export/xlsx", headers=staff_h)
        assert xlsx.status_code == 200 and len(xlsx.content) > 1000
        tbl_cmd = client.post("/api/agent/command", headers=ceo_h, json={"message": "sort clients by risk and show table"})
        assert tbl_cmd.status_code == 200 and tbl_cmd.json()["data_table"] is not None
        assert len(tbl_cmd.json()["data_table"]["rows"]) >= 1


def test_ai_engine_fixes_sse_errors_and_history(monkeypatch):
    """Verify Codex JWT claim extraction, SSE streaming parser, error transparency, conversational greeting, and history."""
    import base64
    import json

    from app.database import SessionLocal
    from app.services import hermes_engine
    from app.services.connectors import set_setting

    # 1. JWT chatgpt-account-id claim extraction
    payload = base64.urlsafe_b64encode(
        json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_test_123"}}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    fake_jwt = f"eyJhbGciOiJSUzI1NiJ9.{payload}.sig"
    assert hermes_engine._extract_chatgpt_account_id(fake_jwt) == "acct_test_123"

    # 2. Conversational greeting when NO provider is configured (must NOT dump canned 3-source Embassy blurb)
    db = SessionLocal()
    try:
        set_setting(db, "ai_provider", "auto", is_secret=False, category="ai")
        set_setting(db, "codex_access_token", "", is_secret=True, category="oauth")
        set_setting(db, "claude_oauth_token", "", is_secret=True, category="oauth")
        set_setting(db, "antigravity_access_token", "", is_secret=True, category="oauth")

        greet = hermes_engine.answer_customer_question(db, "hi there")
        assert "Here is verified guidance based on official U.S. Embassy Kingston" not in greet["reply"]
        assert "ChatGPT" in greet["reply"] and "Claude" in greet["reply"] and "Ollama" in greet["reply"]
        assert greet["provider_used"] == "none-configured"

        # 3. Connected provider HTTP error must NEVER be silently swallowed
        set_setting(db, "ai_provider", "openai-codex", is_secret=False, category="ai")
        set_setting(db, "codex_access_token", fake_jwt, is_secret=True, category="oauth")

        def fake_codex_fail(token, model, system_prompt, history, user_prompt):
            return None, 401, "Session expired — please re-authenticate"

        monkeypatch.setattr(hermes_engine, "_call_openai_codex_sse", fake_codex_fail)
        err_res = hermes_engine.answer_customer_question(db, "hi")
        assert "HTTP 401" in err_res["reply"]
        assert "Session expired" in err_res["reply"]
        assert "Here is verified guidance" not in err_res["reply"]

        # 4. Connected provider receives full conversation history
        captured = {}

        def fake_codex_ok(token, model, system_prompt, history, user_prompt):
            captured["history"] = history
            captured["user_prompt"] = user_prompt
            return "Hello Shakir! I remember our earlier turn.", 200, None

        monkeypatch.setattr(hermes_engine, "_call_openai_codex_sse", fake_codex_ok)
        prior_turns = [
            {"role": "user", "content": "My name is Shakir."},
            {"role": "assistant", "content": "Nice to meet you, Shakir!"},
        ]
        ok_res = hermes_engine.answer_customer_question(db, "What is my name?", history=prior_turns)
        assert ok_res["reply"] == "Hello Shakir! I remember our earlier turn."
        assert ok_res["provider_used"].startswith("chatgpt-codex:")
        assert captured["history"] == prior_turns
        assert captured["user_prompt"] == "What is my name?"

        # 5. Typo-tolerant case ID detection (CO33, co27, case 34)
        from app.routers.agent_router import _detect_case_id, _wants_questionnaire_generation

        assert _detect_case_id(db, "CO33", "C034") == "C033"
        assert _detect_case_id(db, "co27", "C034") == "C027"
        assert _detect_case_id(db, "what should I do for case 34?", None) == "C034"
        assert _wants_questionnaire_generation("genereate folloup question for co34") is True
        assert _wants_questionnaire_generation("prepare question for Marcus campbell") is True
    finally:
        # Clean up test settings
        set_setting(db, "ai_provider", "auto", is_secret=False, category="ai")
        set_setting(db, "codex_access_token", "", is_secret=True, category="oauth")
        db.close()


def test_v220_username_forgot_gmail_zip_delete():
    """Verify v2.2.0: username login + testaccount all-tiers, Forgot Password PIN, Gmail Cron/Dual Mode, ZIP/TXT synthesis, and Safe Chat Delete + Undo."""
    import io
    import zipfile

    with TestClient(app) as client:
        # 1. All-tier testaccount login by username (no email needed!)
        login = client.post("/api/auth/login", json={"username": "testaccount", "password": "testpassword"})
        assert login.status_code == 200, login.text
        u = login.json()["user"]
        assert u["username"] == "testaccount"
        assert u["all_tiers"] is True
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 2. Forgot Password flow via username + offline Recovery PIN ('1234'), then restore 'testpassword'
        req = client.post("/api/auth/forgot-password/request", json={"identifier": "testaccount"})
        assert req.status_code == 200 and req.json()["has_recovery_pin"] is True
        rst = client.post(
            "/api/auth/forgot-password/reset",
            json={"identifier": "testaccount", "recovery_pin": "1234", "new_password": "newpassword123"},
        )
        assert rst.status_code == 200 and rst.json()["reset"] is True
        assert client.post("/api/auth/login", json={"username": "testaccount", "password": "newpassword123"}).status_code == 200
        # Change password back to testpassword
        chg = client.post(
            "/api/auth/change-password",
            headers=h,
            json={"current_password": "newpassword123", "new_password": "testpassword"},
        )
        assert chg.status_code == 200 and chg.json()["updated"] is True

        # 3. Gmail Automation Hub: overview, 5 seeded Dual-Mode rules, Run All, AI Draft, Hermes Cron sync
        ov = client.get("/api/gmail/overview", headers=h)
        assert ov.status_code == 200 and len(ov.json()["rules"]) >= 5
        run_res = client.post("/api/gmail/run-all", headers=h)
        assert run_res.status_code == 200 and run_res.json()["rules_evaluated"] >= 5
        draft = client.post("/api/gmail/ai-draft", headers=h, json={"case_id": "C034", "topic": "passport expires soon"})
        assert draft.status_code == 200 and draft.json()["whatsapp_text"]
        hc = client.post("/api/gmail/sync-hermes-cron", headers=h)
        assert hc.status_code == 200 and hc.json()["job_count"] >= 5

        # 3b. Create, list, and undo a natural-language Cron Job directly from Chat!
        cron_cmd = client.post(
            "/api/agent/command",
            headers=h,
            json={"message": "create a daily 9am cron to remind clients whose passport expires within 180 days"},
        )
        assert cron_cmd.status_code == 200 and cron_cmd.json()["provider_used"] == "gmail-automation"
        c_pa = cron_cmd.json()["pending_action"]
        assert c_pa and c_pa["action_type"] == "create_cron_rule"
        list_cmd = client.post("/api/agent/command", headers=h, json={"message": "list cron jobs"})
        assert list_cmd.status_code == 200 and "Scheduled Gmail" in list_cmd.json()["reply"]
        assert client.post(f"/api/actions/{c_pa['id']}/undo", headers=h).status_code == 200

        # 4. Universal ZIP & TXT Client Synthesizer + Confirm + Undo
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            zf.writestr(
                "new_clients.txt",
                "Full Name: Andre Wallace\nEmail: andre@example.jm\nParish: St. James\nOccupation: Chef\n\n---\n\nFull Name: Keisha Grant\nEmail: keisha@example.jm\nParish: Manchester\n",
            )
            zf.writestr("Andre_Wallace_passport.txt", "Passport scan placeholder for Andre Wallace")
        zup = client.post(
            "/api/agent/upload-chat-file",
            headers=h,
            files={"file": ("batch_clients.zip", zbuf.getvalue(), "application/zip")},
        )
        assert zup.status_code == 200, zup.text
        zpa = zup.json()["pending_action"]
        assert zup.json()["row_count"] == 2
        assert client.post(f"/api/actions/{zpa['id']}/confirm", headers=h).status_code == 200
        assert client.post(f"/api/actions/{zpa['id']}/undo", headers=h).status_code == 200

        # 5. Safe Chat Delete + Confirm + Undo Snapshot Restore
        del_cmd = client.post("/api/agent/command", headers=h, json={"message": "delete client C034", "case_id": "C034"})
        assert del_cmd.status_code == 200 and del_cmd.json()["pending_action"]["action_type"] == "delete_client"
        d_id = del_cmd.json()["pending_action"]["id"]
        assert client.post(f"/api/actions/{d_id}/confirm", headers=h).status_code == 200
        assert client.get("/api/clients/C034", headers=h).status_code == 404
        assert client.post(f"/api/actions/{d_id}/undo", headers=h).status_code == 200
        assert client.get("/api/clients/C034", headers=h).status_code == 200


def test_v240_quiz_builder_and_weighted_risk():
    """Verify v2.4.0: Docs & Personal Data remain primary risk weight (Q&A gives small capped bump), plus full Quiz Builder X/Y/Z/A, Effective Pathway, Hidden Patterns & Printable PDF."""
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "testaccount", "password": "testpassword"})
        assert login.status_code == 200, login.text
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 1. Weighted Risk Scoring: answering a follow-up question or mock practice gives ONLY a small capped bump
        before = client.get("/api/clients/C034", headers=h).json()
        before_score = before["standing_score"]
        open_flags = [f for f in before["risk_flags"] if f["severity"] in ("red", "amber") and f["category"] != "ai_questionnaire"]
        assert len(open_flags) >= 1, "C034 should have active data/document risk flags"

        # Answer 8 mock practice questions — readiness lift must stay small and strictly capped at +6
        for i in range(8):
            mp = client.post(
                "/api/clients/C034/mock-practice",
                headers=h,
                json={
                    "theme": f"purpose_of_trip_{i}",
                    "question_text": f"Practice question {i}?",
                    "client_answer": "I am attending a 5-day business conference in Miami and returning to my salaried job in Kingston.",
                },
            )
            assert mp.status_code == 200, mp.text
            sb = mp.json()["score_breakdown"]
            assert sb["practice_bonus"] <= 6

        after = client.get("/api/clients/C034", headers=h).json()
        # Score must NOT magically jump to 100% just from answering practice questions while real data risks exist
        assert after["standing_score"] - before_score <= 6
        assert after["standing_score"] < 100

        # 2. Quiz Builder Canvas (X / Y / Z / A + SVG relationship edges + Effective Pathway cohorts)
        canvas_res = client.get("/api/quiz-builder/canvas?case_id=C034&effective_mode=true", headers=h)
        assert canvas_res.status_code == 200, canvas_res.text
        cv = canvas_res.json()
        assert len(cv["lane_x"]) >= 1
        assert len(cv["lane_y"]) >= 1
        assert len(cv["lane_z"]) >= 5
        assert len(cv["lane_a"]) >= 5
        assert len(cv["edges"]) >= 1
        assert len(cv["effective"]["cohort_stats"]) >= 3
        assert len(cv["clients_picker"]) >= 10

        # Criteria filters work cleanly
        for qf in ("most_common", "hardest", "weak", "most_used"):
            fr = client.get(f"/api/quiz-builder/canvas?q_filter={qf}", headers=h)
            assert fr.status_code == 200, fr.text

        # 3. Generate new relationship-backed questions
        gen = client.post("/api/quiz-builder/generate", headers=h, json={"case_id": "C034", "count": 3, "focus": "weak"})
        assert gen.status_code == 200, gen.text
        assert len(gen.json()["generated"]) >= 1

        # 4. Official Q&A (Lane Z / A) Create + Delete
        oqa = client.post(
            "/api/quiz-builder/official-qa",
            headers=h,
            json={
                "theme_id": "employer_ties",
                "visa_class": "B1/B2",
                "question_text": "How long have you worked at your current employer in Jamaica?",
                "answer_text": "State exact hire date, role, monthly salary matching DS-160, and bring your job letter.",
                "answer_quality": "strong",
                "outcome_tag": "approved",
                "difficulty": "medium",
            },
        )
        assert oqa.status_code == 200, oqa.text
        qa_id = oqa.json()["id"]
        assert client.delete(f"/api/quiz-builder/official-qa/{qa_id}", headers=h).status_code == 200

        # 5. Save Lane Y Client Answer
        first_x = cv["lane_x"][0]
        sy = client.post(
            "/api/quiz-builder/save-answer",
            headers=h,
            json={
                "case_id": "C034",
                "source_type": first_x["source_type"],
                "db_id": first_x["db_id"],
                "theme_id": first_x["theme_id"],
                "question_text": first_x["question_text"],
                "answer_text": "I have been a senior nurse at UHWI for 6 years and am visiting my sister in Fort Lauderdale for 7 days.",
            },
        )
        assert sy.status_code == 200, sy.text
        assert sy.json()["saved"] is True
        assert sy.json()["score_breakdown"]["practice_bonus"] <= 6

        # 6. Hidden Pattern Analysis
        pat = client.post("/api/quiz-builder/analyze-patterns", headers=h, json={"case_id": "C034"})
        assert pat.status_code == 200, pat.text
        pd = pat.json()
        assert pd["dataset_summary"]["total_cases"] >= 10
        assert len(pd["cohort_stats"]) >= 3
        assert len(pd["trait_patterns"]) >= 1
        assert pd["executive_summary"]

        # 7. Printable PDF (specific client + general question bank)
        pdf_client = client.get("/api/quiz-builder/print-pdf?case_id=C034", headers=h)
        assert pdf_client.status_code == 200
        assert pdf_client.headers["content-type"] == "application/pdf"
        assert pdf_client.content.startswith(b"%PDF-")

        pdf_general = client.get("/api/quiz-builder/print-pdf?case_id=ALL&q_filter=hardest", headers=h)
        assert pdf_general.status_code == 200
        assert pdf_general.headers["content-type"] == "application/pdf"
        assert pdf_general.content.startswith(b"%PDF-")

        # 8. Text-first Quiz Builder Chat Controller (generate -> Output propagation, effective pathway, patterns, print PDF)
        ch_gen = client.post("/api/quiz-builder/chat", headers=h, json={"message": "Generate 3 questions for C034"})
        assert ch_gen.status_code == 200, ch_gen.text
        assert len(ch_gen.json()["output_questions"]) >= 1
        assert ch_gen.json()["trigger_flow"] is True

        ch_eff = client.post("/api/quiz-builder/chat", headers=h, json={"message": "Trace effective pathway and who gets approved most"})
        assert ch_eff.status_code == 200
        assert ch_eff.json()["canvas_state"]["effective_mode"] is True
        assert "Client Types Getting Through Most" in ch_eff.json()["reply"]

        ch_pat = client.post("/api/quiz-builder/chat", headers=h, json={"message": "Find all hidden patterns"})
        assert ch_pat.status_code == 200
        assert "Hidden Patterns" in ch_pat.json()["reply"]

        ch_pdf = client.post("/api/quiz-builder/chat", headers=h, json={"message": "Print questions PDF for C034"})
        assert ch_pdf.status_code == 200
        assert ch_pdf.json()["print_pdf_url"] and "case_id=C034" in ch_pdf.json()["print_pdf_url"]

        ch_flt = client.post("/api/quiz-builder/chat", headers=h, json={"message": "Filter hardest questions"})
        assert ch_flt.status_code == 200
        assert ch_flt.json()["canvas_state"]["q_filter"] == "hardest"


def test_v250_live_extensions_self_evolution():
    """Verify v2.5.0: Safe Self-Evolving Software Engine (live custom risk rules, sandboxed widgets, Quiz cohorts, 1-click Undo, rollback, and .jahtaria-pack export/import)."""
    from app.services.extensions_service import validate_widget_html

    # 1. Sandbox security validator blocks unsafe scripts/exfiltration
    assert validate_widget_html("<script>eval('bad')</script>")[0] is False
    assert validate_widget_html("<script>document.cookie</script>")[0] is False
    assert validate_widget_html("<div>Safe live widget</div>")[0] is True

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "testaccount", "password": "testpassword"})
        assert login.status_code == 200
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 2. Build a live sandboxed sidebar widget via main Chat -> returns UI panel + 1-click Undo!
        w_cmd = client.post(
            "/api/agent/command",
            headers=h,
            json={"message": "Build me a Passport Expiry Tracker widget"},
        )
        assert w_cmd.status_code == 200, w_cmd.text
        assert w_cmd.json()["provider_used"] == "hermes-live-builder"
        assert w_cmd.json()["ui_panel"]["panel"] == "custom_widget"
        slug = w_cmd.json()["ui_panel"]["doc_key"]
        pa_id = w_cmd.json()["pending_action"]["id"]

        # Sandboxed HTML render endpoint injects live window.JAHTARIA_DATA
        rend = client.get(f"/api/extensions/{slug}/render", headers=h)
        assert rend.status_code == 200
        assert "window.JAHTARIA_DATA" in rend.text
        assert "Passport Expiry" in rend.text

        # 3. Build a live custom risk rule -> immediately evaluates inside evaluate_client_standing()!
        r_res = client.post(
            "/api/extensions/build",
            headers=h,
            json={"prompt": "Add a custom risk rule: flag -12 pts if B1/B2 missing documents"},
        )
        assert r_res.status_code == 200, r_res.text
        rule_ext = r_res.json()["extension"]
        assert rule_ext["ext_type"] == "risk_rule"
        assert r_res.json()["affected_cases"] >= 1

        # 4. Build a live Quiz Builder cohort -> immediately appears in Quiz Builder Effective Pathway!
        c_res = client.post(
            "/api/extensions/build",
            headers=h,
            json={"prompt": "Add a cohort for Hospitality workers"},
        )
        assert c_res.status_code == 200
        assert c_res.json()["extension"]["ext_type"] == "quiz_cohort"
        cv = client.get("/api/quiz-builder/canvas?effective_mode=true", headers=h).json()
        assert any("Hospitality" in co["label"] for co in cv["effective"]["cohort_stats"])

        # 5. Export & re-import portable .jahtaria-pack.json
        pack = client.get("/api/extensions/export-pack", headers=h)
        assert pack.status_code == 200 and pack.json()["count"] >= 3
        imp = client.post("/api/extensions/import-pack", headers=h, json=pack.json())
        assert imp.status_code == 200 and imp.json()["imported_count"] >= 3

        # 6. 1-Click Rollback works on updated version
        rb = client.post(f"/api/extensions/{rule_ext['id']}/rollback", headers=h)
        assert rb.status_code == 200

        # 7. 1-Click Undo on the Chat-built widget removes it cleanly
        undo = client.post(f"/api/actions/{pa_id}/undo", headers=h)
        assert undo.status_code == 200 and undo.json()["status"] == "undone"
        assert client.get(f"/api/extensions/{slug}", headers=h).status_code == 404


def test_v251_model_selection_and_antigravity_disconnect(monkeypatch):
    """Verify v2.5.1: model selection never sticks on Antigravity, disconnect works even with local agy, and auto respects API keys."""
    from fastapi.testclient import TestClient

    from app.database import SessionLocal
    from app.main import app
    from app.services import hermes_engine, oauth_hub
    from app.services.connectors import set_setting

    # Simulate a PC that has local Antigravity `agy` binary installed
    monkeypatch.setattr(hermes_engine, "find_antigravity_bin", lambda: "/usr/local/bin/agy")

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "testaccount", "password": "testpassword"})
        if login.status_code != 200:
            login = client.post("/api/auth/login", json={"username": "testaccount", "password": "newpassword123"})
        assert login.status_code == 200, login.text
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 1. Select Antigravity explicitly
        sel_agy = client.post("/api/models/select", headers=h, json={"provider": "antigravity", "model": "gemini-4-neon-high"})
        assert sel_agy.status_code == 200
        cat_agy = sel_agy.json()
        assert cat_agy["active_provider"] == "antigravity"
        assert cat_agy["active_model"] == "gemini-4-neon-high"
        agy_item = next(i for g in cat_agy["groups"] for i in g["items"] if i["provider"] == "antigravity")
        assert agy_item["connected"] is True

        # 2. Disconnect Antigravity -> MUST mark connected=False even though local agy binary exists & reset active_provider to auto
        disc = client.post("/api/oauth/disconnect", headers=h, json={"provider": "antigravity"})
        assert disc.status_code == 200
        cat_disc = disc.json()["catalog"]
        assert cat_disc["active_provider"] == "auto"
        assert cat_disc["active_model"] == "auto-flagship"
        auto_item = next(i for g in cat_disc["groups"] for i in g["items"] if i["provider"] == "auto")
        assert auto_item["models"] == ["auto-flagship"]  # no duplicate Auto options!
        agy_item_after = next(i for g in cat_disc["groups"] for i in g["items"] if i["provider"] == "antigravity")
        assert agy_item_after["connected"] is False

        # 3. Switch back to Antigravity then save an OpenAI API key via /api/settings/ai-provider (omitting ai_model)
        client.post("/api/models/select", headers=h, json={"provider": "antigravity", "model": "gemini-3.8-flash-medium"})
        save_oai = client.post(
            "/api/settings/ai-provider",
            headers=h,
            json={"ai_provider": "openai", "openai_api_key": "sk-test-fake-openai-key-1234567890abcdef"},
        )
        assert save_oai.status_code == 200
        cat_oai = save_oai.json()["catalog"]
        assert cat_oai["active_provider"] == "openai"
        # Must NOT leak Antigravity's gemini-3.8-flash-medium into OpenAI!
        assert "gemini" not in cat_oai["active_model"].lower()
        oai_item = next(i for g in cat_oai["groups"] for i in g["items"] if i["provider"] == "openai")
        assert oai_item["connected"] is True

        # 4. Select a specific OpenAI model & verify persistence via /api/models/catalog
        sel_oai = client.post("/api/models/select", headers=h, json={"provider": "openai", "model": "gpt-5.4"})
        assert sel_oai.status_code == 200
        assert sel_oai.json()["active_provider"] == "openai"
        assert sel_oai.json()["active_model"] == "gpt-5.4"

        # 5. In `auto` mode, configured OpenAI API key MUST be preferred ahead of Antigravity
        client.post("/api/models/select", headers=h, json={"provider": "auto", "model": "auto-flagship"})
        called_urls: list[str] = []

        class _FakeResp:
            status_code = 200
            text = '{"choices":[{"message":{"content":"OpenAI handled auto mode."}}]}'

            def json(self):
                return {"choices": [{"message": {"content": "OpenAI handled auto mode."}}]}

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, **kwargs):
                called_urls.append(url)
                if "localhost:11434" in url:
                    raise RuntimeError("ollama offline")
                return _FakeResp()

        monkeypatch.setattr(hermes_engine.httpx, "Client", _FakeClient)
        db = SessionLocal()
        try:
            set_setting(db, "codex_access_token", "", is_secret=True, category="oauth")
            set_setting(db, "claude_oauth_token", "", is_secret=True, category="oauth")
            set_setting(db, "antigravity_access_token", "ya29.fake_db_token", is_secret=True, category="oauth")
            set_setting(db, "antigravity_disabled", "", is_secret=False, category="oauth")
            res = hermes_engine.call_llm_detailed(db, "sys", "hello")
            assert res["text"] == "OpenAI handled auto mode."
            assert res["provider"].startswith("openai:")
            assert any("api.openai.com" in u for u in called_urls)
        finally:
            # Clean up test settings so other tests remain hermetic
            set_setting(db, "openai_api_key", "", is_secret=True, category="ai")
            set_setting(db, "antigravity_access_token", "", is_secret=True, category="oauth")
            set_setting(db, "antigravity_disabled", "", is_secret=False, category="oauth")
            set_setting(db, "ai_provider", "auto", is_secret=False, category="ai")
            set_setting(db, "ai_model", "auto-flagship", is_secret=False, category="ai")
            oauth_hub.clear_model_catalog_cache()
            db.close()


def test_v252_codex_live_discovery_and_http400_failover(monkeypatch):
    """Verify v2.5.2: live Codex /models discovery, retired-slug migration, and HTTP 400 unsupported-model auto-failover."""
    import base64
    import json

    from app.database import SessionLocal
    from app.services import hermes_engine, oauth_hub
    from app.services.connectors import get_setting, set_setting

    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "https://api.openai.com/auth": {
                    "chatgpt_account_id": "acct_codex_live_999",
                    "chatgpt_data_residency": "us",
                }
            }
        ).encode("utf-8")
    ).decode("ascii").rstrip("=")
    fake_jwt = f"eyJhbGciOiJSUzI1NiJ9.{payload}.sig"

    # 1. Verify _codex_account_headers extracts both ChatGPT-Account-ID and residency
    hdrs = oauth_hub._codex_account_headers(fake_jwt)
    assert hdrs["ChatGPT-Account-ID"] == "acct_codex_live_999"
    assert hdrs["x-openai-internal-codex-residency"] == "us"

    # 2. Verify live /backend-api/codex/models?client_version=99.0.0 discovery + hidden filtering + priority sorting
    seen_reqs: list[tuple[str, dict]] = []

    class _MockCodexModelsResp:
        status_code = 200

        def json(self):
            return {
                "models": [
                    {"slug": "gpt-5.6-luna", "priority": 2, "visibility": "list"},
                    {"slug": "hidden-internal", "priority": 0, "visibility": "hidden"},
                    {"slug": "gpt-6-sol", "priority": 1, "visibility": "list"},
                    {"slug": "gpt-5.5", "priority": 3, "visibility": "list"},
                ]
            }

    class _MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None, **kwargs):
            seen_reqs.append((url, headers or {}))
            if "chatgpt.com/backend-api/codex/models" in url:
                return _MockCodexModelsResp()
            raise RuntimeError("offline")

    oauth_hub.clear_model_catalog_cache()
    monkeypatch.setattr(oauth_hub.httpx, "Client", _MockHttpxClient)

    models, is_live = oauth_hub.discover_codex_models(fake_jwt)
    assert is_live is True
    assert models == ["gpt-6-sol", "gpt-5.6-luna", "gpt-5.5"]
    assert "hidden-internal" not in models
    assert any("client_version=99.0.0" in u and h.get("ChatGPT-Account-ID") == "acct_codex_live_999" for u, h in seen_reqs)

    # 3. Verify catalog auto-migrates stale saved `gpt-5.4` when account's live catalog doesn't support it
    db = SessionLocal()
    try:
        set_setting(db, "codex_access_token", fake_jwt, is_secret=True, category="oauth")
        set_setting(db, "ai_provider", "openai-codex", is_secret=False, category="ai")
        set_setting(db, "ai_model", "gpt-5.4", is_secret=False, category="ai")
        cat = oauth_hub.get_grouped_model_catalog(db)
        assert cat["active_provider"] == "openai-codex"
        assert cat["active_model"] == "gpt-6-sol"
        assert cat["codex_live_discovered"] is True
        assert get_setting(db, "ai_model", "") == "gpt-6-sol"

        # 4. Verify HTTP 400 "not supported when using Codex with a ChatGPT account" automatically fails over & persists working model
        set_setting(db, "ai_model", "gpt-5.4", is_secret=False, category="ai")
        attempted: list[str] = []

        def fake_codex_sse(token, codex_model, system_prompt, history, user_prompt):
            attempted.append(codex_model)
            if codex_model == "gpt-5.4":
                return None, 400, "The 'gpt-5.4' model is not supported when using Codex with a ChatGPT account."
            if codex_model == "gpt-6-sol":
                return "Live reply from gpt-6-sol!", 200, None
            return None, 400, "unexpected"

        monkeypatch.setattr(hermes_engine, "_call_openai_codex_sse", fake_codex_sse)
        res = hermes_engine.call_llm_detailed(db, "sys", "hi")
        assert res["text"] == "Live reply from gpt-6-sol!"
        assert res["provider"] == "chatgpt-codex:gpt-6-sol"
        assert attempted == ["gpt-5.4", "gpt-6-sol"]
        assert get_setting(db, "ai_model", "") == "gpt-6-sol"
    finally:
        set_setting(db, "codex_access_token", "", is_secret=True, category="oauth")
        set_setting(db, "ai_provider", "auto", is_secret=False, category="ai")
        set_setting(db, "ai_model", "auto-flagship", is_secret=False, category="ai")
        oauth_hub.clear_model_catalog_cache()
        db.close()




