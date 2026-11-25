"use client";

import { useEffect, useState } from "react";
import {
  X,
  ExternalLink,
  RefreshCw,
  Download,
  CheckCircle2,
  XCircle,
  Lock,
  Upload,
  Plus,
  Save,
  Trash2,
  Copy,
  Link2,
  FileText,
  Sparkles,
  BookOpen,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type {
  BrandingConfig,
  ClientDetail,
  ClientSummary,
  GovSourceItem,
  OfficialDocItem,
  UserAccount,
  VaultNoteMeta,
} from "@/lib/types";

export interface PanelRequest {
  panel:
    | "ceo_analytics"
    | "clients_list"
    | "client"
    | "customer_case"
    | "official_pdfs"
    | "gov_sources"
    | "database"
    | "obsidian"
    | "team"
    | "settings";
  case_id?: string;
  subview?: string;
  doc_key?: string;
  table?: string;
  path?: string;
  preview_asset_id?: number | null;
  title?: string;
}

interface RightSidePanelProps {
  request: PanelRequest;
  user: UserAccount;
  branding: BrandingConfig | null;
  recentLinks: PanelRequest[];
  onNavigatePanel: (req: PanelRequest) => void;
  onSelectCaseForChat: (caseId: string) => void;
  onBrandingUpdated: (b: BrandingConfig) => void;
  onClose: () => void;
}

export function RightSidePanel({
  request,
  user,
  branding,
  recentLinks,
  onNavigatePanel,
  onSelectCaseForChat,
  onBrandingUpdated,
  onClose,
}: RightSidePanelProps) {
  const isCeo = user.role === "ceo";
  const isStaffOrCeo = user.role === "ceo" || user.role === "staff";

  return (
    <aside className="w-full lg:w-[48%] xl:w-[46%] max-w-[680px] h-full bg-[#111318] border-l border-white/10 flex flex-col shrink-0">
      {/* Top Panel Bar */}
      <div className="h-12 px-4 border-b border-white/10 flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
          <span className="text-xs font-semibold text-slate-200 truncate">
            {request.title || request.panel.replace(/_/g, " ").toUpperCase()}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
          title="Close Side Panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Recent Opened Artifacts Strip (like image_2.png Links / Files) */}
      {recentLinks.length > 1 && (
        <div className="px-4 py-2 border-b border-white/10 flex items-center gap-1.5 overflow-x-auto shrink-0 bg-[#0e1015]">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mr-1 shrink-0">
            Recent ({recentLinks.length})
          </span>
          {recentLinks.slice(0, 6).map((item, idx) => (
            <button
              key={`${item.panel}-${item.case_id || item.doc_key || item.table || idx}`}
              onClick={() => onNavigatePanel(item)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium whitespace-nowrap transition ${
                item.panel === request.panel && item.case_id === request.case_id && item.doc_key === request.doc_key
                  ? "bg-blue-500/20 text-blue-300 border border-blue-400/30"
                  : "bg-white/5 text-slate-400 hover:text-slate-200 hover:bg-white/10"
              }`}
            >
              {item.title || item.panel}
            </button>
          ))}
        </div>
      )}

      {/* Main Panel Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {request.panel === "ceo_analytics" && isCeo && <CeoAnalyticsSubPanel onOpenCase={(cid) => onNavigatePanel({ panel: "client", case_id: cid, title: `Case ${cid}` })} />}
        {request.panel === "clients_list" && isStaffOrCeo && (
          <ClientsListSubPanel
            onOpenCase={(cid) => {
              onSelectCaseForChat(cid);
              onNavigatePanel({ panel: "client", case_id: cid, subview: "overview", title: `Case ${cid}` });
            }}
          />
        )}
        {(request.panel === "client" || request.panel === "customer_case") && (
          <ClientInspectorSubPanel
            caseId={request.case_id || user.linked_case_id || "C034"}
            initialSubview={request.subview || "overview"}
            initialPreviewAssetId={request.preview_asset_id || null}
            isStaffOrCeo={isStaffOrCeo}
            onOpenObsidian={(path) => onNavigatePanel({ panel: "obsidian", path, title: `Obsidian — ${path}` })}
          />
        )}
        {request.panel === "official_pdfs" && (
          <OfficialPdfsSubPanel initialDocKey={request.doc_key} canUpload={isStaffOrCeo} />
        )}
        {request.panel === "gov_sources" && <GovSourcesSubPanel canScrape={isStaffOrCeo} />}
        {request.panel === "database" && isStaffOrCeo && <DatabaseSubPanel initialTable={request.table || "clients"} />}
        {request.panel === "obsidian" && isStaffOrCeo && <ObsidianSubPanel initialPath={request.path || "Index.md"} />}
        {request.panel === "team" && isCeo && <TeamSubPanel />}
        {request.panel === "settings" && isStaffOrCeo && (
          <SettingsSubPanel isCeo={isCeo} branding={branding} onBrandingUpdated={onBrandingUpdated} />
        )}
      </div>
    </aside>
  );
}

/* ── 1. CEO ANALYTICS + LIVE SVG GRAPHS ────────────────────────────────────── */
function CeoAnalyticsSubPanel({ onOpenCase }: { onOpenCase: (cid: string) => void }) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    apiFetch("/api/ceo/overview").then(setData).catch(() => {});
  }, []);

  if (!data) return <div className="text-xs text-slate-400 p-4">Loading CEO executive analytics…</div>;

  const { kpis, stage_distribution, risk_distribution, top_risk_flags, prediction_evaluation, recent_activity } = data;
  const totalDecided = Math.max(1, kpis.approved_cases + kpis.refused_cases);
  const approvedPct = Math.round((kpis.approved_cases / totalDecided) * 100);
  const circumference = 2 * Math.PI * 36;
  const approvedStroke = (approvedPct / 100) * circumference;

  const stageEntries = Object.entries(stage_distribution as Record<string, number>);
  const maxStage = Math.max(1, ...stageEntries.map(([, v]) => v));

  return (
    <div className="space-y-4">
      {/* KPI Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="g-card p-3.5">
          <div className="text-[11px] text-slate-400">Total Cases</div>
          <div className="text-2xl font-bold text-white mt-0.5">{kpis.total_cases}</div>
          <div className="text-[11px] text-emerald-400 mt-0.5">{kpis.approved_cases} approved • {kpis.refused_cases} refused</div>
        </div>
        <div className="g-card p-3.5">
          <div className="text-[11px] text-slate-400">Avg Good Standing</div>
          <div className="text-2xl font-bold text-amber-300 mt-0.5">{kpis.avg_good_standing_pct}%</div>
          <div className="text-[11px] text-slate-400 mt-0.5">{kpis.pending_document_approvals} draft(s) pending</div>
        </div>
        <div className="g-card p-3.5">
          <div className="text-[11px] text-slate-400">Est. Pipeline Value</div>
          <div className="text-2xl font-bold text-blue-400 mt-0.5">${kpis.estimated_pipeline_usd.toLocaleString()}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">USD active portfolio</div>
        </div>
        <div className="g-card p-3.5">
          <div className="text-[11px] text-slate-400">Verified Gov Corpus</div>
          <div className="text-2xl font-bold text-white mt-0.5">{kpis.official_pdfs_count} PDFs</div>
          <div className="text-[11px] text-slate-400 mt-0.5">{kpis.official_sources_count} gov URLs • {kpis.source_manifest_count} files</div>
        </div>
      </div>

      {/* SVG Outcome Donut + Prediction Recall */}
      <div className="g-card p-4 grid grid-cols-2 gap-4 items-center">
        <div className="flex items-center gap-3">
          <svg width="88" height="88" viewBox="0 0 88 88" className="shrink-0 -rotate-90">
            <circle cx="44" cy="44" r="36" fill="none" stroke="rgba(239,68,68,0.35)" strokeWidth="9" />
            <circle
              cx="44"
              cy="44"
              r="36"
              fill="none"
              stroke="#22c55e"
              strokeWidth="9"
              strokeDasharray={`${approvedStroke} ${circumference}`}
              strokeLinecap="round"
            />
          </svg>
          <div>
            <div className="text-[11px] text-slate-400">Reported Approval</div>
            <div className="text-xl font-bold text-emerald-400">{approvedPct}%</div>
            <div className="text-[10px] text-slate-500">of decided cases</div>
          </div>
        </div>

        <div className="space-y-1.5 border-l border-white/10 pl-4">
          <div className="text-[11px] font-semibold text-slate-300">Prediction Evaluation</div>
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Profile Recall</span>
            <span className="font-bold text-blue-300">{prediction_evaluation.profile_thematic_recall_pct}%</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Frozen Cases</span>
            <span className="font-bold text-white">{prediction_evaluation.frozen_cases_count}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">Policy Qs Separate</span>
            <span className="font-bold text-amber-300">{prediction_evaluation.policy_questions_tracked_separately}</span>
          </div>
        </div>
      </div>

      {/* SVG Pipeline Bar Chart */}
      <div className="g-card p-4 space-y-2.5">
        <div className="text-xs font-semibold text-slate-200">Pipeline Stage Distribution</div>
        <div className="space-y-2">
          {stageEntries.map(([stage, count]) => (
            <div key={stage} className="space-y-1">
              <div className="flex justify-between text-[11px]">
                <span className="text-slate-300 capitalize">{stage.replace(/_/g, " ")}</span>
                <span className="text-slate-400 font-semibold">{count}</span>
              </div>
              <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-emerald-400"
                  style={{ width: `${Math.max(6, (count / maxStage) * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Denial Risk Tier Bars */}
      <div className="g-card p-4 space-y-2">
        <div className="text-xs font-semibold text-slate-200">Top Denial-Risk &amp; Verification Flags</div>
        {top_risk_flags.map((rf: { code: string; count: number }, idx: number) => (
          <div key={idx} className="flex items-center justify-between gap-2 text-xs py-1.5 border-b border-white/5 last:border-0">
            <span className="text-slate-300 truncate">{rf.code}</span>
            <span className="px-2 py-0.5 rounded-full bg-red-500/15 text-red-300 text-[11px] font-semibold shrink-0">
              {rf.count}
            </span>
          </div>
        ))}
        <div className="flex flex-wrap gap-2 pt-2">
          {Object.entries(risk_distribution as Record<string, number>).map(([tier, cnt]) => (
            <span key={tier} className="text-[11px] px-2 py-0.5 rounded-lg bg-white/5 text-slate-300">
              {tier.toUpperCase()}: <b>{cnt}</b>
            </span>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="g-card p-4 space-y-2">
        <div className="text-xs font-semibold text-slate-200">Recent Pipeline Activity</div>
        {recent_activity.slice(0, 6).map((ev: any) => (
          <button
            key={ev.id}
            onClick={() => onOpenCase(ev.case_id)}
            className="w-full text-left p-2 rounded-lg bg-white/[0.03] hover:bg-white/[0.07] transition flex items-start gap-2 text-xs"
          >
            <span className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 font-mono text-[10px] shrink-0">
              {ev.case_id}
            </span>
            <span className="text-slate-300 line-clamp-2">{ev.summary}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── 2. CLEAN CLIENTS LIST (ACTIVE vs HISTORICAL REFERENCE) ───────────────── */
function ClientsListSubPanel({ onOpenCase }: { onOpenCase: (cid: string) => void }) {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [filterMode, setFilterMode] = useState<"active" | "historical" | "all">("active");
  const [search, setSearch] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [newVisa, setNewVisa] = useState("B1/B2");
  const [newDest, setNewDest] = useState("");
  const [newPurpose, setNewPurpose] = useState("");

  const load = () => {
    apiFetch<ClientSummary[]>(`/api/clients${search ? `?search=${encodeURIComponent(search)}` : ""}`)
      .then(setClients)
      .catch(() => {});
  };

  useEffect(load, [search]);

  const filtered = clients.filter((c) => {
    const isRef = (c.full_name || "").startsWith("Reference Case") || (c.full_name || "").startsWith("Case C00");
    if (filterMode === "active") return !isRef;
    if (filterMode === "historical") return isRef;
    return true;
  });

  const createClient = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await apiFetch<{ case_id: string }>("/api/clients", {
      method: "POST",
      body: JSON.stringify({ full_name: newName, visa_class: newVisa, us_destination: newDest, purpose_of_trip: newPurpose }),
    });
    setShowNew(false);
    setNewName("");
    setNewDest("");
    setNewPurpose("");
    load();
    onOpenCase(res.case_id);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input className="g-input text-xs flex-1" placeholder="Search cases or names..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <button onClick={() => setShowNew(!showNew)} className="g-btn-primary px-3 py-2 text-xs inline-flex items-center gap-1 shrink-0">
          <Plus className="w-3.5 h-3.5" /> New
        </button>
      </div>

      <div className="flex gap-1 bg-black/30 p-1 rounded-xl border border-white/10 text-xs">
        {(["active", "historical", "all"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setFilterMode(m)}
            className={`flex-1 py-1.5 rounded-lg font-medium capitalize transition ${
              filterMode === m ? "bg-white/15 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {m === "active" ? "Active Clients" : m === "historical" ? "Historical (33)" : `All (${clients.length})`}
          </button>
        ))}
      </div>

      {showNew && (
        <form onSubmit={createClient} className="g-card p-3.5 space-y-2.5">
          <div className="text-xs font-semibold text-white">Create New Client Case</div>
          <input className="g-input text-xs" required placeholder="Client Full Legal Name" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <select className="g-input text-xs" value={newVisa} onChange={(e) => setNewVisa(e.target.value)}>
              <option value="B1/B2">B1/B2 Visitor</option>
              <option value="F1">F-1 Student</option>
              <option value="H-2B">H-2B Worker</option>
            </select>
            <input className="g-input text-xs" placeholder="U.S. City/State" value={newDest} onChange={(e) => setNewDest(e.target.value)} />
          </div>
          <input className="g-input text-xs" placeholder="Purpose of trip" value={newPurpose} onChange={(e) => setNewPurpose(e.target.value)} />
          <button type="submit" className="g-btn-primary w-full py-2 text-xs">Create &amp; Run Audit</button>
        </form>
      )}

      <div className="space-y-2">
        {filtered.map((c) => (
          <button
            key={c.case_id}
            onClick={() => onOpenCase(c.case_id)}
            className="w-full text-left g-card p-3 hover:border-blue-400/40 transition space-y-2"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-mono text-[11px] font-bold">
                  {c.case_id}
                </span>
                <span className="text-xs font-semibold text-white truncate">{c.full_name || c.pseudonym}</span>
              </div>
              <span className="text-xs font-bold text-emerald-400">{c.standing_score}%</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div
                className={`h-full ${c.standing_score >= 80 ? "bg-emerald-500" : c.standing_score >= 60 ? "bg-amber-400" : "bg-red-500"}`}
                style={{ width: `${c.standing_score}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>{c.visa_class} • {c.pipeline_stage.replace(/_/g, " ")}</span>
              <span className="uppercase">{c.outcome}</span>
            </div>
          </button>
        ))}
        {filtered.length === 0 && (
          <div className="text-xs text-slate-500 text-center py-6">No matching cases in this view. Click + New or switch filter.</div>
        )}
      </div>
    </div>
  );
}

/* ── 3. CLIENT INSPECTOR (GOOD STANDING, FORM, INTERVIEW, DOCS, ROADMAP PNG) ─ */
function ClientInspectorSubPanel({
  caseId,
  initialSubview,
  initialPreviewAssetId,
  isStaffOrCeo,
  onOpenObsidian,
}: {
  caseId: string;
  initialSubview: string;
  initialPreviewAssetId: number | null;
  isStaffOrCeo: boolean;
  onOpenObsidian: (p: string) => void;
}) {
  const [client, setClient] = useState<ClientDetail | null>(null);
  const [view, setView] = useState(initialSubview || "overview");
  const [form, setForm] = useState<Record<string, any>>({});
  const [previewId, setPreviewId] = useState<number | null>(initialPreviewAssetId);
  const [mockQ, setMockQ] = useState<{ theme: string; question_text: string } | null>(null);
  const [mockAns, setMockAns] = useState("");
  const [mockFeedback, setMockFeedback] = useState("");
  const [journalNote, setJournalNote] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => setView(initialSubview || "overview"), [initialSubview, caseId]);
  useEffect(() => {
    if (initialPreviewAssetId) setPreviewId(initialPreviewAssetId);
  }, [initialPreviewAssetId]);

  const load = async () => {
    const endpoint = isStaffOrCeo ? `/api/clients/${caseId}` : "/api/portal/my-case";
    const data = await apiFetch<ClientDetail>(endpoint);
    setClient(data);
    setForm({
      full_name: data.full_name || "",
      email: data.email || "",
      phone: data.phone || "",
      parish: data.parish || "",
      passport_number: data.passport_number || "",
      passport_expiry: data.passport_expiry || "",
      ds160_confirmation_id: data.ds160_confirmation_id || "",
      ais_appointment_barcode: data.ais_appointment_barcode || "",
      purpose_of_trip: data.purpose_of_trip || "",
      us_destination: data.us_destination || "",
      occupation: data.occupation || "",
      employer_name: data.employer_name || "",
      monthly_gross_jmd: data.monthly_gross_jmd ?? "",
      monthly_net_jmd: data.monthly_net_jmd ?? "",
      marital_status: data.marital_status || "",
      us_relatives_details: data.us_relatives_details || "",
    });
    if (!mockQ && data.predictions.length > 0) {
      setMockQ({ theme: data.predictions[0].theme_id, question_text: data.predictions[0].question_text });
    }
    if (!previewId && data.assets.length > 0) {
      setPreviewId(data.assets[0].id);
    }
  };

  useEffect(() => {
    load().catch(() => {});
  }, [caseId]);

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(""), 4000);
  };

  if (!client) return <div className="text-xs text-slate-400 p-4">Loading case {caseId}…</div>;

  const activeAsset = client.assets.find((a) => a.id === previewId) || client.assets[0] || null;

  return (
    <div className="space-y-4">
      {/* Compact Client Header + Dropdown Switcher */}
      <div className="g-card p-3.5 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-mono text-[11px] font-bold">
                {client.case_id}
              </span>
              <h3 className="text-sm font-bold text-white">{client.full_name || client.pseudonym}</h3>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {client.visa_class} • Code: <code>{client.access_code}</code> • Stage: {client.pipeline_stage.replace(/_/g, " ")}
            </p>
          </div>
          <div className="text-right">
            <div className="text-lg font-extrabold text-emerald-400">{client.standing_score}%</div>
            <div className="text-[10px] uppercase text-slate-400">{client.denial_risk_level} risk</div>
          </div>
        </div>

        <div className="w-full h-2 rounded-full bg-white/10 overflow-hidden">
          <div
            className={`h-full transition-all ${client.standing_score >= 80 ? "bg-emerald-500" : client.standing_score >= 60 ? "bg-amber-400" : "bg-red-500"}`}
            style={{ width: `${client.standing_score}%` }}
          />
        </div>

        <div className="flex items-center gap-2">
          <select className="g-input text-xs flex-1" value={view} onChange={(e) => setView(e.target.value)}>
            <option value="overview">Good Standing &amp; Risk Flags ({client.risk_flags.length})</option>
            <option value="intake">Edit Details &amp; Questionnaire</option>
            <option value="interview">Interview Predictions &amp; Mock Practice</option>
            <option value="blueprints">Documents, Visual Roadmap &amp; Approval ({client.assets.length})</option>
            {isStaffOrCeo && <option value="journal">Pipeline Journal ({client.journal?.length || 0})</option>}
          </select>
          {isStaffOrCeo && (
            <button
              onClick={async () => {
                const res = await apiFetch<{ path: string }>(`/api/obsidian/sync-client/${client.case_id}`, { method: "POST" });
                onOpenObsidian(res.path);
              }}
              className="g-btn-ghost px-2.5 py-2 text-xs inline-flex items-center gap-1 shrink-0"
              title="Sync & Open in Obsidian Vault"
            >
              <BookOpen className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {msg && <div className="p-2.5 rounded-xl bg-emerald-500/15 border border-emerald-400/30 text-xs text-emerald-200">{msg}</div>}

      {/* SUBVIEW: OVERVIEW & FLAGS */}
      {view === "overview" && (
        <div className="space-y-2.5">
          {client.risk_flags.map((f) => (
            <div
              key={f.id}
              className={`g-card p-3 space-y-1 border-l-2 ${
                f.severity === "red" ? "border-l-red-500" : f.severity === "amber" ? "border-l-amber-400" : "border-l-emerald-500"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-semibold text-white">{f.title}</span>
                <span
                  className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0 ${
                    f.severity === "red"
                      ? "bg-red-500/20 text-red-300"
                      : f.severity === "amber"
                      ? "bg-amber-500/20 text-amber-300"
                      : "bg-emerald-500/20 text-emerald-300"
                  }`}
                >
                  {f.severity}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">{f.detail}</p>
              {f.source_url && (
                <a href={f.source_url} target="_blank" rel="noreferrer" className="text-[11px] text-blue-400 hover:underline inline-flex items-center gap-1">
                  {f.source_citation || "Verify Official Rule"} <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {/* SUBVIEW: INTAKE FORM */}
      {view === "intake" && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            await apiFetch(`/api/clients/${client.case_id}`, {
              method: "PATCH",
              body: JSON.stringify({
                ...form,
                monthly_gross_jmd: form.monthly_gross_jmd === "" ? null : Number(form.monthly_gross_jmd),
                monthly_net_jmd: form.monthly_net_jmd === "" ? null : Number(form.monthly_net_jmd),
              }),
            });
            await load();
            flash("Saved details & recalculated Good Standing!");
          }}
          className="g-card p-3.5 space-y-2.5"
        >
          <div className="grid grid-cols-2 gap-2">
            {[
              ["full_name", "Full Legal Name"],
              ["parish", "Parish"],
              ["passport_number", "Passport #"],
              ["passport_expiry", "Passport Expiry"],
              ["ds160_confirmation_id", "DS-160 (AA...)"],
              ["ais_appointment_barcode", "AIS Barcode"],
              ["occupation", "Occupation"],
              ["employer_name", "Employer"],
              ["monthly_gross_jmd", "Gross JMD / mo"],
              ["monthly_net_jmd", "Net JMD / mo"],
              ["us_destination", "U.S. City/State"],
              ["marital_status", "Legal Marital Status"],
            ].map(([k, lbl]) => (
              <div key={k}>
                <label className="block text-[10px] text-slate-400 mb-0.5">{lbl}</label>
                <input className="g-input text-xs py-1.5" value={String(form[k] ?? "")} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </div>
            ))}
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-0.5">Purpose of Trip</label>
            <input className="g-input text-xs py-1.5" value={String(form.purpose_of_trip ?? "")} onChange={(e) => setForm({ ...form, purpose_of_trip: e.target.value })} />
          </div>
          <button type="submit" className="g-btn-primary w-full py-2 text-xs">Save &amp; Re-Audit</button>
        </form>
      )}

      {/* SUBVIEW: INTERVIEW PREP & MOCK */}
      {(view === "interview" || view === "practice") && (
        <div className="space-y-3">
          {isStaffOrCeo && (
            <div className="flex items-center justify-between g-card p-3">
              <span className="text-xs text-slate-300">
                {client.predictions_frozen ? `Frozen by ${client.predictions_frozen_by}` : "Predictions unfrozen"}
              </span>
              {!client.predictions_frozen && (
                <button
                  onClick={async () => {
                    await apiFetch(`/api/clients/${client.case_id}/predictions/freeze`, { method: "POST" });
                    await load();
                    flash("Predictions frozen pre-interview!");
                  }}
                  className="g-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1"
                >
                  <Lock className="w-3 h-3" /> Freeze Pre-Interview
                </button>
              )}
            </div>
          )}

          <div className="space-y-1.5 max-h-44 overflow-y-auto">
            {client.predictions.map((p) => (
              <button
                key={p.id}
                onClick={() => setMockQ({ theme: p.theme_id, question_text: p.question_text })}
                className={`w-full text-left p-2.5 rounded-xl border text-xs transition ${
                  mockQ?.theme === p.theme_id ? "bg-blue-500/15 border-blue-400/40 text-white" : "bg-white/[0.03] border-white/5 text-slate-300"
                }`}
              >
                <span className="text-[10px] uppercase text-amber-300 font-semibold mr-2">
                  {p.question_type === "policy_mandatory" ? "Policy" : `#${p.rank}`}
                </span>
                {p.question_text}
              </button>
            ))}
          </div>

          {mockQ && (
            <div className="g-card p-3.5 space-y-2.5">
              <div className="text-xs font-semibold text-blue-300 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" /> Practice: &ldquo;{mockQ.question_text}&rdquo;
              </div>
              <textarea
                rows={3}
                className="g-input text-xs"
                placeholder="Type client's practice answer for truthful consistency check..."
                value={mockAns}
                onChange={(e) => setMockAns(e.target.value)}
              />
              <button
                onClick={async () => {
                  const r = await apiFetch<{ feedback: string }>(`/api/clients/${client.case_id}/mock-practice`, {
                    method: "POST",
                    body: JSON.stringify({ theme: mockQ.theme, question_text: mockQ.question_text, client_answer: mockAns }),
                  });
                  setMockFeedback(r.feedback);
                  setMockAns("");
                }}
                className="g-btn-primary w-full py-2 text-xs"
              >
                Check Answer
              </button>
              {mockFeedback && <div className="p-2.5 rounded-lg bg-white/5 text-xs text-slate-200 leading-relaxed">{mockFeedback}</div>}
            </div>
          )}
        </div>
      )}

      {/* SUBVIEW: DOCUMENTS, VISUAL ROADMAP PNG & APPROVAL GATE */}
      {(view === "blueprints" || view === "docs") && (
        <div className="space-y-3">
          {isStaffOrCeo && (
            <div className="grid grid-cols-2 gap-2">
              {[
                ["ds160_worksheet_pdf", "DS-160 Worksheet PDF"],
                ["checklist_pdf", "Kingston Checklist PDF"],
                ["cover_letter_docx", "Support Packet DOCX"],
                ["visual_roadmap_png", "Visual Roadmap PNG"],
              ].map(([t, lbl]) => (
                <button
                  key={t}
                  onClick={async () => {
                    const r = await apiFetch<{ id: number }>(`/api/clients/${client.case_id}/assets/generate`, {
                      method: "POST",
                      body: JSON.stringify({ asset_type: t }),
                    });
                    setPreviewId(r.id);
                    await load();
                    flash(`Generated draft ${lbl} — click Approve to release.`);
                  }}
                  className="g-btn-ghost py-2 px-2.5 text-[11px] text-left hover:border-blue-400/40"
                >
                  + {lbl}
                </button>
              ))}
            </div>
          )}

          <div className="space-y-2">
            {client.assets.map((a) => (
              <div
                key={a.id}
                onClick={() => setPreviewId(a.id)}
                className={`g-card p-3 cursor-pointer flex items-center justify-between gap-2 ${
                  activeAsset?.id === a.id ? "border-blue-400/50" : ""
                }`}
              >
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-white truncate">{a.title}</div>
                  <div className="text-[10px] text-slate-400">{a.approval_status.replace("_", " ").toUpperCase()}</div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <a
                    href={`/api/assets/${a.id}/file`}
                    download={a.filename}
                    onClick={(e) => e.stopPropagation()}
                    className="g-btn-ghost p-1.5"
                    title="Download"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </a>
                  {isStaffOrCeo && a.approval_status !== "approved" && (
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        await apiFetch(`/api/assets/${a.id}/approve`, {
                          method: "POST",
                          body: JSON.stringify({ decision: "approved", visible_to_client: true }),
                        });
                        await load();
                        flash("Approved & released to Client Portal!");
                      }}
                      className="px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold inline-flex items-center gap-1"
                    >
                      <CheckCircle2 className="w-3 h-3" /> Approve
                    </button>
                  )}
                  {isStaffOrCeo && a.approval_status === "pending_approval" && (
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        await apiFetch(`/api/assets/${a.id}/approve`, {
                          method: "POST",
                          body: JSON.stringify({ decision: "rejected", visible_to_client: false }),
                        });
                        await load();
                      }}
                      className="p-1.5 rounded-lg bg-red-500/20 text-red-300"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {activeAsset && (
            <div className="g-card p-2 overflow-hidden">
              {activeAsset.mime_type === "image/png" ? (
                <img src={`/api/assets/${activeAsset.id}/file`} alt={activeAsset.title} className="w-full rounded-lg" />
              ) : activeAsset.mime_type === "application/pdf" ? (
                <iframe src={`/api/assets/${activeAsset.id}/file`} title={activeAsset.title} className="w-full h-[420px] rounded-lg bg-white" />
              ) : (
                <div className="p-6 text-center text-xs text-slate-300">
                  <FileText className="w-8 h-8 mx-auto mb-2 text-blue-400" />
                  DOCX ready for Word / Google Docs — click Download above.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* SUBVIEW: PIPELINE JOURNAL */}
      {view === "journal" && isStaffOrCeo && (
        <div className="space-y-3">
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!journalNote.trim()) return;
              await apiFetch(`/api/clients/${client.case_id}/journal`, { method: "POST", body: JSON.stringify({ summary: journalNote }) });
              setJournalNote("");
              await load();
            }}
            className="flex gap-2"
          >
            <input className="g-input text-xs" placeholder="Add journal note..." value={journalNote} onChange={(e) => setJournalNote(e.target.value)} />
            <button type="submit" className="g-btn-primary px-3 text-xs shrink-0">Add</button>
          </form>
          <div className="space-y-2">
            {(client.journal || []).map((j) => (
              <div key={j.id} className="g-card p-2.5 text-xs space-y-1">
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span className="font-semibold text-blue-300 uppercase">{j.event_type.replace(/_/g, " ")} • {j.actor}</span>
                  <span>{j.created_at ? new Date(j.created_at).toLocaleString() : ""}</span>
                </div>
                <div className="text-slate-200">{j.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── 4. OFFICIAL GOVERNMENT PDF VIEWER ─────────────────────────────────────── */
function OfficialPdfsSubPanel({ initialDocKey, canUpload }: { initialDocKey?: string; canUpload: boolean }) {
  const [docs, setDocs] = useState<OfficialDocItem[]>([]);
  const [selectedKey, setSelectedKey] = useState(initialDocKey || "");
  const [showUpload, setShowUpload] = useState(false);
  const [bpTitle, setBpTitle] = useState("");
  const [bpFile, setBpFile] = useState<File | null>(null);

  const load = async () => {
    const list = await apiFetch<OfficialDocItem[]>("/api/documents/official");
    setDocs(list);
    if (!selectedKey && list.length > 0) {
      setSelectedKey(initialDocKey || list[0].doc_key);
    }
  };

  useEffect(() => {
    load().catch(() => {});
  }, []);

  useEffect(() => {
    if (initialDocKey) setSelectedKey(initialDocKey);
  }, [initialDocKey]);

  const current = docs.find((d) => d.doc_key === selectedKey) || docs[0] || null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <select className="g-input text-xs flex-1" value={current?.doc_key || ""} onChange={(e) => setSelectedKey(e.target.value)}>
          {docs.map((d) => (
            <option key={d.doc_key} value={d.doc_key}>
              [{d.agency}] {d.title}
            </option>
          ))}
        </select>
        {canUpload && (
          <button onClick={() => setShowUpload(!showUpload)} className="g-btn-ghost p-2" title="Upload PDF/DOCX Blueprint">
            <Upload className="w-4 h-4" />
          </button>
        )}
      </div>

      {showUpload && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!bpFile) return;
            const fd = new FormData();
            fd.append("file", bpFile);
            fd.append("title", bpTitle || bpFile.name);
            const r = await apiFetch<{ doc_key: string }>("/api/documents/blueprints/upload", { method: "POST", body: fd });
            setShowUpload(false);
            setBpTitle("");
            setBpFile(null);
            await load();
            setSelectedKey(r.doc_key);
          }}
          className="g-card p-3 space-y-2"
        >
          <input className="g-input text-xs" placeholder="Blueprint title" value={bpTitle} onChange={(e) => setBpTitle(e.target.value)} />
          <input type="file" accept=".pdf,.docx" onChange={(e) => setBpFile(e.target.files?.[0] || null)} className="text-xs text-slate-300" />
          <button type="submit" className="g-btn-primary w-full py-1.5 text-xs">Upload &amp; Index Fields</button>
        </form>
      )}

      {current && (
        <div className="space-y-2.5">
          <div className="g-card p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-white">{current.title}</span>
              <div className="flex gap-1.5 shrink-0">
                {current.source_url && (
                  <a href={current.source_url} target="_blank" rel="noreferrer" className="g-btn-ghost px-2 py-1 text-[11px] inline-flex items-center gap-1">
                    Source <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                <a href={current.view_url} download={current.filename} className="g-btn-primary px-2.5 py-1 text-[11px] inline-flex items-center gap-1">
                  <Download className="w-3 h-3" /> Save
                </a>
              </div>
            </div>
            <p className="text-[11px] text-slate-400">{current.description}</p>
            {current.detected_fields.length > 0 && (
              <div className="text-[10px] text-emerald-400">{current.detected_fields.length} fillable fields indexed</div>
            )}
          </div>

          {current.file_format === ".pdf" ? (
            <iframe key={current.doc_key} src={current.view_url} title={current.title} className="w-full h-[540px] rounded-xl border border-white/10 bg-white" />
          ) : (
            <div className="g-card p-6 text-center text-xs text-slate-300">
              Editable DOCX template ({current.detected_fields.length} tokens). Click Save to download.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 5. SCRAPED OFFICIAL GOV SOURCES ───────────────────────────────────────── */
function GovSourcesSubPanel({ canScrape }: { canScrape: boolean }) {
  const [sources, setSources] = useState<GovSourceItem[]>([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    apiFetch<GovSourceItem[]>("/api/sources").then(setSources).catch(() => {});
  };
  useEffect(load, []);

  return (
    <div className="space-y-3">
      {canScrape && (
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            await apiFetch("/api/sources/scrape-all", { method: "POST", body: JSON.stringify({ use_browser_fallback: false }) });
            load();
            setBusy(false);
          }}
          className="g-btn-primary w-full py-2 text-xs inline-flex items-center justify-center gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
          {busy ? "Scraping Official Gov Sites..." : "Scrape & Verify All Official Sources"}
        </button>
      )}
      <div className="space-y-2.5">
        {sources.map((s) => (
          <div key={s.source_key} className="g-card p-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase text-emerald-400">{s.agency}</span>
              <span className="text-[10px] text-slate-500">{s.scrape_status}</span>
            </div>
            <div className="text-xs font-semibold text-white">{s.name}</div>
            <a href={s.url} target="_blank" rel="noreferrer" className="text-[11px] text-blue-400 hover:underline inline-flex items-center gap-1 break-all">
              {s.url} <ExternalLink className="w-3 h-3 shrink-0" />
            </a>
            <p className="text-[11px] text-slate-400 leading-relaxed">{s.verified_summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── 6. CLEAN DATABASE TABLE EXPLORER ──────────────────────────────────────── */
function DatabaseSubPanel({ initialTable }: { initialTable: string }) {
  const [tables, setTables] = useState<Array<{ table: string; count: number }>>([]);
  const [active, setActive] = useState(initialTable);
  const [search, setSearch] = useState("");
  const [cols, setCols] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    apiFetch<Array<{ table: string; count: number }>>("/api/database/tables").then(setTables).catch(() => {});
  }, []);

  useEffect(() => {
    apiFetch<{ columns: string[]; rows: Record<string, unknown>[] }>(
      `/api/database/tables/${active}?search=${encodeURIComponent(search)}&limit=80`
    )
      .then((res) => {
        setCols(res.columns);
        setRows(res.rows);
      })
      .catch(() => {});
  }, [active, search]);

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <select className="g-input text-xs w-48" value={active} onChange={(e) => setActive(e.target.value)}>
          {tables.map((t) => (
            <option key={t.table} value={t.table}>
              {t.table} ({t.count})
            </option>
          ))}
        </select>
        <input className="g-input text-xs flex-1" placeholder="Filter rows..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="overflow-x-auto g-card max-h-[540px]">
        <table className="w-full text-left text-[11px] border-collapse">
          <thead className="bg-white/5 text-slate-300 sticky top-0">
            <tr>
              {cols.slice(0, 6).map((c) => (
                <th key={c} className="px-2.5 py-2 font-semibold whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {rows.map((r, i) => (
              <tr key={i} className="hover:bg-white/[0.04]">
                {cols.slice(0, 6).map((c) => {
                  const val = r[c] == null ? "—" : String(r[c]);
                  return (
                    <td key={c} className="px-2.5 py-2 text-slate-300 max-w-[160px] truncate" title={val}>
                      {val.startsWith("http") ? (
                        <a href={val} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
                          Link
                        </a>
                      ) : (
                        val
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── 7. INTEGRATED OBSIDIAN VAULT ──────────────────────────────────────────── */
function ObsidianSubPanel({ initialPath }: { initialPath: string }) {
  const [notes, setNotes] = useState<VaultNoteMeta[]>([]);
  const [path, setPath] = useState(initialPath);
  const [content, setContent] = useState("");
  const [links, setLinks] = useState<string[]>([]);
  const [vaultDir, setVaultDir] = useState("");
  const [saved, setSaved] = useState(false);

  const openNote = async (p: string) => {
    try {
      const n = await apiFetch<{ path: string; content: string; links: string[]; vault_dir: string }>(
        `/api/obsidian/note?path=${encodeURIComponent(p)}`
      );
      setPath(n.path);
      setContent(n.content);
      setLinks(n.links);
      setVaultDir(n.vault_dir);
    } catch {
      // ignore missing
    }
  };

  useEffect(() => {
    apiFetch<{ notes: VaultNoteMeta[] }>("/api/obsidian/notes").then((r) => setNotes(r.notes)).catch(() => {});
    openNote(initialPath);
  }, [initialPath]);

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <select className="g-input text-xs flex-1" value={path} onChange={(e) => openNote(e.target.value)}>
          {notes.map((n) => (
            <option key={n.path} value={n.path}>{n.path}</option>
          ))}
        </select>
        <button
          onClick={async () => {
            await apiFetch("/api/obsidian/note", { method: "PUT", body: JSON.stringify({ path, content }) });
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
          }}
          className="g-btn-primary px-3 text-xs inline-flex items-center gap-1 shrink-0"
        >
          <Save className="w-3.5 h-3.5" /> {saved ? "Saved" : "Save"}
        </button>
      </div>
      <div className="text-[10px] text-slate-500 truncate">Vault: <code>{vaultDir || "data/obsidian-vault"}</code></div>
      <textarea
        className="g-input font-mono text-xs leading-relaxed h-[420px]"
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      {links.length > 0 && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <Link2 className="w-3.5 h-3.5 text-slate-400" />
          {links.map((l, i) => (
            <button
              key={i}
              onClick={() => openNote(l.endsWith(".md") ? l : `${l}.md`)}
              className="px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 text-[11px] hover:bg-blue-500/25"
            >
              [[{l}]]
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 8. CEO TEAM & STAFF ACCOUNT MANAGER ───────────────────────────────────── */
function TeamSubPanel() {
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"staff" | "customer">("staff");
  const [msg, setMsg] = useState("");

  const load = () => {
    apiFetch<UserAccount[]>("/api/auth/users").then(setUsers).catch(() => {});
  };
  useEffect(load, []);

  return (
    <div className="space-y-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          await apiFetch("/api/auth/users", { method: "POST", body: JSON.stringify({ full_name: fullName, email, password, role }) });
          setFullName("");
          setEmail("");
          setPassword("");
          setMsg(`Created ${role} account.`);
          load();
        }}
        className="g-card p-3.5 space-y-2.5"
      >
        <div className="text-xs font-semibold text-white">Create Staff or Client Account (1 CEO Only)</div>
        <input className="g-input text-xs" required placeholder="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <input className="g-input text-xs" required type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="grid grid-cols-2 gap-2">
          <input className="g-input text-xs" required type="password" minLength={6} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <select className="g-input text-xs" value={role} onChange={(e) => setRole(e.target.value as "staff" | "customer")}>
            <option value="staff">Staff Specialist</option>
            <option value="customer">Client Account</option>
          </select>
        </div>
        {msg && <div className="text-xs text-emerald-400">{msg}</div>}
        <button type="submit" className="g-btn-primary w-full py-2 text-xs">Create Account</button>
      </form>

      <div className="space-y-2">
        {users.map((u) => (
          <div key={u.id} className="g-card p-3 flex items-center justify-between gap-2 text-xs">
            <div className="min-w-0">
              <div className="font-semibold text-white truncate">{u.full_name}</div>
              <div className="text-[11px] text-slate-400 truncate">{u.email}</div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="px-2 py-0.5 rounded bg-white/10 text-[10px] uppercase font-semibold text-amber-300">
                {u.role}
              </span>
              {u.role !== "ceo" && (
                <button
                  onClick={async () => {
                    await apiFetch(`/api/auth/users/${u.id}`, { method: "DELETE" });
                    load();
                  }}
                  className="p-1 text-red-400 hover:bg-red-500/15 rounded"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── 9. COMPACT EASY SETUP, SUBSCRIPTIONS, MCP & WHITE-LABEL BRANDING ──────── */
function SettingsSubPanel({
  isCeo,
  branding,
  onBrandingUpdated,
}: {
  isCeo: boolean;
  branding: BrandingConfig | null;
  onBrandingUpdated: (b: BrandingConfig) => void;
}) {
  const [hub, setHub] = useState<any>(null);
  const [provider, setProvider] = useState("auto");
  const [model, setModel] = useState("gpt-4o-mini");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [apiKey, setApiKey] = useState("");
  const [agencyName, setAgencyName] = useState(branding?.agency_name || "Jahtaria Travel Services");
  const [status, setStatus] = useState("");

  useEffect(() => {
    apiFetch<any>("/api/settings/setup-hub")
      .then((d) => {
        setHub(d);
        setProvider(d.ai_providers.active_provider || "auto");
        setModel(d.ai_providers.active_model || "gpt-4o-mini");
        setOllamaUrl(d.ai_providers.ollama.base_url || "http://localhost:11434");
      })
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-3.5">
      {/* AI Engine */}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const body: Record<string, unknown> = { ai_provider: provider, ai_model: model, ollama_base_url: ollamaUrl };
          if (apiKey.trim()) {
            if (provider === "openai") body.openai_api_key = apiKey;
            else if (provider === "anthropic") body.anthropic_api_key = apiKey;
            else if (provider === "gemini") body.gemini_api_key = apiKey;
            else if (provider === "xai_grok") body.xai_api_key = apiKey;
            else if (provider === "openrouter") body.openrouter_api_key = apiKey;
          }
          await apiFetch("/api/settings/ai-provider", { method: "POST", body: JSON.stringify(body) });
          setApiKey("");
          setStatus("AI provider settings saved (Fernet encrypted).");
        }}
        className="g-card p-3.5 space-y-2.5"
      >
        <div className="text-xs font-semibold text-white">1. AI Engine &amp; Subscriptions</div>
        <select className="g-input text-xs" value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="auto">Hermes Auto (Ollama → Keys → Local Rules)</option>
          <option value="antigravity">Antigravity Subscription (`agy` CLI)</option>
          <option value="ollama">Local Ollama (Private Desktop)</option>
          <option value="openai">OpenAI / ChatGPT API</option>
          <option value="anthropic">Anthropic / Claude API</option>
          <option value="gemini">Google Gemini API</option>
          <option value="xai_grok">xAI Grok API</option>
          <option value="openrouter">OpenRouter</option>
        </select>
        <input className="g-input text-xs" placeholder="Model ID (e.g. gpt-4o-mini)" value={model} onChange={(e) => setModel(e.target.value)} />
        {provider === "ollama" ? (
          <input className="g-input text-xs" placeholder="Ollama URL" value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
        ) : (
          <input className="g-input text-xs" type="password" placeholder="API Key (optional — encrypted at rest)" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        )}
        <button type="submit" className="g-btn-primary w-full py-2 text-xs">Save Provider</button>
      </form>

      {/* Built-in /mcp */}
      <div className="g-card p-3.5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-white">2. Built-in /mcp Server (Claude / ChatGPT / Antigravity)</span>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(hub?.claude_desktop_snippet || "");
              setStatus("Copied MCP JSON config!");
            }}
            className="text-[11px] text-blue-400 inline-flex items-center gap-1"
          >
            <Copy className="w-3 h-3" /> Copy
          </button>
        </div>
        <code className="block text-[11px] bg-black/40 p-2 rounded text-emerald-400 break-all">
          {hub?.inbound_mcp_endpoint || "http://127.0.0.1:8010/mcp"}
        </code>
      </div>

      {/* Composio Quick Toggles */}
      <div className="g-card p-3.5 space-y-2">
        <div className="text-xs font-semibold text-white">3. Composio Integrations (Gmail, Sheets, Docs, MS 365)</div>
        {(hub?.composio?.apps || []).map((a: any) => (
          <div key={a.app_id} className="flex items-center justify-between text-xs py-1">
            <span className="text-slate-300">{a.name}</span>
            <button
              onClick={async () => {
                const updated = await apiFetch("/api/settings/composio", {
                  method: "POST",
                  body: JSON.stringify({ toggle_app_id: a.app_id, connected: !a.connected }),
                });
                setHub({ ...hub, composio: updated });
              }}
              className={`px-2.5 py-1 rounded text-[11px] font-semibold ${
                a.connected ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-slate-300"
              }`}
            >
              {a.connected ? "Connected" : "Connect"}
            </button>
          </div>
        ))}
      </div>

      {/* White-Label Branding (CEO Only) */}
      {isCeo && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const b = await apiFetch<BrandingConfig>("/api/ceo/branding", {
              method: "PUT",
              body: JSON.stringify({ agency_name: agencyName }),
            });
            onBrandingUpdated(b);
            setStatus("White-label agency name updated!");
          }}
          className="g-card p-3.5 space-y-2"
        >
          <div className="text-xs font-semibold text-white">4. White-Label Agency Branding (CEO)</div>
          <input className="g-input text-xs" value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
          <button type="submit" className="g-btn-primary w-full py-1.5 text-xs">Update Branding</button>
        </form>
      )}

      {status && <div className="text-xs text-emerald-400">{status}</div>}
    </div>
  );
}
