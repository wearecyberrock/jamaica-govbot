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
  Lightbulb,
  MessageSquarePlus,
  Maximize2,
  Minimize2,
  ArrowUpDown,
  FileSpreadsheet,
  FolderOpen,
  Package,
  Scissors,
  Zap,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type {
  BrandingConfig,
  ChatQuestionnairePayload,
  ClientDetail,
  ClientDocumentItem,
  ClientSummary,
  GovSourceItem,
  OfficialDocItem,
  StudioTarget,
  UserAccount,
  VaultNoteMeta,
} from "@/lib/types";
import { ClientSpreadsheetView } from "./ClientSpreadsheetView";
import { GmailAutomationPanel } from "./GmailAutomationPanel";

export interface PanelRequest {
  panel:
    | "ceo_analytics"
    | "clients_list"
    | "spreadsheet"
    | "gmail"
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
  refreshNonce?: number;
  panelWidth?: number;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
  onNavigatePanel: (req: PanelRequest) => void;
  onSelectCaseForChat: (caseId: string) => void;
  onImportQuestionnaireToChat?: (payload: ChatQuestionnairePayload) => void;
  onOpenStudio?: (target: StudioTarget) => void;
  onBrandingUpdated: (b: BrandingConfig) => void;
  onClose: () => void;
}

export function RightSidePanel({
  request,
  user,
  branding,
  recentLinks,
  refreshNonce = 0,
  panelWidth,
  isExpanded = false,
  onToggleExpand,
  onNavigatePanel,
  onSelectCaseForChat,
  onImportQuestionnaireToChat,
  onOpenStudio,
  onBrandingUpdated,
  onClose,
}: RightSidePanelProps) {
  const isCeo = user.role === "ceo";
  const isStaffOrCeo = user.role === "ceo" || user.role === "staff";

  return (
    <aside
      style={isExpanded ? undefined : panelWidth ? { width: `${panelWidth}px` } : undefined}
      className={`${
        isExpanded
          ? "fixed inset-0 z-40 w-screen h-screen"
          : panelWidth
          ? "max-w-[85vw] h-full shrink-0"
          : "w-full lg:w-[48%] xl:w-[46%] max-w-[680px] h-full shrink-0"
      } bg-[#0f1311] border-l border-[#e5b84b]/12 flex flex-col`}
    >
      <div className="h-[2px] w-full ja-ribbon shrink-0 opacity-80" />
      {/* Top Panel Bar */}
      <div className="h-12 px-4 border-b border-white/10 flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
          <span className="text-xs font-semibold text-slate-200 truncate">
            {request.title || request.panel.replace(/_/g, " ").toUpperCase()}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {onToggleExpand && (
            <button
              onClick={onToggleExpand}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
              title={isExpanded ? "Restore Side Panel Width" : "Expand Side Panel Full Screen"}
            >
              {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            title="Close Side Panel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
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
        {request.panel === "ceo_analytics" && isCeo && (
          <CeoAnalyticsSubPanel
            onOpenCase={(cid) => {
              onSelectCaseForChat(cid);
              onNavigatePanel({ panel: "client", case_id: cid, subview: "overview", title: `Case ${cid}` });
            }}
          />
        )}
        {request.panel === "clients_list" && isStaffOrCeo && (
          <ClientsListSubPanel
            onOpenCase={(cid) => {
              onSelectCaseForChat(cid);
              onNavigatePanel({ panel: "client", case_id: cid, subview: "overview", title: `Case ${cid}` });
            }}
            onOpenSpreadsheet={() => onNavigatePanel({ panel: "spreadsheet", title: "Client Spreadsheet & Vault" })}
          />
        )}
        {request.panel === "spreadsheet" && isStaffOrCeo && (
          <ClientSpreadsheetView
            refreshNonce={refreshNonce}
            onOpenProfile={(cid) => {
              onSelectCaseForChat(cid);
              onNavigatePanel({ panel: "client", case_id: cid, subview: "overview", title: `Case ${cid}` });
            }}
            onOpenStudio={(t) => onOpenStudio?.(t)}
          />
        )}
        {request.panel === "gmail" && isStaffOrCeo && (
          <GmailAutomationPanel
            refreshNonce={refreshNonce}
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
            refreshNonce={refreshNonce}
            onImportQuestionnaireToChat={onImportQuestionnaireToChat}
            onOpenStudio={onOpenStudio}
            onOpenObsidian={(path) => onNavigatePanel({ panel: "obsidian", path, title: `Obsidian — ${path}` })}
          />
        )}
        {request.panel === "official_pdfs" && (
          <OfficialPdfsSubPanel
            initialDocKey={request.doc_key}
            canUpload={isStaffOrCeo}
            activeCaseId={request.case_id}
            onOpenStudio={onOpenStudio}
          />
        )}
        {request.panel === "gov_sources" && <GovSourcesSubPanel canScrape={isStaffOrCeo} refreshNonce={refreshNonce} />}
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

/* ── 2. CLEAN CLIENTS LIST (ACTIVE vs HISTORICAL + EASY SORT TAB) ─────────── */
function ClientsListSubPanel({
  onOpenCase,
  onOpenSpreadsheet,
}: {
  onOpenCase: (cid: string) => void;
  onOpenSpreadsheet: () => void;
}) {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [filterMode, setFilterMode] = useState<"active" | "historical" | "all">("active");
  const [sortBy, setSortBy] = useState("updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [newVisa, setNewVisa] = useState("B1/B2");
  const [newDest, setNewDest] = useState("");
  const [newPurpose, setNewPurpose] = useState("");

  const load = () => {
    const qs = new URLSearchParams({ sort_by: sortBy, sort_dir: sortDir });
    if (search.trim()) qs.set("search", search.trim());
    apiFetch<ClientSummary[]>(`/api/clients?${qs.toString()}`)
      .then(setClients)
      .catch(() => {});
  };

  useEffect(load, [search, sortBy, sortDir]);

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSortBy(col);
      setSortDir(col === "full_name" || col === "embassy_interview_date" ? "asc" : "desc");
    }
  };

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
        <input className="g-input text-xs flex-1" placeholder="Search cases, names, parish..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <button onClick={onOpenSpreadsheet} className="g-btn-ghost px-2.5 py-2 text-xs inline-flex items-center gap-1 text-emerald-300 shrink-0" title="Open Editable Spreadsheet">
          <FileSpreadsheet className="w-3.5 h-3.5" /> Sheet
        </button>
        <button onClick={() => setShowNew(!showNew)} className="g-btn-primary px-3 py-2 text-xs inline-flex items-center gap-1 shrink-0">
          <Plus className="w-3.5 h-3.5" /> New
        </button>
      </div>

      {/* Easy Sort Tab Bar */}
      <div className="flex items-center gap-1 overflow-x-auto pb-0.5 text-[11px]">
        <span className="text-slate-500 inline-flex items-center gap-1 mr-1 shrink-0">
          <ArrowUpDown className="w-3 h-3" /> Sort:
        </span>
        {[
          ["updated_at", "Recent"],
          ["standing_score", "Standing"],
          ["denial_risk_level", "Risk"],
          ["full_name", "Name"],
          ["monthly_gross_jmd", "Salary"],
          ["embassy_interview_date", "Interview"],
        ].map(([id, lbl]) => {
          const act = sortBy === id;
          return (
            <button
              key={id}
              onClick={() => toggleSort(id)}
              className={`px-2 py-0.5 rounded-full border whitespace-nowrap transition ${
                act ? "bg-blue-500/20 border-blue-400/40 text-blue-200 font-semibold" : "bg-white/[0.03] border-white/10 text-slate-400 hover:text-white"
              }`}
            >
              {lbl} {act ? (sortDir === "asc" ? "↑" : "↓") : ""}
            </button>
          );
        })}
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
  refreshNonce = 0,
  onImportQuestionnaireToChat,
  onOpenStudio,
  onOpenObsidian,
}: {
  caseId: string;
  initialSubview: string;
  initialPreviewAssetId: number | null;
  isStaffOrCeo: boolean;
  refreshNonce?: number;
  onImportQuestionnaireToChat?: (payload: ChatQuestionnairePayload) => void;
  onOpenStudio?: (target: StudioTarget) => void;
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
  const [genCount, setGenCount] = useState("5");
  const [genBusy, setGenBusy] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [openTipIds, setOpenTipIds] = useState<Record<number, boolean>>({});
  const [vaultCat, setVaultCat] = useState("all");
  const [officialDocs, setOfficialDocs] = useState<OfficialDocItem[]>([]);
  const [fillDocKey, setFillDocKey] = useState("");
  const [vaultBusy, setVaultBusy] = useState(false);

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
  }, [caseId, refreshNonce]);

  useEffect(() => {
    if (isStaffOrCeo) {
      apiFetch<OfficialDocItem[]>("/api/documents/official")
        .then((list) => {
          setOfficialDocs(list);
          if (!fillDocKey && list.length > 0) setFillDocKey(list[0].doc_key);
        })
        .catch(() => {});
    }
  }, [isStaffOrCeo]);

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
            <option value="overview">
              Good Standing &amp; Risk Flags ({client.risk_flags.filter((f) => f.category !== "ai_questionnaire").length})
            </option>
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
          {client.risk_flags
            .filter((f) => f.category !== "ai_questionnaire")
            .map((f) => (
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

      {/* SUBVIEW: INTAKE FORM & AI-IN-THE-LOOP QUESTIONNAIRE */}
      {view === "intake" && (
        <div className="space-y-3">
          <div className="g-card p-3.5 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-white">
                Interactive Questionnaire ({client.risk_flags.filter((f) => f.follow_up_question).length})
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                {onImportQuestionnaireToChat && (
                  <button
                    type="button"
                    disabled={importBusy || genBusy}
                    onClick={async () => {
                      if (importBusy) return;
                      setImportBusy(true);
                      try {
                        let payload = await apiFetch<ChatQuestionnairePayload>(`/api/clients/${client.case_id}/questionnaire`);
                        if (payload.items.length === 0) {
                          const gen = await apiFetch<{ questionnaire: ChatQuestionnairePayload }>(
                            `/api/clients/${client.case_id}/questionnaire/generate`,
                            { method: "POST", body: JSON.stringify({ count: 5, focus: "live readiness & risk gaps" }) }
                          );
                          payload = gen.questionnaire;
                          await load();
                        }
                        onImportQuestionnaireToChat(payload);
                        flash(`Imported ${payload.items.length} question(s) into chat!`);
                      } finally {
                        setImportBusy(false);
                      }
                    }}
                    className="px-2.5 py-1 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 border border-blue-400/30 text-blue-200 text-[11px] font-medium inline-flex items-center gap-1 transition disabled:opacity-50"
                    title="Pop this exact questionnaire cleanly into the chat area"
                  >
                    <MessageSquarePlus className="w-3 h-3" /> {importBusy ? "Importing…" : "Import into Chat"}
                  </button>
                )}
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={genCount}
                  onChange={(e) => setGenCount(e.target.value)}
                  className="w-14 bg-white/5 border border-white/10 rounded-lg px-1.5 py-1 text-[11px] text-center text-slate-200 outline-none"
                  title="How many questions to generate (e.g. 5, 25, 100, 500)"
                />
                <button
                  type="button"
                  disabled={genBusy}
                  onClick={async () => {
                    const n = Math.max(1, Math.min(parseInt(genCount, 10) || 5, 1000));
                    setGenBusy(true);
                    try {
                      await apiFetch(`/api/clients/${client.case_id}/questionnaire/generate`, {
                        method: "POST",
                        body: JSON.stringify({ count: n, focus: "live readiness & risk gaps" }),
                      });
                      await load();
                      flash(`Generated ${n} tailored question(s)!`);
                    } finally {
                      setGenBusy(false);
                    }
                  }}
                  className="g-btn-primary px-2.5 py-1 text-[11px] inline-flex items-center gap-1 disabled:opacity-40"
                >
                  <Sparkles className="w-3 h-3" /> {genBusy ? "Generating…" : "Generate"}
                </button>
              </div>
            </div>

            <div className="space-y-2 max-h-[380px] overflow-y-auto pr-0.5">
              {client.risk_flags
                .filter((f) => f.follow_up_question)
                .map((f, fi) => {
                  const tipOpen = Boolean(openTipIds[f.id]);
                  const opts = f.options || [];
                  return (
                    <div key={f.id} className="p-2.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[11px] font-semibold text-slate-200 leading-snug">
                          <span className="text-slate-500 font-mono mr-1">#{fi + 1}</span>
                          {f.follow_up_question}
                        </span>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={() => setOpenTipIds((prev) => ({ ...prev, [f.id]: !prev[f.id] }))}
                            className={`p-1 rounded-md transition ${
                              tipOpen ? "bg-amber-500/25 text-amber-200" : "text-amber-300/80 hover:bg-amber-500/15"
                            }`}
                            title="Tips & Explanation"
                          >
                            <Lightbulb className="w-3.5 h-3.5" />
                          </button>
                          {f.resolved && <span className="text-[10px] text-emerald-400 font-bold">Cleared</span>}
                        </div>
                      </div>

                      {tipOpen && (
                        <div className="p-2 rounded-lg bg-amber-500/[0.08] border border-amber-400/20 text-[11px] space-y-1">
                          <div><b className="text-amber-300">Why:</b> <span className="text-slate-300">{f.detail}</span></div>
                          {f.suggested_fix && (
                            <div><b className="text-emerald-300">Tip:</b> <span className="text-slate-300">{f.suggested_fix}</span></div>
                          )}
                        </div>
                      )}

                      {opts.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {opts.map((opt, oi) => (
                            <button
                              key={oi}
                              type="button"
                              onClick={async () => {
                                await apiFetch(`/api/clients/${client.case_id}/questionnaire`, {
                                  method: "POST",
                                  body: JSON.stringify({ flag_id: f.id, client_response: opt, mark_resolved: isStaffOrCeo }),
                                });
                                await load();
                                flash("Choice saved & Good Standing updated live!");
                              }}
                              className={`px-2 py-0.5 rounded-lg text-[10px] border transition ${
                                f.client_response === opt
                                  ? "bg-blue-500/25 border-blue-400/50 text-white"
                                  : "bg-white/[0.03] hover:bg-white/10 border-white/10 text-slate-300"
                              }`}
                            >
                              {opt}
                            </button>
                          ))}
                        </div>
                      )}

                      <div className="flex gap-1.5">
                        <input
                          className="g-input text-xs py-1 flex-1"
                          defaultValue={f.client_response || ""}
                          key={`${f.id}-${f.client_response}`}
                          placeholder="Type truthful answer & press Enter..."
                          onKeyDown={async (e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              const val = (e.target as HTMLInputElement).value;
                              await apiFetch(`/api/clients/${client.case_id}/questionnaire`, {
                                method: "POST",
                                body: JSON.stringify({ flag_id: f.id, client_response: val, mark_resolved: isStaffOrCeo }),
                              });
                              await load();
                              flash("Answer saved & Good Standing updated live!");
                            }
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>

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
            <div className="text-xs font-semibold text-slate-300">Client Profile Fields</div>
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
        </div>
      )}

      {/* SUBVIEW: INTERVIEW PREP & VOICE MOCK */}
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
              <div className="flex items-start justify-between gap-2">
                <div className="text-xs font-semibold text-blue-300 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 shrink-0" /> &ldquo;{mockQ.question_text}&rdquo;
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    const token = localStorage.getItem("jahtaria_govbot_token") || "";
                    const r = await fetch("/api/voice/speak", {
                      method: "POST",
                      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
                      body: JSON.stringify({ text: mockQ.question_text, persona: "officer_us" }),
                    });
                    if (r.ok) {
                      const audio = new Audio(URL.createObjectURL(await r.blob()));
                      audio.play();
                    }
                  }}
                  className="g-btn-ghost px-2 py-1 text-[11px] shrink-0"
                  title="Hear U.S. Consular Officer ask this question"
                >
                  🔊 Officer Voice
                </button>
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

      {/* SUBVIEW: CLIENT DOCUMENT & IMAGE VAULT, OFFICIAL AUTO-FILL, 92% RGD & EMBASSY PACKET */}
      {(view === "blueprints" || view === "docs") && (
        <div className="space-y-3.5">
          {/* Categorized Client Vault Upload + Official Form AI Auto-Fill + 1-Click Embassy Packet */}
          {isStaffOrCeo && (
            <div className="g-card p-3 space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-white inline-flex items-center gap-1.5">
                  <FolderOpen className="w-3.5 h-3.5 text-blue-400" /> Client Document &amp; Image Vault ({(client.documents || []).length})
                </span>
                <div className="flex items-center gap-1.5">
                  <label className="g-btn-primary px-2.5 py-1 text-[11px] inline-flex items-center gap-1 cursor-pointer">
                    <Upload className="w-3 h-3" /> {vaultBusy ? "Scanning…" : "Upload & Scan"}
                    <input
                      type="file"
                      multiple
                      accept=".pdf,.png,.jpg,.jpeg,.webp,.docx"
                      className="hidden"
                      onChange={async (e) => {
                        const fls = Array.from(e.target.files || []);
                        if (!fls.length) return;
                        setVaultBusy(true);
                        try {
                          for (const f of fls) {
                            const fd = new FormData();
                            fd.append("file", f);
                            fd.append("auto_scan", "true");
                            await apiFetch(`/api/clients/${client.case_id}/documents/upload`, { method: "POST", body: fd });
                          }
                          await load();
                          flash(`Uploaded & AI-scanned ${fls.length} file(s) into ${client.case_id}'s Vault!`);
                        } finally {
                          setVaultBusy(false);
                          e.target.value = "";
                        }
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={async () => {
                      const r = await apiFetch<{ id: number; included_count: number }>(`/api/clients/${client.case_id}/embassy-packet`, {
                        method: "POST",
                        body: JSON.stringify({ bundle_format: "pdf" }),
                      });
                      setPreviewId(r.id);
                      await load();
                      flash(`Exported Embassy Packet PDF (${r.included_count} doc(s))!`);
                    }}
                    className="px-2.5 py-1 rounded-lg bg-emerald-600/25 hover:bg-emerald-600/40 border border-emerald-400/30 text-emerald-200 text-[11px] font-semibold inline-flex items-center gap-1"
                    title="Merge approved forms & vault docs into 1 printable Embassy Packet PDF"
                  >
                    <Package className="w-3 h-3" /> Packet PDF
                  </button>
                </div>
              </div>

              {/* Select Official Gov PDF -> AI Auto-Fill into Client Vault */}
              {officialDocs.length > 0 && (
                <div className="flex gap-1.5">
                  <select className="g-input text-[11px] py-1 flex-1" value={fillDocKey} onChange={(e) => setFillDocKey(e.target.value)}>
                    {officialDocs.map((d) => (
                      <option key={d.doc_key} value={d.doc_key}>
                        [{d.agency}] {d.title}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={vaultBusy || !fillDocKey}
                    onClick={async () => {
                      setVaultBusy(true);
                      try {
                        const r = await apiFetch<{ document: ClientDocumentItem }>(`/api/clients/${client.case_id}/documents/fill-official`, {
                          method: "POST",
                          body: JSON.stringify({ doc_key: fillDocKey }),
                        });
                        await load();
                        flash(`AI-filled '${r.document.title}' — opening Full-Screen Studio!`);
                        onOpenStudio?.({ source_type: "vault", source_id: String(r.document.id), case_id: client.case_id, title: r.document.title });
                      } finally {
                        setVaultBusy(false);
                      }
                    }}
                    className="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/30 text-amber-200 text-[11px] font-semibold inline-flex items-center gap-1 shrink-0"
                  >
                    <Sparkles className="w-3 h-3" /> AI Fill Form
                  </button>
                </div>
              )}

              {/* Category Filter Pills */}
              <div className="flex gap-1 overflow-x-auto text-[10px] pb-0.5">
                {[
                  ["all", "All"],
                  ["passport_id", "Passport / ID"],
                  ["financial_payslips", "Financial"],
                  ["rgd_civil", "RGD Civil"],
                  ["embassy_forms", "Embassy Forms"],
                  ["photos_other", "Photos / Other"],
                ].map(([cid, lbl]) => (
                  <button
                    key={cid}
                    onClick={() => setVaultCat(cid)}
                    className={`px-2 py-0.5 rounded-full whitespace-nowrap border ${
                      vaultCat === cid ? "bg-blue-500/20 border-blue-400/40 text-blue-200 font-semibold" : "bg-white/[0.03] border-white/10 text-slate-400"
                    }`}
                  >
                    {lbl}
                  </button>
                ))}
              </div>

              {/* Vault Documents List */}
              {(client.documents || []).filter((d) => vaultCat === "all" || d.category === vaultCat).length > 0 && (
                <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
                  {(client.documents || [])
                    .filter((d) => vaultCat === "all" || d.category === vaultCat)
                    .map((d) => (
                      <div key={d.id} className="p-2 rounded-xl bg-white/[0.03] border border-white/10 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-white truncate">
                              {d.title}{" "}
                              {d.version_number > 1 && <span className="text-[10px] text-emerald-300 font-mono">v{d.version_number}</span>}
                            </div>
                            <div className="text-[10px] text-slate-400 truncate">
                              {d.category.replace(/_/g, " ")} • {d.ai_summary || d.filename}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              type="button"
                              onClick={() => onOpenStudio?.({ source_type: "vault", source_id: String(d.id), case_id: client.case_id, title: d.title })}
                              className="px-2 py-1 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 text-blue-200 text-[10px] font-semibold inline-flex items-center gap-1"
                              title="Open Full-Screen Preview, Text Editor & Signature Studio"
                            >
                              <Maximize2 className="w-3 h-3" /> Edit/Sign
                            </button>
                            <button
                              type="button"
                              onClick={async () => {
                                await apiFetch(`/api/documents/vault/${d.id}/rgd-92`, { method: "POST" });
                                await load();
                                flash("Created 92% RGD Kingston-compliant PDF in Vault!");
                              }}
                              className="p-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/30 text-amber-300"
                              title="1-Click 92% RGD Photocopy Scale Converter"
                            >
                              <Scissors className="w-3 h-3" />
                            </button>
                            <a href={d.file_url} download={d.filename} className="p-1 rounded-lg bg-white/5 hover:bg-white/15 text-slate-300" title="Download">
                              <Download className="w-3 h-3" />
                            </a>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}

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
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenStudio?.({ source_type: "asset", source_id: String(a.id), case_id: client.case_id, title: a.title });
                    }}
                    className="px-2 py-1 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 text-blue-200 text-[10px] font-semibold inline-flex items-center gap-1"
                    title="Full-Screen Preview, Edit & Sign"
                  >
                    <Maximize2 className="w-3 h-3" /> Studio
                  </button>
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
function OfficialPdfsSubPanel({
  initialDocKey,
  canUpload,
  activeCaseId,
  onOpenStudio,
}: {
  initialDocKey?: string;
  canUpload: boolean;
  activeCaseId?: string;
  onOpenStudio?: (target: StudioTarget) => void;
}) {
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
                <button
                  type="button"
                  onClick={() =>
                    onOpenStudio?.({
                      source_type: "official",
                      source_id: current.doc_key,
                      case_id: activeCaseId || null,
                      title: current.title,
                    })
                  }
                  className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-semibold inline-flex items-center gap-1"
                >
                  <Maximize2 className="w-3 h-3" /> Full-Screen Edit &amp; Sign
                </button>
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
function GovSourcesSubPanel({ canScrape, refreshNonce = 0 }: { canScrape: boolean; refreshNonce?: number }) {
  const [sources, setSources] = useState<GovSourceItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [newName, setNewName] = useState("");
  const [newAgency, setNewAgency] = useState("");

  const load = () => {
    apiFetch<GovSourceItem[]>("/api/sources").then(setSources).catch(() => {});
  };
  useEffect(load, [refreshNonce]);

  const addSource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUrl.trim()) return;
    setBusy(true);
    try {
      await apiFetch("/api/sources", {
        method: "POST",
        body: JSON.stringify({
          url: newUrl.trim(),
          name: newName.trim() || newUrl.trim().replace(/^https?:\/\//, "").split("/")[0],
          agency: newAgency.trim() || "Official Agency",
          category: newUrl.includes(".jm") ? "jamaica_civil" : "us_dos",
        }),
      });
      setNewUrl("");
      setNewName("");
      setNewAgency("");
      setShowAdd(false);
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {canScrape && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                await apiFetch("/api/sources/scrape-all", { method: "POST", body: JSON.stringify({ use_browser_fallback: false }) });
                load();
                setBusy(false);
              }}
              className="g-btn-primary flex-1 py-2 text-xs inline-flex items-center justify-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
              {busy ? "Scraping Official Gov Sites..." : "Scrape & Verify All"}
            </button>
            <button
              type="button"
              onClick={() => setShowAdd(!showAdd)}
              className="g-btn-ghost px-3 py-2 text-xs inline-flex items-center gap-1 shrink-0"
            >
              <Plus className="w-3.5 h-3.5" /> Add URL
            </button>
          </div>
          {showAdd && (
            <form onSubmit={addSource} className="g-card p-3 space-y-2">
              <input required className="g-input text-xs" placeholder="https://jis.gov.jm/" value={newUrl} onChange={(e) => setNewUrl(e.target.value)} />
              <div className="grid grid-cols-2 gap-2">
                <input className="g-input text-xs" placeholder="Title (optional)" value={newName} onChange={(e) => setNewName(e.target.value)} />
                <input className="g-input text-xs" placeholder="Agency (optional)" value={newAgency} onChange={(e) => setNewAgency(e.target.value)} />
              </div>
              <button type="submit" disabled={busy} className="g-btn-primary w-full py-1.5 text-xs">
                Save &amp; Scrape Official Source
              </button>
            </form>
          )}
        </div>
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

/* ── 8. CEO TEAM & STAFF ACCOUNT MANAGER (Username + Reset Password!) ──────── */
function TeamSubPanel() {
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryPin, setRecoveryPin] = useState("");
  const [role, setRole] = useState<"staff" | "customer">("staff");
  const [msg, setMsg] = useState("");
  const [resetTargetId, setResetTargetId] = useState<number | null>(null);
  const [resetNewPw, setResetNewPw] = useState("");
  const [resetNewPin, setResetNewPin] = useState("");

  const load = () => {
    apiFetch<UserAccount[]>("/api/auth/users").then(setUsers).catch(() => {});
  };
  useEffect(load, []);

  return (
    <div className="space-y-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          await apiFetch("/api/auth/users", {
            method: "POST",
            body: JSON.stringify({
              full_name: fullName,
              username,
              email,
              password,
              recovery_pin: recoveryPin,
              role,
            }),
          });
          setFullName("");
          setUsername("");
          setEmail("");
          setPassword("");
          setRecoveryPin("");
          setMsg(`Created ${role} account.`);
          load();
        }}
        className="g-card p-3.5 space-y-2.5"
      >
        <div className="text-xs font-semibold text-white">Create Staff or Client Account (Username Login)</div>
        <div className="grid grid-cols-2 gap-2">
          <input className="g-input text-xs" required placeholder="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          <input className="g-input text-xs" required placeholder="Username (e.g. keisha_staff)" value={username} onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <input className="g-input text-xs" required type="password" minLength={6} placeholder="Password (min 6)" value={password} onChange={(e) => setPassword(e.target.value)} />
          <input className="g-input text-xs" placeholder="Recovery PIN (4+ digits)" value={recoveryPin} onChange={(e) => setRecoveryPin(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <input className="g-input text-xs" type="email" placeholder="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} />
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
          <div key={u.id} className="g-card p-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-semibold text-white truncate">
                  {u.full_name}{" "}
                  <span className="text-[11px] font-mono text-emerald-300">@{u.username || u.email.split("@")[0]}</span>
                </div>
                <div className="text-[11px] text-slate-400 truncate">
                  {u.email} {u.all_tiers ? "• ALL TIERS" : ""}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="px-2 py-0.5 rounded bg-white/10 text-[10px] uppercase font-semibold text-amber-300">
                  {u.role}
                </span>
                <button
                  onClick={() => {
                    setResetTargetId(resetTargetId === u.id ? null : u.id);
                    setResetNewPw("");
                    setResetNewPin("");
                  }}
                  className="px-2 py-1 rounded bg-white/5 hover:bg-white/15 text-[10px] text-slate-200"
                  title="Reset user password or PIN"
                >
                  Reset PW
                </button>
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
            {resetTargetId === u.id && (
              <div className="pt-2 border-t border-white/10 flex flex-wrap gap-2">
                <input
                  className="g-input text-xs flex-1 min-w-[120px]"
                  type="password"
                  placeholder="New password (min 6)"
                  value={resetNewPw}
                  onChange={(e) => setResetNewPw(e.target.value)}
                />
                <input
                  className="g-input text-xs w-28"
                  placeholder="New PIN (opt)"
                  value={resetNewPin}
                  onChange={(e) => setResetNewPin(e.target.value)}
                />
                <button
                  onClick={async () => {
                    if (resetNewPw.length < 6) return;
                    await apiFetch(`/api/auth/users/${u.id}/reset-password`, {
                      method: "POST",
                      body: JSON.stringify({ new_password: resetNewPw, new_recovery_pin: resetNewPin }),
                    });
                    setMsg(`Reset password for @${u.username || u.email}.`);
                    setResetTargetId(null);
                  }}
                  className="g-btn-primary px-3 py-1 text-[11px]"
                >
                  Save
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── 9. REAL SUBSCRIPTION OAUTH, VOICE STUDIO, COMPOSIO, MCP & WHITE-LABEL ─── */
function SettingsSubPanel({
  isCeo,
  branding,
  onBrandingUpdated,
}: {
  isCeo: boolean;
  branding: BrandingConfig | null;
  onBrandingUpdated: (b: BrandingConfig) => void;
}) {
  const [catalog, setCatalog] = useState<any>(null);
  const [hub, setHub] = useState<any>(null);
  const [voice, setVoice] = useState<any>(null);

  // OAuth interactive flow states
  const [codexFlow, setCodexFlow] = useState<{ flow_id: string; user_code: string; verification_uri: string; status: string } | null>(null);
  const [agyFlow, setAgyFlow] = useState<{ flow_id: string; auth_url: string } | null>(null);
  const [agyCodeInput, setAgyCodeInput] = useState("");
  const [claudeTok, setClaudeTok] = useState("");
  const [showClaudeBox, setShowClaudeBox] = useState(false);
  const [customModelId, setCustomModelId] = useState("");
  const [refreshingModels, setRefreshingModels] = useState(false);

  // API key & ClawLink / Composio quick save
  const [apiProv, setApiProv] = useState("gemini");
  const [apiKeyVal, setApiKeyVal] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [composioKeyInput, setComposioKeyInput] = useState("");
  const [clawUrl, setClawUrl] = useState("");
  const [clawToken, setClawToken] = useState("");
  const [clawChannel, setClawChannel] = useState("");

  // Voice settings
  const [voiceEngine, setVoiceEngine] = useState("edge");
  const [voicePersona, setVoicePersona] = useState("advisor_ja");
  const [elevenKey, setElevenKey] = useState("");
  const [elevenVoiceId, setElevenVoiceId] = useState("JBFqnCBsd6RMkjVDRZzb");
  const [fishKey, setFishKey] = useState("");
  const [fishVoiceId, setFishVoiceId] = useState("");

  // Branding
  const [agencyName, setAgencyName] = useState(branding?.agency_name || "Jahtaria Travel Services");
  const [status, setStatus] = useState("");

  const loadAll = async () => {
    const [cat, h, v] = await Promise.all([
      apiFetch<any>("/api/models/catalog"),
      apiFetch<any>("/api/settings/setup-hub"),
      apiFetch<any>("/api/voice/config"),
    ]);
    setCatalog(cat);
    setHub(h);
    setVoice(v);
    setOllamaUrl(h?.ai_providers?.ollama?.base_url || "http://localhost:11434");
    setClawUrl(h?.clawlink?.base_url || "");
    setClawChannel(h?.clawlink?.channel || "");
    setVoiceEngine(v?.engine || "edge");
    setVoicePersona(v?.default_persona || "advisor_ja");
    setElevenVoiceId(v?.elevenlabs_voice_id || "JBFqnCBsd6RMkjVDRZzb");
    setFishVoiceId(v?.fish_voice_id || "");
  };

  useEffect(() => {
    loadAll().catch(() => {});
  }, []);

  // Poll ChatGPT Codex device-code login automatically
  useEffect(() => {
    if (!codexFlow || codexFlow.status !== "pending") return;
    const timer = setInterval(async () => {
      try {
        const res = await apiFetch<{ status: string; error?: string }>(`/api/oauth/poll/${codexFlow.flow_id}`);
        if (res.status === "connected") {
          setCodexFlow({ ...codexFlow, status: "connected" });
          setStatus("ChatGPT / Codex Subscription connected!");
          loadAll();
        } else if (res.status === "error" || res.status === "expired") {
          setCodexFlow({ ...codexFlow, status: res.status });
          setStatus(res.error || "Sign-in expired. Try again.");
        }
      } catch {
        // ignore poll glitch
      }
    }, 4000);
    return () => clearInterval(timer);
  }, [codexFlow]);

  const startCodex = async () => {
    setStatus("Requesting ChatGPT Codex sign-in code...");
    const res = await apiFetch<any>("/api/oauth/start", { method: "POST", body: JSON.stringify({ provider: "openai-codex" }) });
    if (res.ok) {
      setCodexFlow({ flow_id: res.flow_id, user_code: res.user_code, verification_uri: res.verification_uri, status: "pending" });
      setStatus("Enter the code on OpenAI's page — this panel will auto-connect as soon as you approve.");
    } else {
      setStatus(res.error || "Failed to start ChatGPT Codex flow.");
    }
  };

  const startAntigravity = async () => {
    const res = await apiFetch<any>("/api/oauth/start", { method: "POST", body: JSON.stringify({ provider: "antigravity" }) });
    if (res.ok) {
      setAgyFlow({ flow_id: res.flow_id, auth_url: res.auth_url });
      setStatus("Open the Google Sign-In link, then paste the redirected URL or code below.");
    }
  };

  const finishAntigravity = async () => {
    if (!agyFlow || !agyCodeInput.trim()) return;
    const res = await apiFetch<any>("/api/oauth/exchange", {
      method: "POST",
      body: JSON.stringify({ flow_id: agyFlow.flow_id, code_or_url: agyCodeInput }),
    });
    if (res.ok) {
      setAgyFlow(null);
      setAgyCodeInput("");
      setStatus("Antigravity Google account connected!");
      loadAll();
    } else {
      setStatus(res.error || "Token exchange failed.");
    }
  };

  const testVoice = async () => {
    setStatus("Generating sample voice audio...");
    try {
      const token = localStorage.getItem("jahtaria_govbot_token") || "";
      const res = await fetch("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          text: "Good day! Your U.S. visa preparation voice engine is connected and ready for Kingston Embassy interview practice.",
          persona: voicePersona,
          engine: voiceEngine,
        }),
      });
      if (!res.ok) throw new Error("Voice test failed");
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audio.play();
      setStatus("Playing live voice preview!");
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Voice test failed");
    }
  };

  const downloadMcpJson = () => {
    const snippet = hub?.claude_desktop_snippet || "{}";
    const blob = new Blob([snippet], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "jahtaria-visa-mcp-config.json";
    a.click();
    setStatus("Downloaded jahtaria-visa-mcp-config.json!");
  };

  const subItems = catalog?.groups?.[0]?.items || [];

  return (
    <div className="space-y-3.5">
      {status && (
        <div className="p-2.5 rounded-xl bg-blue-500/15 border border-blue-400/30 text-xs text-blue-200">{status}</div>
      )}

      {/* 1. RECOMMENDED: CHATGPT / OPENAI CODEX OAUTH */}
      <div className="g-card p-3.5 space-y-2.5 border-emerald-400/35">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white">1. ChatGPT / OpenAI OAuth</span>
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 text-[10px] font-bold">
              RECOMMENDED
            </span>
          </div>
          {subItems.find((i: any) => i.provider === "openai-codex")?.connected ? (
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[11px] font-semibold">Connected</span>
          ) : (
            <button
              onClick={async () => {
                await startCodex();
              }}
              className="g-btn-primary px-3 py-1.5 text-[11px] shrink-0"
            >
              1-Click Sign In with ChatGPT
            </button>
          )}
        </div>
        <div className="text-[11px] text-slate-400">
          Fastest setup: uses your ChatGPT Plus / Pro account via device OAuth (no API billing needed). You can also paste any API key or MCP link directly in chat!
        </div>
        {codexFlow && codexFlow.status === "pending" && (
          <div className="p-2.5 rounded-lg bg-black/40 border border-blue-400/30 space-y-2 text-xs">
            <div className="text-slate-300">Copy this code &amp; approve on OpenAI&apos;s sign-in page:</div>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <code className="text-base font-bold tracking-widest text-amber-300">{codexFlow.user_code}</code>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(codexFlow.user_code);
                    setStatus("Copied code! Paste it on OpenAI's page.");
                  }}
                  className="p-1 rounded bg-white/10 hover:bg-white/20 text-slate-200"
                  title="Copy Code"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
              </div>
              <a
                href={codexFlow.verification_uri}
                target="_blank"
                rel="noreferrer"
                className="g-btn-primary px-3 py-1.5 text-[11px] inline-flex items-center gap-1"
              >
                Open OpenAI Sign-In <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <div className="text-[10px] text-slate-400">Waiting for approval… connects automatically in seconds.</div>
          </div>
        )}
      </div>

      {/* 2. COMPOSIO APPS (GMAIL, GOOGLE SHEETS, DOCS, MICROSOFT 365 / ONEDRIVE) */}
      <div className="g-card p-3.5 space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold text-white">2. Composio Hub (Gmail, Google Sheets, Docs, Microsoft 365)</span>
          {hub?.composio?.api_key_configured && (
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-semibold">Key Saved</span>
          )}
        </div>
        <div className="flex gap-1.5">
          <input
            type="password"
            value={composioKeyInput}
            onChange={(e) => setComposioKeyInput(e.target.value)}
            placeholder={hub?.composio?.api_key_configured ? `Saved (${hub.composio.api_key_masked}) — paste to update` : "Paste Composio API Key (or paste right in chat!)"}
            className="g-input text-xs flex-1"
          />
          <button
            type="button"
            onClick={async () => {
              if (!composioKeyInput.trim()) return;
              const updated = await apiFetch("/api/settings/composio", { method: "POST", body: JSON.stringify({ api_key: composioKeyInput.trim() }) });
              setHub({ ...hub, composio: updated });
              setComposioKeyInput("");
              setStatus("Composio API key saved!");
            }}
            className="g-btn-primary px-3 text-xs shrink-0"
          >
            Save
          </button>
        </div>
        <div className="space-y-1">
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
      </div>

      {/* 3. CLAWLINK EASY CONNECTION */}
      <div className="g-card p-3.5 space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold text-white inline-flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-300" /> 3. ClawLink Connection
          </span>
          {hub?.clawlink?.configured && (
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-semibold">Connected</span>
          )}
        </div>
        <div className="text-[11px] text-slate-400">
          Connect your ClawLink endpoint &amp; token here — or simply paste your ClawLink URL/token directly into chat.
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input className="g-input text-xs" placeholder="ClawLink URL (https://...)" value={clawUrl} onChange={(e) => setClawUrl(e.target.value)} />
          <input
            className="g-input text-xs"
            type="password"
            placeholder={hub?.clawlink?.token_masked ? `Token (${hub.clawlink.token_masked})` : "ClawLink Token / Secret"}
            value={clawToken}
            onChange={(e) => setClawToken(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <input className="g-input text-xs flex-1" placeholder="Optional Channel / Workspace ID" value={clawChannel} onChange={(e) => setClawChannel(e.target.value)} />
          <button
            type="button"
            onClick={async () => {
              const r = await apiFetch<{ note: string }>("/api/settings/clawlink", {
                method: "POST",
                body: JSON.stringify({ base_url: clawUrl, token: clawToken || undefined, channel: clawChannel }),
              });
              setClawToken("");
              setStatus(`ClawLink: ${r.note}`);
              loadAll();
            }}
            className="g-btn-primary px-3.5 text-xs shrink-0"
          >
            Connect &amp; Test
          </button>
        </div>
      </div>

      {/* 4. OTHER OAUTH SUBSCRIPTIONS (CLAUDE PRO/MAX & ANTIGRAVITY) */}
      <div className="g-card p-3.5 space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold text-white">4. Other OAuth Subscriptions (Claude &amp; Antigravity)</span>
          <button
            onClick={async () => {
              const r = await apiFetch<{ count: number; imported: string[] }>("/api/oauth/import-local", { method: "POST" });
              setStatus(r.count ? `Auto-imported local sign-in(s): ${r.imported.join(", ")}` : "No local CLI tokens found on this PC.");
              loadAll();
            }}
            className="text-[11px] text-blue-400 hover:underline"
          >
            Auto-Detect Local Sign-In
          </button>
        </div>

        {/* Claude Pro / Max Subscription */}
        <div className="p-2.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs">
            <div>
              <div className="font-semibold text-white">Claude Pro / Max Subscription</div>
              <div className="text-[11px] text-slate-400">Connect via Claude Code sign-in or `claude setup-token`</div>
            </div>
            {subItems.find((i: any) => i.provider === "claude-sub")?.connected ? (
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[11px] font-semibold">Connected</span>
            ) : (
              <button onClick={() => setShowClaudeBox(!showClaudeBox)} className="g-btn-primary px-3 py-1.5 text-[11px] shrink-0">
                Connect Claude
              </button>
            )}
          </div>
          {showClaudeBox && (
            <div className="flex gap-2">
              <input className="g-input text-xs" type="password" placeholder="Paste Claude OAuth / setup-token..." value={claudeTok} onChange={(e) => setClaudeTok(e.target.value)} />
              <button
                onClick={async () => {
                  await apiFetch("/api/oauth/claude-token", { method: "POST", body: JSON.stringify({ token: claudeTok }) });
                  setClaudeTok("");
                  setShowClaudeBox(false);
                  setStatus("Claude subscription connected!");
                  loadAll();
                }}
                className="g-btn-primary px-3 text-xs shrink-0"
              >
                Save
              </button>
            </div>
          )}
        </div>

        {/* Antigravity Google OAuth */}
        <div className="p-2.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs">
            <div>
              <div className="font-semibold text-white">Antigravity (Google OAuth / CLI)</div>
              <div className="text-[11px] text-slate-400">Sign in with your Google Antigravity account or local `agy.exe`</div>
            </div>
            {subItems.find((i: any) => i.provider === "antigravity")?.connected ? (
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[11px] font-semibold">Connected</span>
            ) : (
              <button onClick={startAntigravity} className="g-btn-primary px-3 py-1.5 text-[11px] shrink-0">
                Sign In with Google
              </button>
            )}
          </div>
          {agyFlow && (
            <div className="p-2.5 rounded-lg bg-black/40 border border-blue-400/30 space-y-2 text-xs">
              <a href={agyFlow.auth_url} target="_blank" rel="noreferrer" className="g-btn-primary px-3 py-1.5 text-[11px] inline-flex items-center gap-1">
                1. Open Google OAuth Sign-In <ExternalLink className="w-3 h-3" />
              </a>
              <div className="flex gap-2">
                <input className="g-input text-xs" placeholder="2. Paste redirected URL or auth code here..." value={agyCodeInput} onChange={(e) => setAgyCodeInput(e.target.value)} />
                <button onClick={finishAntigravity} className="g-btn-primary px-3 text-xs shrink-0">Link</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 5. CLOUD API KEYS & LOCAL OLLAMA */}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const body: Record<string, unknown> = { ai_provider: apiProv, ollama_base_url: ollamaUrl };
          if (apiKeyVal.trim()) {
            const keyField: Record<string, string> = {
              openai: "openai_api_key",
              anthropic: "anthropic_api_key",
              gemini: "gemini_api_key",
              xai_grok: "xai_api_key",
              openrouter: "openrouter_api_key",
            };
            if (keyField[apiProv]) body[keyField[apiProv]] = apiKeyVal.trim();
          }
          await apiFetch("/api/settings/ai-provider", { method: "POST", body: JSON.stringify(body) });
          setApiKeyVal("");
          setStatus("Saved encrypted provider key.");
          loadAll();
        }}
        className="g-card p-3.5 space-y-2.5"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-bold text-white">5. Cloud API Keys, Local Ollama &amp; Live Models</div>
          <button
            type="button"
            disabled={refreshingModels}
            onClick={async () => {
              setRefreshingModels(true);
              try {
                await apiFetch("/api/models/refresh", { method: "POST" });
                await loadAll();
                setStatus("Refreshed live flagship models from all connected providers!");
              } finally {
                setRefreshingModels(false);
              }
            }}
            className="text-[11px] text-emerald-400 hover:underline inline-flex items-center gap-1 shrink-0 disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${refreshingModels ? "animate-spin" : ""}`} />
            {refreshingModels ? "Refreshing…" : "Refresh Live Models"}
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[145px_1fr_auto] gap-2">
          <select className="g-input text-xs" value={apiProv} onChange={(e) => setApiProv(e.target.value)}>
            <option value="gemini">Google Gemini</option>
            <option value="antigravity">Antigravity</option>
            <option value="openai-codex">ChatGPT / Codex</option>
            <option value="openai">OpenAI API</option>
            <option value="anthropic">Anthropic API</option>
            <option value="xai_grok">xAI Grok</option>
            <option value="openrouter">OpenRouter</option>
            <option value="ollama">Local Ollama</option>
          </select>
          {apiProv === "ollama" ? (
            <input className="g-input text-xs min-w-0" value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} placeholder="http://localhost:11434" />
          ) : (
            <input className="g-input text-xs min-w-0" type="password" value={apiKeyVal} onChange={(e) => setApiKeyVal(e.target.value)} placeholder="Paste encrypted API key (or leave blank)..." />
          )}
          <button type="submit" className="g-btn-primary px-3.5 text-xs shrink-0">Save</button>
        </div>
        <div className="flex items-center gap-2 pt-1 border-t border-white/10">
          <input
            className="g-input text-xs flex-1 min-w-0"
            value={customModelId}
            onChange={(e) => setCustomModelId(e.target.value)}
            placeholder="Custom Model ID (e.g. gemini-4-neon, gpt-5.4, claude-opus-5-5)..."
          />
          <button
            type="button"
            disabled={!customModelId.trim()}
            onClick={async () => {
              await apiFetch("/api/models/select", {
                method: "POST",
                body: JSON.stringify({ provider: apiProv, model: customModelId.trim() }),
              });
              setStatus(`Activated custom model ${apiProv} · ${customModelId.trim()}!`);
              setCustomModelId("");
              loadAll();
            }}
            className="g-btn-ghost px-3 py-1.5 text-[11px] text-[#e5b84b] shrink-0 disabled:opacity-40"
          >
            Use Model
          </button>
        </div>
      </form>

      {/* 3. VOICE ENGINE (FREE EDGE NEURAL + ELEVENLABS FLASH + FISH AUDIO) */}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          await apiFetch("/api/voice/config", {
            method: "POST",
            body: JSON.stringify({
              engine: voiceEngine,
              default_persona: voicePersona,
              elevenlabs_api_key: elevenKey || undefined,
              elevenlabs_voice_id: elevenVoiceId,
              fish_api_key: fishKey || undefined,
              fish_voice_id: fishVoiceId,
            }),
          });
          setElevenKey("");
          setFishKey("");
          setStatus("Voice Engine settings saved!");
          loadAll();
        }}
        className="g-card p-3.5 space-y-2.5"
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-white">6. Voice Engine (Mock Interviews &amp; Hands-Free AI)</span>
          <button type="button" onClick={testVoice} className="text-[11px] text-emerald-400 hover:underline font-semibold">
            Test Voice 🔊
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select className="g-input text-xs" value={voiceEngine} onChange={(e) => setVoiceEngine(e.target.value)}>
            <option value="edge">Free Neural Voices (Built-in Edge)</option>
            <option value="elevenlabs">ElevenLabs Flash API</option>
            <option value="fish">Fish Audio API</option>
          </select>
          <select className="g-input text-xs" value={voicePersona} onChange={(e) => setVoicePersona(e.target.value)}>
            {(voice?.personas || []).map((p: any) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
        {voiceEngine === "elevenlabs" && (
          <div className="grid grid-cols-2 gap-2">
            <input className="g-input text-xs" type="password" placeholder={voice?.elevenlabs_configured ? `ElevenLabs (${voice.elevenlabs_key_masked})` : "ElevenLabs API Key"} value={elevenKey} onChange={(e) => setElevenKey(e.target.value)} />
            <input className="g-input text-xs" placeholder="ElevenLabs Voice ID" value={elevenVoiceId} onChange={(e) => setElevenVoiceId(e.target.value)} />
          </div>
        )}
        {voiceEngine === "fish" && (
          <div className="grid grid-cols-2 gap-2">
            <input className="g-input text-xs" type="password" placeholder={voice?.fish_configured ? `Fish Key (${voice.fish_key_masked})` : "Fish Audio API Key"} value={fishKey} onChange={(e) => setFishKey(e.target.value)} />
            <input className="g-input text-xs" placeholder="Fish Reference Voice ID" value={fishVoiceId} onChange={(e) => setFishVoiceId(e.target.value)} />
          </div>
        )}
        <button type="submit" className="g-btn-primary w-full py-1.5 text-xs">Save Voice Settings</button>
      </form>

      {/* 4. BUILT-IN /mcp EXPORT (Connect Claude Desktop, ChatGPT & Antigravity on Your PC) */}
      <div className="g-card p-3.5 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-white">7. Connect Antigravity / Claude / ChatGPT (/mcp)</span>
          <div className="flex gap-2">
            <button
              onClick={() => {
                navigator.clipboard?.writeText(hub?.claude_desktop_snippet || "");
                setStatus("Copied MCP JSON config!");
              }}
              className="text-[11px] text-blue-400 inline-flex items-center gap-1"
            >
              <Copy className="w-3 h-3" /> Copy
            </button>
            <button onClick={downloadMcpJson} className="text-[11px] text-emerald-400 inline-flex items-center gap-1">
              <Download className="w-3 h-3" /> Export JSON
            </button>
          </div>
        </div>
        <code className="block text-[11px] bg-black/40 p-2 rounded text-emerald-400 break-all">
          {hub?.inbound_mcp_endpoint || "http://127.0.0.1:8010/mcp"}
        </code>
      </div>

      {/* 6. VOICE ENGINE, MCP & WHITE-LABEL BRANDING */}
      {/* (Duplicate Composio card removed — Composio is now promoted to #2 above!) */}

      {isCeo && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const b = await apiFetch<BrandingConfig>("/api/ceo/branding", {
              method: "PUT",
              body: JSON.stringify({ agency_name: agencyName }),
            });
            onBrandingUpdated(b);
            setStatus("White-label agency branding updated!");
          }}
          className="g-card p-3.5 space-y-2"
        >
          <div className="text-xs font-semibold text-white">8. White-Label Agency Branding (CEO)</div>
          <div className="flex gap-2">
            <input className="g-input text-xs flex-1" value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
            <button type="submit" className="g-btn-primary px-3 text-xs shrink-0">Save</button>
          </div>
        </form>
      )}
    </div>
  );
}
