"""Hermes-Powered Multi-Provider AI Engine & Autonomous Tool-Calling Loop ("Hands").

Supports:
1. Antigravity (`agy` CLI subscription runner adapted from Elevedenbot/server/api/antigravity_stream.py)
2. Local Ollama (configurable base URL & model — 100% private PII mode)
3. Cloud API Keys via LiteLLM / HTTP (OpenAI/ChatGPT, Anthropic/Claude, Google Gemini, xAI Grok, OpenRouter)
4. Grounded Deterministic Consular Intelligence Fallback (works out of the box with zero API keys!)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models import (
    BrandingConfig,
    ClientCase,
    GeneratedAsset,
    GovSource,
    OfficialDocument,
    PipelineJournal,
)
from app.services.connectors import get_setting
from app.services.doc_generator import (
    generate_ds160_worksheet_pdf,
    generate_kingston_checklist_pdf,
    generate_support_letter_docx,
    generate_visual_roadmap_png,
)
from app.services.obsidian import sync_client_to_obsidian
from app.services.risk_engine import evaluate_client_standing, generate_ranked_predictions
from app.services.scraper import scrape_single_source

COMPLIANCE_SYSTEM_PROMPT = """You are the Jahtaria Visa Intelligence AI Specialist for Jamaican applicants preparing for U.S. Visa interviews at the U.S. Embassy in Kingston (142 Old Hope Road, Kingston).

STRICT COMPLIANCE RULES (NON-NEGOTIABLE):
1. Assist ONLY with truthful application verification, factual document readiness, and accurate, spontaneous interview answers.
2. NEVER coach concealment, NEVER invent ties, NEVER advise omitting U.S. relatives or prior refusals, and NEVER guarantee visa approval.
3. Clearly distinguish Gross vs. Net JMD monthly salary (DS-160 requires accurate monthly gross; net take-home is a normal distinction, not automatically false).
4. Always cite official verified sources (jm.usembassy.gov, travel.state.gov, ais.usvisa-info.com/en-jm/niv, pica.gov.jm) when referencing fees, passport rules, the April 1, 2025 DS-160 AA-barcode matching rule, or the 92% RGD civil document photocopy rule.
5. Keep answers practical, warm, clear, and concise."""


def find_antigravity_bin() -> str | None:
    found = shutil.which("agy")
    if found:
        return found
    for cand in (
        Path("/usr/local/bin/agy"),
        Path.home() / ".local" / "bin" / "agy",
        Path("/opt/antigravity/bin/agy"),
    ):
        if cand.exists() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def detect_available_providers(db: Session) -> dict[str, Any]:
    agy_bin = find_antigravity_bin()
    claude_cli = shutil.which("claude")
    codex_cli = shutil.which("codex")
    ollama_url = get_setting(db, "ollama_base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_models: list[str] = []
    ollama_ok = False
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{ollama_url.rstrip('/')}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                ollama_models = [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        pass

    return {
        "active_provider": get_setting(db, "ai_provider", "auto"),
        "active_model": get_setting(db, "ai_model", "gpt-4o-mini"),
        "subscriptions": {
            "antigravity_agy": {"installed": bool(agy_bin), "binary": agy_bin or "", "models": ["gemini-3.8-flash-medium", "claude-sonnet-5-5-medium", "gemini-4-argon-high"]},
            "claude_cli": {"installed": bool(claude_cli), "binary": claude_cli or ""},
            "codex_chatgpt_cli": {"installed": bool(codex_cli), "binary": codex_cli or ""},
        },
        "ollama": {"reachable": ollama_ok, "base_url": ollama_url, "models": ollama_models},
        "api_keys": {
            "openai": bool(get_setting(db, "openai_api_key", os.getenv("OPENAI_API_KEY", ""))),
            "anthropic": bool(get_setting(db, "anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", ""))),
            "gemini": bool(get_setting(db, "gemini_api_key", os.getenv("GEMINI_API_KEY", ""))),
            "xai_grok": bool(get_setting(db, "xai_api_key", os.getenv("XAI_API_KEY", ""))),
            "openrouter": bool(get_setting(db, "openrouter_api_key", os.getenv("OPENROUTER_API_KEY", ""))),
        },
    }


def call_llm(db: Session, system_prompt: str, user_prompt: str) -> tuple[str | None, str]:
    """Route completion across Subscriptions (ChatGPT Codex, Claude Pro/Max, Antigravity), Local Ollama, and Cloud API Keys."""
    provider = get_setting(db, "ai_provider", "auto").lower()
    model = get_setting(db, "ai_model", "")

    # 1. ChatGPT / OpenAI Codex Subscription OAuth
    if provider in ("openai-codex", "auto"):
        codex_tok = get_setting(db, "codex_access_token", "")
        if codex_tok:
            codex_model = model if model and ("gpt-" in model or model.startswith("o")) else "gpt-5.3-codex"
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.post(
                        "https://chatgpt.com/backend-api/codex/responses",
                        headers={
                            "Authorization": f"Bearer {codex_tok}",
                            "Content-Type": "application/json",
                            "User-Agent": "codex_cli_rs/0.0.0 (Jahtaria Desktop)",
                        },
                        json={
                            "model": codex_model,
                            "instructions": system_prompt,
                            "input": [{"role": "user", "content": user_prompt}],
                            "store": False,
                            "stream": False,
                        },
                    )
                    if r.status_code == 200:
                        data = r.json()
                        txt = data.get("output_text") or ""
                        if not txt and isinstance(data.get("output"), list):
                            parts = []
                            for item in data["output"]:
                                for c in item.get("content", []):
                                    if c.get("text"):
                                        parts.append(c["text"])
                            txt = "\n".join(parts)
                        if txt.strip():
                            return txt.strip(), f"chatgpt-codex:{codex_model}"
            except Exception:
                pass

    # 2. Claude Pro / Max Subscription OAuth Token
    if provider in ("claude-sub", "auto"):
        claude_tok = get_setting(db, "claude_oauth_token", os.getenv("CLAUDE_CODE_OAUTH_TOKEN", ""))
        if claude_tok:
            c_model = model if model.startswith("claude") else "claude-sonnet-4-5"
            try:
                with httpx.Client(timeout=35.0) as client:
                    r = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Authorization": f"Bearer {claude_tok}",
                            "anthropic-version": "2023-06-01",
                            "anthropic-beta": "oauth-2025-04-20",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": c_model,
                            "max_tokens": 1200,
                            "system": system_prompt,
                            "messages": [{"role": "user", "content": user_prompt}],
                        },
                    )
                    if r.status_code == 200:
                        blocks = r.json().get("content", [])
                        txt = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                        if txt.strip():
                            return txt.strip(), f"claude-subscription:{c_model}"
            except Exception:
                pass

    # 3. Antigravity CLI / Google OAuth Subscription
    if provider == "antigravity":
        agy = find_antigravity_bin()
        if agy:
            try:
                cmd = [agy, "-p", f"{system_prompt}\n\n{user_prompt}", "--output-format", "text"]
                if model:
                    cmd.extend(["--model", model])
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip(), f"antigravity:{model or 'default'}"
            except Exception:
                pass

    # 4. Local Ollama
    if provider in ("ollama", "auto"):
        ollama_url = get_setting(db, "ollama_base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        ollama_model = get_setting(db, "ollama_model", os.getenv("OLLAMA_MODEL", "llama3.2"))
        try:
            with httpx.Client(timeout=25.0) as client:
                r = client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": ollama_model,
                        "stream": False,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                if r.status_code == 200:
                    content = r.json().get("message", {}).get("content", "").strip()
                    if content:
                        return content, f"ollama:{ollama_model}"
        except Exception:
            if provider == "ollama":
                return None, "ollama_unreachable"

    # 5. Cloud API Keys (OpenAI, xAI Grok, OpenRouter, Qwen, MiniMax, Anthropic, Gemini)
    openai_compat = [
        ("openai", "openai_api_key", "OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", model or "gpt-4o-mini"),
        ("xai_grok", "xai_api_key", "XAI_API_KEY", "https://api.x.ai/v1/chat/completions", model or "grok-2-latest"),
        ("openrouter", "openrouter_api_key", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", model or "openai/gpt-4o-mini"),
        ("qwen", "qwen_api_key", "QWEN_API_KEY", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", model or "qwen-plus"),
        ("minimax", "minimax_api_key", "MINIMAX_API_KEY", "https://api.minimaxi.chat/v1/text/chatcompletion_v2", model or "MiniMax-Text-01"),
    ]
    for prov_id, setting_key, env_key, endpoint, default_model in openai_compat:
        if provider not in ("auto", prov_id):
            continue
        api_key = get_setting(db, setting_key, os.getenv(env_key, ""))
        if not api_key:
            continue
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": default_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                if r.status_code == 200:
                    txt = r.json()["choices"][0]["message"]["content"]
                    if txt:
                        return txt.strip(), f"{prov_id}:{default_model}"
        except Exception:
            continue

    # Anthropic Claude API Key
    if provider in ("auto", "anthropic"):
        anth_key = get_setting(db, "anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", ""))
        if anth_key:
            anth_model = model if model.startswith("claude") else "claude-3-5-sonnet-latest"
            try:
                with httpx.Client(timeout=30.0) as client:
                    r = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": anth_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": anth_model,
                            "max_tokens": 1200,
                            "system": system_prompt,
                            "messages": [{"role": "user", "content": user_prompt}],
                        },
                    )
                    if r.status_code == 200:
                        blocks = r.json().get("content", [])
                        txt = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                        if txt.strip():
                            return txt.strip(), f"anthropic:{anth_model}"
            except Exception:
                pass

    # Google Gemini API Key
    if provider in ("auto", "gemini"):
        gem_key = get_setting(db, "gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
        if gem_key:
            gem_model = model.replace("gemini/", "") if "gemini" in model else "gemini-2.0-flash"
            try:
                with httpx.Client(timeout=30.0) as client:
                    r = client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={gem_key}",
                        json={
                            "systemInstruction": {"parts": [{"text": system_prompt}]},
                            "contents": [{"parts": [{"text": user_prompt}]}],
                        },
                    )
                    if r.status_code == 200:
                        cands = r.json().get("candidates", [])
                        if cands:
                            txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
                            if txt.strip():
                                return txt.strip(), f"gemini:{gem_model}"
            except Exception:
                pass

    return None, "consular-ai-local"


def _gather_gov_context(db: Session, query: str) -> list[GovSource]:
    q_tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    sources = db.query(GovSource).filter(GovSource.enabled == True).all()  # noqa: E712
    scored: list[tuple[int, GovSource]] = []
    for s in sources:
        blob = f"{s.name} {s.agency} {s.category} {s.verified_summary} {s.key_rules_json} {s.scraped_excerpt}".lower()
        hits = sum(2 if tok in s.name.lower() else (1 if tok in blob else 0) for tok in q_tokens)
        scored.append((hits, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for hits, s in scored[:4] if hits > 0] or sources[:3]


def answer_customer_question(db: Session, message: str, client: ClientCase | None = None) -> dict[str, Any]:
    """Customer Portal Q&A Assistant grounded in verified official U.S./Jamaica sources."""
    relevant_sources = _gather_gov_context(db, message)
    context_lines = []
    for s in relevant_sources:
        context_lines.append(f"- [{s.name} ({s.agency})]({s.url}): {s.verified_summary}")

    case_ctx = ""
    if client:
        case_ctx = (
            f"\nClient Case Context: Case {client.case_id} ({client.visa_class}), Stage={client.pipeline_stage}, "
            f"Good Standing={client.standing_score}%, DS-160={client.ds160_confirmation_id or 'Pending'}, "
            f"Passport Expiry={client.passport_expiry or 'Pending'}."
        )

    prompt = (
        f"Verified Official Reference Knowledge:\n{chr(10).join(context_lines)}{case_ctx}\n\n"
        f"Customer Question: {message}\n\n"
        "Answer clearly in friendly, reassuring, truthful language. Cite the official URL(s) relevant to the question."
    )
    llm_reply, provider = call_llm(db, COMPLIANCE_SYSTEM_PROMPT, prompt)
    if llm_reply:
        return {
            "reply": llm_reply,
            "provider_used": provider,
            "citations": [{"name": s.name, "agency": s.agency, "url": s.url} for s in relevant_sources],
        }

    # Intelligent deterministic grounded answer (works immediately offline / without API key!)
    ql = message.lower()
    bullets: list[str] = []
    if any(k in ql for k in ("fee", "cost", "price", "mrv", "185", "pay")):
        bullets.append("**U.S. Visa MRV Application Fees (2026):** B-1/B-2 Visitor, F-1 Student, and J-1 Exchange visas are **$185 USD** (non-refundable). Petition-based work visas (H-2B, L, O, P) are **$205 USD**. Payment & Kingston scheduling are handled at `ais.usvisa-info.com/en-jm/niv`.")
    if any(k in ql for k in ("barcode", "ds-160", "ds160", "ceac", "appointment")):
        bullets.append("**Critical Kingston Embassy Rule (Effective April 1, 2025):** Your printed Form DS-160 confirmation barcode (starting with `AA`) **must exactly match** the barcode entered in your `ais.usvisa-info.com/en-jm/niv` appointment profile — otherwise you will NOT be admitted to interview.")
    if any(k in ql for k in ("passport", "pica", "renew", "expire", "6 month")):
        bullets.append("**Jamaican Passport Requirements (PICA & Kingston Embassy):** Your Jamaican passport must be valid for **at least 6 months beyond your intended U.S. entry/stay**. If renewing an undamaged adult 10-year passport with no name/marital change, you can use the **PICA Simplified Adult Renewal Form 1** (available right in our Official Documents library!).")
    if any(k in ql for k in ("birth", "rgd", "marriage", "certificate", "92%", "copy")):
        bullets.append("**Jamaican RGD Civil Document 92% Rule:** Because Jamaican RGD birth/marriage certificates are slightly longer than standard U.S. Letter paper, photocopies MUST be reduced to **92% scale** so the top and bottom serial numbers are never cut off.")
    if any(k in ql for k in ("bring", "document", "checklist", "embassy", "phone", "old hope")):
        bullets.append("**What to Bring to U.S. Embassy Kingston (142 Old Hope Road):** Valid passport (+ expired passports with prior U.S. visas), printed DS-160 confirmation page (`AA...`), AIS appointment letter, one 2×2 inch white-background photo (no glasses), employment letter + 3 months pay slips, bank statements, and 92%-scaled RGD certificates. **No cellphones, smartwatches, or large bags** — there is no storage at the Embassy.")
    if any(k in ql for k in ("salary", "income", "gross", "net", "money", "bank")):
        bullets.append("**Gross vs. Net JMD Salary Tip:** Form DS-160 asks for your **monthly gross income** (before NIS/NHT/PAYE). If an officer asks what you earn, state clearly whether the amount is gross or net take-home so it matches your payslips truthfully.")
    if any(k in ql for k in ("refus", "denied", "214", "221", "5535", "admin")):
        bullets.append("**Prior Refusals & Administrative Processing:** Always disclose prior visa refusals truthfully on DS-160. Most tourist refusals fall under INA 214(b) (ties to Jamaica). Only submit Form **DS-5535** if specifically requested by the Consular Officer (email PDF to `KingstonNIV@state.gov` with subject `V11 – DS-5535 – [SURNAME, GIVEN NAME]`).")

    if not bullets:
        for s in relevant_sources[:3]:
            bullets.append(f"**{s.name} ({s.agency}):** {s.verified_summary}")

    if client:
        bullets.append(
            f"\n**Your Current Case ({client.case_id}):** Good Standing is **{client.standing_score}%** "
            f"(Stage: `{client.pipeline_stage.replace('_', ' ').title()}`). Check your Questionnaire & Action Steps tabs to clear any remaining items."
        )

    reply = (
        "Here is verified guidance based on official U.S. Embassy Kingston & Jamaican agency sources:\n\n"
        + "\n\n".join(bullets)
        + "\n\n*Reminder: All visa preparation is strictly for truthful verification and interview readiness — final visa decisions are made solely by the U.S. Consular Officer.*"
    )
    return {
        "reply": reply,
        "provider_used": "hermes-local-knowledge",
        "citations": [{"name": s.name, "agency": s.agency, "url": s.url} for s in relevant_sources],
    }


def run_staff_agent_loop(
    db: Session,
    instruction: str,
    case_id: str | None = None,
    actor: str = "Hermes Agent",
) -> dict[str, Any]:
    """Autonomous Staff Hermes Tool-Calling & Self-Correction Loop ("Hands").

    Executes multi-step inspection, audit, scraping, self-correction, Obsidian sync,
    and draft asset generation — always pausing at the Human Approval Gate for final outputs.
    """
    tool_trace: list[dict[str, Any]] = []
    low = instruction.lower()

    # Resolve target case_id from parameter or instruction text (e.g. C001)
    if not case_id:
        m = re.search(r"\b(C\d{3})\b", instruction.upper())
        if m:
            case_id = m.group(1)

    client = db.query(ClientCase).filter(ClientCase.case_id == case_id).first() if case_id else None
    branding = db.query(BrandingConfig).first()

    # Step 1: Inspect Client Profile if target case exists
    if client:
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "get_client_case",
                "status": "ok",
                "detail": f"Loaded {client.case_id} ({client.full_name or client.pseudonym}) — {client.visa_class}, stage={client.pipeline_stage}, standing={client.standing_score}%.",
            }
        )

    # Step 2: Check if instruction requests scraping / checking official sources
    if any(k in low for k in ("scrape", "refresh", "check official", "update rules", "pica", "embassy", "source")):
        target_sources = _gather_gov_context(db, instruction)[:2]
        for src in target_sources:
            res = scrape_single_source(db, src, use_browser_fallback=False)
            tool_trace.append(
                {
                    "step": len(tool_trace) + 1,
                    "tool": "scrape_official_source",
                    "status": "ok",
                    "detail": f"Checked {src.name} ({src.url}) -> {res['status']} (changed={res['changed']}).",
                }
            )

    # Step 3: Check if instruction asks to search PDFs / forms
    if any(k in low for k in ("pdf", "form", "passport", "ds-5535", "ds-157", "blueprint")):
        docs = db.query(OfficialDocument).all()
        matched_docs = [d.title for d in docs if any(w in (d.title + d.description).lower() for w in low.split() if len(w) > 3)] or [d.title for d in docs[:5]]
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "search_official_pdfs",
                "status": "ok",
                "detail": f"Located {len(matched_docs)} official PDF/blueprint documents: {', '.join(matched_docs[:4])}.",
            }
        )

    # Step 4: Run Good Standing Audit & Self-Correction check
    audit_res = None
    if client and any(k in low for k in ("audit", "check", "risk", "standing", "fix", "correct", "review", "prepare", "packet", "generate", "interview")):
        audit_res = evaluate_client_standing(db, client)
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "run_good_standing_audit",
                "status": "ok",
                "detail": f"Evaluated {client.case_id}: Good Standing={audit_res['standing_score']}% ({audit_res['denial_risk_level']} risk) — {audit_res['red_count']} Red, {audit_res['amber_count']} Amber, {audit_res['green_count']} Green.",
            }
        )
        # Self-correction step: align pipeline stage if still new_intake
        if client.pipeline_stage == "new_intake":
            client.pipeline_stage = "risk_audit"
            db.commit()
            tool_trace.append(
                {
                    "step": len(tool_trace) + 1,
                    "tool": "self_correct_pipeline_stage",
                    "status": "ok",
                    "detail": f"Advanced {client.case_id} from 'new_intake' -> 'risk_audit' after automated rule check.",
                }
            )

    # Step 5: Generate interview predictions if asked
    if client and any(k in low for k in ("predict", "interview", "question", "mock", "prepare")):
        preds = generate_ranked_predictions(db, client, author="hermes_agent")
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "generate_ranked_predictions",
                "status": "ok",
                "detail": f"Prepared {len(preds)} interview questions ({sum(1 for p in preds if p.question_type=='profile_driven')} profile-driven + {sum(1 for p in preds if p.question_type=='policy_mandatory')} mandatory policy).",
            }
        )

    # Step 6: Generate draft documents / visual roadmap if requested (ALWAYS pauses for Human Approval!)
    created_assets: list[str] = []
    if client and any(k in low for k in ("generate", "draft", "worksheet", "checklist", "letter", "docx", "roadmap", "image", "visual", "packet")):
        if any(k in low for k in ("ds-160", "ds160", "worksheet", "packet", "all")):
            p, flds = generate_ds160_worksheet_pdf(client, client.risk_flags, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="ds160_worksheet_pdf", title="DS-160 Preparation Worksheet (Draft)", filename=p.name, file_path=str(p), mime_type="application/pdf", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if any(k in low for k in ("checklist", "packet", "all")):
            p, flds = generate_kingston_checklist_pdf(client, client.predictions, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="checklist_pdf", title="Kingston Embassy Checklist (Draft)", filename=p.name, file_path=str(p), mime_type="application/pdf", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if any(k in low for k in ("letter", "docx", "word", "packet", "all")):
            p, flds = generate_support_letter_docx(client, client.risk_flags, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="cover_letter_docx", title="Support & Verification Packet DOCX (Draft)", filename=p.name, file_path=str(p), mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if any(k in low for k in ("roadmap", "image", "visual", "step", "packet", "all")):
            p, flds = generate_visual_roadmap_png(client, client.risk_flags, branding)
            db.add(GeneratedAsset(case_id=client.case_id, asset_type="visual_roadmap_png", title="Client Visual Action Roadmap PNG (Draft)", filename=p.name, file_path=str(p), mime_type="image/png", filled_fields_json=json.dumps(flds), approval_status="pending_approval"))
            created_assets.append(p.name)
        if created_assets:
            db.commit()
            tool_trace.append(
                {
                    "step": len(tool_trace) + 1,
                    "tool": "generate_draft_assets_approval_gate",
                    "status": "paused_for_approval",
                    "detail": f"Generated {len(created_assets)} draft file(s) ({', '.join(created_assets)}) — PAUSED at Human Approval Gate before client release.",
                }
            )

    # Step 7: Sync to Obsidian Vault if requested or after audit
    if client and (any(k in low for k in ("obsidian", "vault", "note", "sync")) or audit_res):
        note = sync_client_to_obsidian(client, client.risk_flags, client.journal_entries)
        tool_trace.append(
            {
                "step": len(tool_trace) + 1,
                "tool": "sync_obsidian_dossier",
                "status": "ok",
                "detail": f"Synced live dossier & journal to Obsidian Vault: {note['path']}.",
            }
        )

    # Log to Pipeline Journal if bound to a client
    if client:
        db.add(
            PipelineJournal(
                case_id=client.case_id,
                event_type="hermes_agent_run",
                actor=actor,
                summary=f"Hermes executed {len(tool_trace)} tool steps for instruction: '{instruction[:120]}'",
                metadata_json=json.dumps({"tools": [t["tool"] for t in tool_trace], "created_assets": created_assets}),
            )
        )
        db.commit()

    # Synthesize final executive summary (LLM if configured, otherwise crisp structured summary)
    trace_text = "\n".join(f"{t['step']}. [{t['tool']}] ({t['status']}) {t['detail']}" for t in tool_trace)
    llm_reply, provider = call_llm(
        db,
        COMPLIANCE_SYSTEM_PROMPT,
        f"Staff instruction: {instruction}\n\nTool Execution Trace:\n{trace_text or 'General inquiry — no case selected.'}\n\n"
        "Summarize what was verified, any red/amber flags needing human review, and the exact next recommended step.",
    )

    if not llm_reply:
        if tool_trace:
            llm_reply = (
                f"**AI Consular Agent Complete** ({len(tool_trace)} actions executed):\n\n"
                + "\n".join(f"- **Step {t['step']} (`{t['tool']}`):** {t['detail']}" for t in tool_trace)
                + (
                    "\n\n**Human Approval Gate:** Draft documents are ready in the side panel for review before releasing to the client."
                    if created_assets
                    else ""
                )
            )
        else:
            fallback = answer_customer_question(db, instruction, client)
            llm_reply = fallback["reply"]

    return {
        "reply": llm_reply,
        "provider_used": provider,
        "case_id": client.case_id if client else None,
        "tool_trace": tool_trace,
        "created_assets": created_assets,
    }
