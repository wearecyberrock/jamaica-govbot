"""Safe Self-Evolving Software Engine (Locked Core + AI-Mutable Live Extensions).

Allows Hermes (via the main Chat or Live Extensions Studio) to safely create, edit,
toggle, export/import, and 1-click rollback live agency extensions WITHOUT modifying
compiled executables or risking app stability:

1. `risk_rule`     — Live Good Standing / Risk Engine rules evaluated automatically in `risk_engine.py`.
2. `widget`        — Sandboxed custom sidebar mini-apps (`<iframe sandbox="allow-scripts">`) hydrated
                     with live read-only client/case/cohort JSON snapshots.
3. `quiz_cohort`   — Live custom client-type cohorts evaluated inside Quiz Builder Effective Pathway.
4. `pdf_template`  — Live custom printable checklist / agency header notes injected into Quiz PDFs.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import ClientCase, ClientDocument, LiveExtension, PendingAction, RiskFlag, User
from app.services.hermes_engine import COMPLIANCE_SYSTEM_PROMPT, call_llm

EXTENSIONS_DIR = DATA_DIR / "extensions"
EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)

_FORBIDDEN_WIDGET_PATTERNS = [
    r"\bdocument\.cookie\b",
    r"\blocalStorage\b",
    r"\bsessionStorage\b",
    r"\bwindow\.parent\b",
    r"\bwindow\.top\b",
    r"\beval\s*\(",
    r"\bnew\s+Function\s*\(",
    r"<script[^>]+src\s*=",
]


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:48] or "custom-module").strip("-")


def validate_widget_html(html: str) -> tuple[bool, str]:
    """Ensure AI-generated widgets stay strictly inside the safe sandbox (zero exfiltration or eval)."""
    if not html or not html.strip():
        return False, "Widget HTML cannot be empty."
    if len(html) > 120_000:
        return False, "Widget exceeds 120 KB safety limit."
    for pat in _FORBIDDEN_WIDGET_PATTERNS:
        if re.search(pat, html, re.IGNORECASE):
            return False, f"Blocked unsafe widget pattern ({pat}). Widgets run strictly sandboxed."
    return True, "ok"


def _mirror_to_disk(ext: LiveExtension) -> None:
    try:
        EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
        payload = serialize_extension(ext, include_code=True)
        (EXTENSIONS_DIR / f"{ext.slug}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def _remove_disk_mirror(slug: str) -> None:
    try:
        p = EXTENSIONS_DIR / f"{slug}.json"
        if p.exists():
            p.unlink()
    except Exception:
        pass


def serialize_extension(ext: LiveExtension, include_code: bool = False) -> dict[str, Any]:
    try:
        cfg = json.loads(ext.config_json or "{}")
    except Exception:
        cfg = {}
    out: dict[str, Any] = {
        "id": ext.id,
        "slug": ext.slug,
        "name": ext.name,
        "ext_type": ext.ext_type,
        "description": ext.description,
        "icon": ext.icon,
        "enabled": bool(ext.enabled),
        "version": ext.version,
        "config": cfg,
        "has_rollback": bool((ext.previous_snapshot_json or "").strip()),
        "created_by": ext.created_by,
        "updated_at": ext.updated_at.isoformat() if ext.updated_at else None,
    }
    if include_code:
        out["code_html"] = ext.code_html or ""
    return out


def _make_snapshot(ext: LiveExtension) -> str:
    return json.dumps(
        {
            "name": ext.name,
            "description": ext.description,
            "icon": ext.icon,
            "enabled": bool(ext.enabled),
            "version": ext.version,
            "config_json": ext.config_json,
            "code_html": ext.code_html,
        }
    )


def list_extensions(db: Session, ext_type: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
    q = db.query(LiveExtension)
    if ext_type:
        q = q.filter(LiveExtension.ext_type == ext_type)
    if enabled_only:
        q = q.filter(LiveExtension.enabled.is_(True))
    rows = q.order_by(LiveExtension.updated_at.desc(), LiveExtension.id.desc()).all()
    return [serialize_extension(r, include_code=False) for r in rows]


def build_live_widget_data(db: Session) -> dict[str, Any]:
    """Assemble live read-only agency telemetry & client summary injected into sandboxed widget iframes."""
    clients = db.query(ClientCase).order_by(ClientCase.id.desc()).all()
    docs_count: dict[str, int] = {}
    for d in db.query(ClientDocument).all():
        docs_count[d.case_id] = docs_count.get(d.case_id, 0) + 1

    today = date.today()
    rows = []
    expiring_soon = []
    for c in clients:
        days_left = None
        if c.passport_expiry:
            try:
                exp = datetime.strptime(c.passport_expiry.strip()[:10], "%Y-%m-%d").date()
                days_left = (exp - today).days
            except Exception:
                days_left = None
        item = {
            "case_id": c.case_id,
            "full_name": c.full_name or c.pseudonym or c.case_id,
            "visa_class": c.visa_class,
            "parish": c.parish or "",
            "occupation": c.occupation or "",
            "employer_name": c.employer_name or "",
            "monthly_gross_jmd": c.monthly_gross_jmd,
            "passport_expiry": c.passport_expiry or "",
            "passport_days_left": days_left,
            "standing_score": c.standing_score,
            "denial_risk_level": c.denial_risk_level,
            "pipeline_stage": c.pipeline_stage,
            "outcome": c.outcome,
            "prior_us_refusals": c.prior_us_refusals or 0,
            "vault_docs": docs_count.get(c.case_id, 0),
        }
        rows.append(item)
        if days_left is not None and days_left <= 240:
            expiring_soon.append(item)

    expiring_soon.sort(key=lambda x: x["passport_days_left"] if x["passport_days_left"] is not None else 9999)
    avg_standing = round(sum(c["standing_score"] for c in rows) / len(rows), 1) if rows else 0.0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_clients": len(rows),
        "avg_standing": avg_standing,
        "high_risk_count": sum(1 for r in rows if r["denial_risk_level"] in ("high", "critical")),
        "approved_count": sum(1 for r in rows if (r["outcome"] or "").lower() == "approved"),
        "refused_count": sum(1 for r in rows if (r["outcome"] or "").lower() == "refused"),
        "expiring_passports": expiring_soon[:15],
        "clients": rows[:80],
    }


def render_sandboxed_widget_html(db: Session, ext: LiveExtension) -> str:
    """Inject live read-only window.JAHTARIA_DATA into the sandboxed widget HTML document."""
    live_data = build_live_widget_data(db)
    data_script = f"<script>window.JAHTARIA_DATA = {json.dumps(live_data)};</script>"
    body = ext.code_html or "<div style='padding:24px;color:#cbd5e1;font-family:sans-serif'>Empty module.</div>"
    if "</head>" in body.lower():
        return re.sub(r"</head>", f"{data_script}</head>", body, count=1, flags=re.IGNORECASE)
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        "<style>*{box-sizing:border-box}body{margin:0;background:#0d0f13;color:#e2e8f0;font-family:Inter,system-ui,sans-serif;padding:18px;}"
        ".card{background:#13171b;border:1px solid rgba(255,255,255,0.09);border-radius:14px;padding:14px;margin-bottom:12px;}"
        ".badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;}"
        "input,select{background:#0f1311;border:1px solid rgba(255,255,255,0.14);color:#fff;border-radius:8px;padding:6px 10px;font-size:12px;}"
        "table{width:100%;border-collapse:collapse;font-size:12px;}th,td{padding:8px;border-bottom:1px solid rgba(255,255,255,0.07);text-align:left;}"
        "th{color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.05em;}</style>"
        f"{data_script}</head><body>{body}</body></html>"
    )


# ── LIVE RUNTIME HOOKS (CALLED SAFELY BY LOCKED CORE) ─────────────────────────


def evaluate_custom_risk_rules(
    db: Session,
    client: ClientCase,
    add_flag: Callable[..., None],
) -> None:
    """Evaluate all enabled custom `risk_rule` extensions safely during Good Standing audits."""
    try:
        rules = (
            db.query(LiveExtension)
            .filter(LiveExtension.ext_type == "risk_rule", LiveExtension.enabled.is_(True))
            .all()
        )
    except Exception:
        return

    if not rules:
        return

    vault_count = db.query(ClientDocument).filter(ClientDocument.case_id == client.case_id).count()
    tags_raw = (client.profile_tags_json or "").lower()
    occ = (client.occupation or "").lower()
    emp = (client.employer_name or "").lower()
    parish = (client.parish or "").lower()
    vc = (client.visa_class or "").upper()

    for ext in rules:
        try:
            cfg = json.loads(ext.config_json or "{}")
            cond = cfg.get("conditions") or {}
            matched = True

            if cond.get("visa_class") and cond["visa_class"].upper() not in vc:
                matched = False
            if matched and cond.get("occupation_contains"):
                kw = str(cond["occupation_contains"]).lower()
                if kw not in occ and kw not in tags_raw and kw not in emp:
                    matched = False
            if matched and cond.get("parish_contains"):
                if str(cond["parish_contains"]).lower() not in parish:
                    matched = False
            if matched and cond.get("tag_contains"):
                if str(cond["tag_contains"]).lower() not in tags_raw:
                    matched = False
            if matched and cond.get("min_prior_refusals") is not None:
                if (client.prior_us_refusals or 0) < int(cond["min_prior_refusals"]):
                    matched = False
            if matched and cond.get("max_income_jmd") is not None:
                if client.monthly_gross_jmd is not None and client.monthly_gross_jmd > float(cond["max_income_jmd"]):
                    matched = False
            if matched and cond.get("requires_vault_docs"):
                if vault_count >= int(cond["requires_vault_docs"]):
                    matched = False
            if matched and cond.get("field_missing"):
                fld = str(cond["field_missing"])
                val = getattr(client, fld, None)
                if val is not None and str(val).strip() != "":
                    matched = False

            if matched:
                penalty = max(0, min(30, int(cfg.get("penalty", 10))))
                severity = cfg.get("severity") if cfg.get("severity") in ("red", "amber", "green") else ("red" if penalty >= 15 else "amber")
                code = f"CUSTOM_{ext.slug.upper().replace('-', '_')[:40]}"
                add_flag(
                    code=code,
                    severity=severity,
                    category="custom_rule",
                    title=f"[Custom Rule] {cfg.get('title') or ext.name}",
                    detail=cfg.get("detail") or ext.description or "Triggered by agency-defined live risk rule.",
                    suggested_fix=cfg.get("suggested_fix") or "Verify supporting documentation and update client record.",
                    follow_up_question=cfg.get("follow_up_question") or f"Please clarify documentation related to {ext.name}.",
                    source_citation=f"Agency Live Rule ({ext.name} v{ext.version})",
                    source_url="",
                    penalty=penalty,
                )
        except Exception:
            continue


def get_custom_cohorts(db: Session) -> list[dict[str, Any]]:
    """Return enabled custom Quiz Builder cohorts."""
    try:
        rows = (
            db.query(LiveExtension)
            .filter(LiveExtension.ext_type == "quiz_cohort", LiveExtension.enabled.is_(True))
            .all()
        )
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            cfg = json.loads(r.config_json or "{}")
            out.append(
                {
                    "cohort_id": f"custom_{r.slug}",
                    "label": r.name,
                    "summary": r.description or cfg.get("summary") or "Agency-defined custom client cohort",
                    "config": cfg,
                }
            )
        except Exception:
            continue
    return out


def client_matches_custom_cohort(c: ClientCase, cfg: dict[str, Any]) -> bool:
    tags = (c.profile_tags_json or "").lower()
    occ = (c.occupation or "").lower()
    emp = (c.employer_name or "").lower()
    parish = (c.parish or "").lower()
    vc = (c.visa_class or "").upper()
    purpose = (c.purpose_of_trip or "").lower()

    if cfg.get("visa_class") and cfg["visa_class"].upper() not in vc:
        return False
    if cfg.get("keyword"):
        kw = str(cfg["keyword"]).lower()
        hay = f"{tags} {occ} {emp} {parish} {purpose}"
        if not any(part.strip() and part.strip() in hay for part in kw.split(",")):
            return False
    if cfg.get("min_prior_refusals") is not None and (c.prior_us_refusals or 0) < int(cfg["min_prior_refusals"]):
        return False
    return True


def get_custom_pdf_notes(db: Session) -> list[str]:
    """Return enabled custom printable PDF notes/checklists."""
    try:
        rows = (
            db.query(LiveExtension)
            .filter(LiveExtension.ext_type == "pdf_template", LiveExtension.enabled.is_(True))
            .all()
        )
    except Exception:
        return []
    notes = []
    for r in rows:
        try:
            cfg = json.loads(r.config_json or "{}")
            txt = (cfg.get("note") or r.description or "").strip()
            if txt:
                notes.append(f"{r.name}: {txt}")
        except Exception:
            continue
    return notes


# ── DETERMINISTIC HIGH-CRAFT WIDGET TEMPLATES (OFFLINE + FALLBACK) ───────────


def _template_passport_tracker_html() -> str:
    return """<div style="max-width:960px;margin:0 auto;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
    <div>
      <h2 style="margin:0;font-size:16px;color:#fff;">Passport Expiry &amp; PICA Renewal Tracker</h2>
      <p style="margin:3px 0 0;font-size:12px;color:#94a3b8;">Live 6-month Kingston Embassy validity watch across all client cases</p>
    </div>
    <input id="q" placeholder="Filter client or parish..." oninput="render()" />
  </div>
  <div id="stats" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;"></div>
  <div class="card"><table><thead><tr><th>Case</th><th>Client</th><th>Visa</th><th>Expiry</th><th>Days Left</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table></div>
</div>
<script>
function render(){
  const d = window.JAHTARIA_DATA || {clients:[]};
  const q = (document.getElementById('q').value || '').toLowerCase();
  const list = (d.clients || []).filter(c => (c.full_name + ' ' + c.case_id + ' ' + c.parish).toLowerCase().includes(q));
  const urgent = list.filter(c => c.passport_days_left !== null && c.passport_days_left < 180).length;
  const missing = list.filter(c => !c.passport_expiry).length;
  document.getElementById('stats').innerHTML =
    '<div class="card"><div style="font-size:10px;color:#94a3b8;">TOTAL CLIENTS</div><div style="font-size:22px;font-weight:700;color:#fff;">'+list.length+'</div></div>' +
    '<div class="card"><div style="font-size:10px;color:#f87171;">UNDER 6 MONTHS</div><div style="font-size:22px;font-weight:700;color:#f87171;">'+urgent+'</div></div>' +
    '<div class="card"><div style="font-size:10px;color:#fbbf24;">UNVERIFIED EXPIRY</div><div style="font-size:22px;font-weight:700;color:#fbbf24;">'+missing+'</div></div>';
  document.getElementById('rows').innerHTML = list.slice(0,30).map(c => {
    const dl = c.passport_days_left;
    const badge = !c.passport_expiry ? '<span class="badge" style="background:rgba(251,191,36,.15);color:#fbbf24;">Missing</span>'
      : dl < 180 ? '<span class="badge" style="background:rgba(248,113,113,.15);color:#f87171;">Renew PICA</span>'
      : '<span class="badge" style="background:rgba(52,211,153,.15);color:#34d399;">Valid</span>';
    return '<tr><td style="font-family:monospace;color:#60a5fa;">'+c.case_id+'</td><td>'+c.full_name+'</td><td>'+c.visa_class+'</td><td>'+(c.passport_expiry||'—')+'</td><td>'+(dl===null?'—':dl+'d')+'</td><td>'+badge+'</td></tr>';
  }).join('');
}
render();
</script>"""


def _template_fee_calculator_html() -> str:
    return """<div style="max-width:720px;margin:0 auto;">
  <h2 style="margin:0 0 4px;font-size:16px;color:#fff;">U.S. Visa Fee &amp; JMD Trip Budget Calculator</h2>
  <p style="margin:0 0 14px;font-size:12px;color:#94a3b8;">Instant MRV fee, SEVIS, PICA renewal &amp; JMD/USD exchange estimator for Kingston applicants</p>
  <div class="card" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
    <div><label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px;">Visa Class</label>
      <select id="vc" onchange="calc()" style="width:100%;"><option value="185">B1/B2 Visitor ($185)</option><option value="185">F-1 Student ($185 + $350 SEVIS)</option><option value="205">H-2B / Petition Worker ($205)</option></select></div>
    <div><label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px;">Applicants</label>
      <input id="cnt" type="number" min="1" value="1" oninput="calc()" style="width:100%;"/></div>
    <div><label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px;">JMD per 1 USD</label>
      <input id="fx" type="number" value="158" oninput="calc()" style="width:100%;"/></div>
    <div><label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px;">Est. Flight + Hotel (USD)</label>
      <input id="trip" type="number" value="1450" oninput="calc()" style="width:100%;"/></div>
  </div>
  <div id="out" class="card" style="border-color:rgba(229,184,75,.35);"></div>
</div>
<script>
function calc(){
  const sel = document.getElementById('vc');
  const mrv = Number(sel.value) || 185;
  const sevis = sel.options[sel.selectedIndex].text.includes('SEVIS') ? 350 : 0;
  const cnt = Math.max(1, Number(document.getElementById('cnt').value) || 1);
  const fx = Math.max(1, Number(document.getElementById('fx').value) || 158);
  const trip = Math.max(0, Number(document.getElementById('trip').value) || 0);
  const feesUsd = (mrv + sevis) * cnt;
  const totalUsd = feesUsd + trip * cnt;
  const totalJmd = Math.round(totalUsd * fx);
  document.getElementById('out').innerHTML =
    '<div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="color:#94a3b8;">Official Visa Fees (USD)</span><b style="color:#e5b84b;">$'+feesUsd.toLocaleString()+'</b></div>' +
    '<div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="color:#94a3b8;">Total Est. Budget (USD)</span><b style="color:#34d399;">$'+totalUsd.toLocaleString()+'</b></div>' +
    '<div style="display:flex;justify-content:space-between;font-size:15px;"><span>Total in Jamaican Dollars</span><b style="color:#fff;">JMD '+totalJmd.toLocaleString()+'</b></div>';
}
calc();
</script>"""


def _template_generic_dashboard_html(title: str, subtitle: str) -> str:
    safe_t = title.replace("<", "&lt;").replace(">", "&gt;")
    safe_s = subtitle.replace("<", "&lt;").replace(">", "&gt;")
    return f"""<div style="max-width:960px;margin:0 auto;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
    <div>
      <h2 style="margin:0;font-size:16px;color:#fff;">{safe_t}</h2>
      <p style="margin:3px 0 0;font-size:12px;color:#94a3b8;">{safe_s}</p>
    </div>
    <input id="q" placeholder="Search cases..." oninput="render()" />
  </div>
  <div id="kpis" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;"></div>
  <div class="card"><table><thead><tr><th>Case</th><th>Client</th><th>Visa</th><th>Occupation</th><th>Vault Docs</th><th>Standing</th></tr></thead><tbody id="tb"></tbody></table></div>
</div>
<script>
function render(){{
  const d = window.JAHTARIA_DATA || {{clients:[]}};
  const q = (document.getElementById('q').value || '').toLowerCase();
  const list = (d.clients || []).filter(c => (c.full_name+' '+c.case_id+' '+c.occupation+' '+c.visa_class).toLowerCase().includes(q));
  document.getElementById('kpis').innerHTML =
    '<div class="card"><div style="font-size:10px;color:#94a3b8;">CASES</div><div style="font-size:20px;font-weight:700;color:#fff;">'+d.total_clients+'</div></div>'+
    '<div class="card"><div style="font-size:10px;color:#34d399;">AVG STANDING</div><div style="font-size:20px;font-weight:700;color:#34d399;">'+d.avg_standing+'%</div></div>'+
    '<div class="card"><div style="font-size:10px;color:#f87171;">HIGH RISK</div><div style="font-size:20px;font-weight:700;color:#f87171;">'+d.high_risk_count+'</div></div>'+
    '<div class="card"><div style="font-size:10px;color:#e5b84b;">APPROVED</div><div style="font-size:20px;font-weight:700;color:#e5b84b;">'+d.approved_count+'</div></div>';
  document.getElementById('tb').innerHTML = list.slice(0,30).map(c =>
    '<tr><td style="font-family:monospace;color:#60a5fa;">'+c.case_id+'</td><td>'+c.full_name+'</td><td>'+c.visa_class+'</td><td>'+(c.occupation||'—')+'</td><td>'+c.vault_docs+'</td><td><b>'+c.standing_score+'%</b></td></tr>'
  ).join('');
}}
render();
</script>"""


# ── NATURAL-LANGUAGE HERMES EXTENSION BUILDER ─────────────────────────────────


def build_extension_from_prompt(
    db: Session,
    prompt: str,
    author: str = "Hermes Builder",
    user_id: int | None = None,
) -> dict[str, Any]:
    """Build or update a live extension (risk_rule | widget | quiz_cohort | pdf_template) safely."""
    raw = (prompt or "").strip()
    low = raw.lower()
    if not raw:
        raise ValueError("Please describe the rule, widget, cohort, or template you want Hermes to build.")

    # Detect extension type cleanly
    if any(k in low for k in ("risk rule", "scoring rule", "add rule", "flag ", "penalty", "deduct", "points if")):
        ext_type = "risk_rule"
    elif any(k in low for k in ("cohort", "client group", "client type")):
        ext_type = "quiz_cohort"
    elif any(k in low for k in ("pdf note", "pdf template", "print header", "print checklist", "cover note")):
        ext_type = "pdf_template"
    else:
        ext_type = "widget"

    name = ""
    description = raw[:220]
    icon = "sparkles"
    config: dict[str, Any] = {}
    code_html = ""
    provider_used = "hermes-live-builder"

    if ext_type == "risk_rule":
        icon = "shield"
        m_pen = re.search(r"[-+]?(\d{1,2})\s*(?:pt|pts|point|points|%)", low)
        penalty = max(3, min(30, int(m_pen.group(1)))) if m_pen else 12
        severity = "red" if ("red" in low or penalty >= 15) else "amber"
        cond: dict[str, Any] = {}
        for vc in ("B1/B2", "F-1", "H-2B", "J-1"):
            if vc.lower() in low or vc.replace("-", "").lower() in low:
                cond["visa_class"] = vc
                break
        if "self-employed" in low or "self employed" in low or "business" in low:
            cond["occupation_contains"] = "business"
        elif "nurse" in low or "hospitality" in low or "hotel" in low or "student" in low:
            for kw in ("nurse", "hospitality", "hotel", "student"):
                if kw in low:
                    cond["occupation_contains"] = kw
                    break
        if "prior refusal" in low or "refused" in low:
            cond["min_prior_refusals"] = 1
        if any(k in low for k in ("vault", "bank statement", "document", "trn", "payslip", "job letter")):
            cond["requires_vault_docs"] = 1
        if "missing employer" in low or "no employer" in low:
            cond["field_missing"] = "employer_name"
        elif "missing email" in low or "no email" in low:
            cond["field_missing"] = "email"
        elif "missing passport" in low or "no passport" in low:
            cond["field_missing"] = "passport_expiry"

        clean_title = re.sub(r"^(?:please\s+)?(?:add|create|build|make)\s+(?:a\s+)?(?:custom\s+)?(?:risk|scoring)\s+rule[:\-\s]*", "", raw, flags=re.IGNORECASE).strip()
        name = (clean_title[:64] or "Custom Agency Risk Rule").capitalize()
        config = {
            "title": name,
            "detail": f"Live agency rule: {raw}",
            "severity": severity,
            "penalty": penalty,
            "conditions": cond,
            "suggested_fix": "Verify supporting documents and reconcile with Form DS-160 before interview.",
            "follow_up_question": f"Can you provide verified documentation addressing: {name}?",
        }

    elif ext_type == "quiz_cohort":
        icon = "users"
        clean_title = re.sub(r"^(?:please\s+)?(?:add|create|build|make)\s+(?:a\s+)?(?:custom\s+)?(?:quiz\s+builder\s+)?(?:cohort|client\s+type|client\s+group)\s*(?:for)?[:\-\s]*", "", raw, flags=re.IGNORECASE).strip()
        name = (clean_title[:60] or "Custom Client Cohort").title()
        kw_tokens = [w for w in re.findall(r"[a-zA-Z0-9-]+", clean_title.lower()) if len(w) >= 3 and w not in ("for", "the", "and", "with", "clients", "applicants", "workers")]
        config = {
            "summary": f"Live cohort created via Hermes: {raw}",
            "keyword": ",".join(kw_tokens[:3]) if kw_tokens else "business",
        }
        for vc in ("B1/B2", "F-1", "H-2B", "J-1"):
            if vc.lower() in low or vc.replace("-", "").lower() in low:
                config["visa_class"] = vc
                break

    elif ext_type == "pdf_template":
        icon = "file"
        clean_note = re.sub(r"^(?:please\s+)?(?:add|create|set)\s+(?:a\s+)?(?:pdf\s+template|pdf\s+note|print\s+checklist|print\s+header)[:\-\s]*", "", raw, flags=re.IGNORECASE).strip()
        name = "Agency Printable Checklist Note"
        config = {"note": clean_note or raw}

    else:
        # Custom Live Sandboxed Sidebar Widget!
        icon = "layout"
        clean_title = re.sub(
            r"^(?:please\s+)?(?:build|create|make|add)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:new\s+)?(?:custom\s+)?(?:sidebar\s+)?(?:tab|widget|mini[- ]?app|module|dashboard|tracker|tool)?\s*(?:to|for)?[:\-\s]*",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()
        clean_title = re.sub(r"\s+(?:widget|sidebar\s+tab|tab|module|mini[- ]?app)$", "", clean_title, flags=re.IGNORECASE).strip()
        name = (clean_title[:54] or "Custom Agency Tool").title()

        # Try connected LLM first for bespoke widget HTML (strictly validated before saving!)
        llm_html, prov = call_llm(
            db,
            COMPLIANCE_SYSTEM_PROMPT,
            f"Build a clean, dark-graphite standalone HTML/JS body snippet (NO <html>/<head> tags, NO external CDN links, NO localStorage/eval/fetch) for this agency sidebar module:\n"
            f"Request: {raw}\n\n"
            f"You have live read-only client data available at `window.JAHTARIA_DATA` with keys: "
            f"`total_clients`, `avg_standing`, `high_risk_count`, `approved_count`, `refused_count`, `expiring_passports`, and `clients` "
            f"(each client has `case_id`, `full_name`, `visa_class`, `parish`, `occupation`, `employer_name`, `monthly_gross_jmd`, `passport_expiry`, `passport_days_left`, `standing_score`, `denial_risk_level`, `outcome`, `vault_docs`).\n"
            f"Return ONLY the raw HTML + inline <script> snippet using clean dark styling matching #0d0f13/#13171b.",
        )
        if llm_html:
            cleaned = re.sub(r"^```(?:html)?\s*|\s*```$", "", llm_html.strip(), flags=re.IGNORECASE)
            ok, _reason = validate_widget_html(cleaned)
            if ok and ("<" in cleaned and ">" in cleaned):
                code_html = cleaned
                provider_used = prov

        if not code_html:
            if any(k in low for k in ("passport", "pica", "expir", "renew")):
                name = "Passport Expiry Tracker" if len(name) < 6 else name
                code_html = _template_passport_tracker_html()
            elif any(k in low for k in ("fee", "budget", "calculator", "jmd", "usd", "cost", "mrv")):
                name = "Visa Fee & JMD Calculator" if len(name) < 6 else name
                code_html = _template_fee_calculator_html()
            else:
                code_html = _template_generic_dashboard_html(name, f"Live agency module built by Hermes · {raw[:110]}")

        ok, reason = validate_widget_html(code_html)
        if not ok:
            raise ValueError(reason)

    slug = _slugify(name)
    existing = db.query(LiveExtension).filter(LiveExtension.slug == slug).first()
    was_existing = existing is not None
    before_snap = _make_snapshot(existing) if existing else ""

    if existing:
        existing.previous_snapshot_json = before_snap
        existing.name = name
        existing.ext_type = ext_type
        existing.description = description
        existing.icon = icon
        existing.enabled = True
        existing.version = (existing.version or 1) + 1
        existing.config_json = json.dumps(config)
        existing.code_html = code_html
        existing.created_by = author
        ext = existing
    else:
        ext = LiveExtension(
            slug=slug,
            name=name,
            ext_type=ext_type,
            description=description,
            icon=icon,
            enabled=True,
            version=1,
            config_json=json.dumps(config),
            code_html=code_html,
            previous_snapshot_json="",
            created_by=author,
        )
        db.add(ext)

    db.commit()
    db.refresh(ext)
    _mirror_to_disk(ext)

    # If a custom risk rule was added/updated, recalculate active clients immediately!
    affected_cases = 0
    if ext_type == "risk_rule":
        from app.services.risk_engine import evaluate_client_standing

        code_key = f"CUSTOM_{ext.slug.upper().replace('-', '_')[:40]}"
        for c in db.query(ClientCase).all():
            res = evaluate_client_standing(db, c)
            if any(f["code"] == code_key for f in res["flags"]):
                affected_cases += 1

    # Record a PendingAction (already applied, ready for 1-click Undo!) if user_id given
    pa = None
    if user_id is not None:
        pa = PendingAction(
            user_id=user_id,
            action_type="live_extension",
            target_ref=str(ext.id),
            summary=f"{'Updated' if was_existing else 'Created'} live {ext_type.replace('_', ' ')}: {ext.name} (v{ext.version})",
            before_json=json.dumps({"existed": was_existing, "extension_id": ext.id, "slug": ext.slug, "snapshot": before_snap}),
            after_json=json.dumps({"extension_id": ext.id, "slug": ext.slug, "version": ext.version, "ext_type": ext.ext_type}),
            status="applied",
            applied_at=datetime.now(timezone.utc),
        )
        db.add(pa)
        db.commit()
        db.refresh(pa)

    return {
        "extension": serialize_extension(ext, include_code=False),
        "provider_used": provider_used,
        "affected_cases": affected_cases,
        "pending_action": pa,
    }


def rollback_extension(db: Session, ext: LiveExtension) -> dict[str, Any]:
    if not (ext.previous_snapshot_json or "").strip():
        raise ValueError("No previous version snapshot available to rollback.")
    snap = json.loads(ext.previous_snapshot_json)
    current = _make_snapshot(ext)
    ext.name = snap.get("name", ext.name)
    ext.description = snap.get("description", ext.description)
    ext.icon = snap.get("icon", ext.icon)
    ext.enabled = bool(snap.get("enabled", True))
    ext.version = max(1, int(snap.get("version", 1)))
    ext.config_json = snap.get("config_json", "{}")
    ext.code_html = snap.get("code_html", "")
    ext.previous_snapshot_json = current
    db.commit()
    db.refresh(ext)
    _mirror_to_disk(ext)
    return serialize_extension(ext, include_code=False)


def export_extensions_pack(db: Session) -> dict[str, Any]:
    rows = db.query(LiveExtension).order_by(LiveExtension.id.asc()).all()
    return {
        "format": "jahtaria-pack/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "extensions": [serialize_extension(r, include_code=True) for r in rows],
    }


def import_extensions_pack(db: Session, pack: dict[str, Any], author: str = "Pack Import") -> dict[str, Any]:
    items = pack.get("extensions") or []
    imported = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        ext_type = str(item.get("ext_type") or "widget")
        code_html = str(item.get("code_html") or "")
        if ext_type == "widget":
            ok, reason = validate_widget_html(code_html)
            if not ok:
                continue
        slug = _slugify(str(item.get("slug") or name))
        existing = db.query(LiveExtension).filter(LiveExtension.slug == slug).first()
        cfg_str = json.dumps(item.get("config") or {})
        if existing:
            existing.previous_snapshot_json = _make_snapshot(existing)
            existing.name = name
            existing.ext_type = ext_type
            existing.description = str(item.get("description") or "")
            existing.config_json = cfg_str
            existing.code_html = code_html
            existing.version = (existing.version or 1) + 1
            existing.enabled = bool(item.get("enabled", True))
            ext = existing
        else:
            ext = LiveExtension(
                slug=slug,
                name=name,
                ext_type=ext_type,
                description=str(item.get("description") or ""),
                icon=str(item.get("icon") or "sparkles"),
                enabled=bool(item.get("enabled", True)),
                version=1,
                config_json=cfg_str,
                code_html=code_html,
                created_by=author,
            )
            db.add(ext)
        db.commit()
        db.refresh(ext)
        _mirror_to_disk(ext)
        imported.append(serialize_extension(ext))
    return {"imported_count": len(imported), "extensions": imported}


def detect_chat_extension_command(db: Session, user: User, message: str) -> dict[str, Any] | None:
    """Detect natural-language self-evolving extension commands straight from the main Chat."""
    low = (message or "").lower().strip()

    if any(k in low for k in ("open live extensions", "show live extensions", "show extensions", "manage extensions", "custom modules")):
        exts = list_extensions(db)
        return {
            "reply": f"Opened **Live Extensions** ({len(exts)} installed). Tell me to build a new **risk rule**, **sidebar widget/tab**, **Quiz Builder cohort**, or **printable PDF note** anytime — every change has **1-click Undo**.",
            "ui_panel": {"panel": "extensions", "title": "Live Extensions & Self-Evolution"},
            "pending_action": None,
        }

    triggers = (
        "build me a ",
        "build a new ",
        "create a sidebar ",
        "add a sidebar ",
        "build a widget",
        "create a widget",
        "add a risk rule",
        "create a risk rule",
        "add a custom risk rule",
        "add a scoring rule",
        "add a cohort",
        "create a cohort",
        "add a custom cohort",
        "add a pdf template",
        "add a pdf note",
        "add a print checklist",
        "build a tracker",
        "build a calculator",
        "create a mini app",
        "create a mini-app",
    )
    if any(t in low for t in triggers):
        res = build_extension_from_prompt(db, message, author=user.full_name, user_id=user.id)
        ext = res["extension"]
        etype = ext["ext_type"]
        if etype == "widget":
            panel = {"panel": "custom_widget", "doc_key": ext["slug"], "title": ext["name"]}
            extra = "It is now live in your left sidebar under **Custom Modules** and open on the right."
        elif etype == "risk_rule":
            panel = {"panel": "extensions", "title": "Live Extensions & Self-Evolution"}
            extra = f"Recalculated Good Standing across all clients immediately (**{res['affected_cases']} cases matched**)."
        elif etype == "quiz_cohort":
            panel = {"panel": "extensions", "title": "Live Extensions & Self-Evolution"}
            extra = "It is now live inside **Quiz Builder → Effective Pathway** and **Hidden Patterns**."
        else:
            panel = {"panel": "extensions", "title": "Live Extensions & Self-Evolution"}
            extra = "It will automatically appear on all printable **Quiz Builder PDFs**."
        return {
            "reply": (
                f"Built and activated live **{etype.replace('_', ' ')}**: **{ext['name']}** (`v{ext['version']}`, via `{res['provider_used']}`).\n\n"
                f"{extra}\n\n"
                "Core app & database remain safely locked — click **Undo** below anytime to revert cleanly."
            ),
            "ui_panel": panel,
            "pending_action": res["pending_action"],
        }

    return None
