"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowUpDown,
  Download,
  FileSpreadsheet,
  Maximize2,
  Minimize2,
  Plus,
  Upload,
  FileText,
  Image as ImageIcon,
  ExternalLink,
  Check,
  Search,
} from "lucide-react";
import { apiFetch, getStoredToken } from "@/lib/api";
import type { ClientSummary, StudioTarget } from "@/lib/types";

interface ClientSpreadsheetViewProps {
  onOpenProfile: (caseId: string) => void;
  onOpenStudio: (target: StudioTarget) => void;
  fullScreenDefault?: boolean;
  refreshNonce?: number;
}

const SORT_TABS = [
  { id: "updated_at", label: "Recent" },
  { id: "standing_score", label: "Standing %" },
  { id: "denial_risk_level", label: "Risk" },
  { id: "full_name", label: "Name A–Z" },
  { id: "monthly_gross_jmd", label: "Salary" },
  { id: "embassy_interview_date", label: "Interview" },
  { id: "pipeline_stage", label: "Stage" },
];

const STAGES = [
  "new_intake",
  "data_synced",
  "risk_audit",
  "questionnaire",
  "review_approval",
  "docs_ready",
  "embassy_scheduled",
  "completed",
];

export function ClientSpreadsheetView({
  onOpenProfile,
  onOpenStudio,
  fullScreenDefault = false,
  refreshNonce = 0,
}: ClientSpreadsheetViewProps) {
  const [rows, setRows] = useState<ClientSummary[]>([]);
  const [search, setSearch] = useState("");
  const [filterGroup, setFilterGroup] = useState<"active" | "historical" | "all">("active");
  const [sortBy, setSortBy] = useState("updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [fullScreen, setFullScreen] = useState(fullScreenDefault);
  const [editingCell, setEditingCell] = useState<{ caseId: string; field: string; value: string } | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [newClient, setNewClient] = useState({ full_name: "", visa_class: "B1/B2", parish: "Kingston & St. Andrew", us_destination: "", occupation: "" });
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = async () => {
    const qs = new URLSearchParams({ sort_by: sortBy, sort_dir: sortDir });
    if (search.trim()) qs.set("search", search.trim());
    const data = await apiFetch<ClientSummary[]>(`/api/clients?${qs.toString()}`);
    setRows(data);
  };

  useEffect(() => {
    load().catch(() => {});
  }, [search, sortBy, sortDir, refreshNonce]);

  const flash = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(""), 3500);
  };

  const visibleRows = rows.filter((c) => {
    const isRef = (c.full_name || "").startsWith("Reference Case") || (c.full_name || "").startsWith("Case C00");
    if (filterGroup === "active") return !isRef;
    if (filterGroup === "historical") return isRef;
    return true;
  });

  const toggleSort = (col: string) => {
    if (sortBy === col) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(col);
      setSortDir(col === "full_name" || col === "embassy_interview_date" ? "asc" : "desc");
    }
  };

  const commitEdit = async () => {
    if (!editingCell) return;
    const { caseId, field, value } = editingCell;
    const payload: Record<string, unknown> = {};
    if (field === "monthly_gross_jmd" || field === "monthly_net_jmd") {
      payload[field] = value.trim() === "" ? null : Number(value.replace(/,/g, ""));
    } else {
      payload[field] = value.trim();
    }
    await apiFetch(`/api/clients/${caseId}`, { method: "PATCH", body: JSON.stringify(payload) });
    setEditingCell(null);
    await load();
    flash(`Updated ${caseId} (${field.replace(/_/g, " ")}) & recalculated Good Standing!`);
  };

  const downloadExport = async (kind: "xlsx" | "csv") => {
    const token = getStoredToken();
    const res = await fetch(`/api/clients/export/${kind}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `jahtaria_clients.${kind}`;
    a.click();
    flash(`Exported jahtaria_clients.${kind}!`);
  };

  const handleImportFile = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await apiFetch<{ imported_count: number }>("/api/clients/import/spreadsheet", { method: "POST", body: fd });
    await load();
    flash(`Imported ${res.imported_count} client(s) from ${file.name}!`);
  };

  const createQuickClient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newClient.full_name.trim()) return;
    const res = await apiFetch<{ case_id: string }>("/api/clients", {
      method: "POST",
      body: JSON.stringify(newClient),
    });
    setNewClient({ full_name: "", visa_class: "B1/B2", parish: "Kingston & St. Andrew", us_destination: "", occupation: "" });
    setShowNew(false);
    await load();
    flash(`Created ${res.case_id}!`);
  };

  const EditableCell = ({ c, field, display, raw }: { c: ClientSummary; field: string; display: string; raw: string }) => {
    const isEd = editingCell?.caseId === c.case_id && editingCell.field === field;
    if (isEd) {
      if (field === "pipeline_stage") {
        return (
          <select
            autoFocus
            value={editingCell.value}
            onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
            onBlur={commitEdit}
            className="bg-[#0d0f13] border border-blue-400 rounded px-1.5 py-0.5 text-xs text-white outline-none"
          >
            {STAGES.map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
            ))}
          </select>
        );
      }
      return (
        <div className="flex items-center gap-1">
          <input
            autoFocus
            value={editingCell.value}
            onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitEdit();
              if (e.key === "Escape") setEditingCell(null);
            }}
            onBlur={commitEdit}
            className="bg-[#0d0f13] border border-blue-400 rounded px-1.5 py-0.5 text-xs text-white outline-none w-28"
          />
          <button onMouseDown={commitEdit} className="text-emerald-400"><Check className="w-3 h-3" /></button>
        </div>
      );
    }
    return (
      <button
        type="button"
        onClick={() => setEditingCell({ caseId: c.case_id, field, value: raw })}
        className="text-left hover:text-blue-300 hover:underline decoration-dotted truncate max-w-[140px] block"
        title="Click to edit inline"
      >
        {display || <span className="text-slate-600">—</span>}
      </button>
    );
  };

  const containerCls = fullScreen
    ? "fixed inset-0 z-40 bg-[#0d0f13] p-5 flex flex-col gap-3 overflow-hidden"
    : "space-y-3";

  return (
    <div className={containerCls}>
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx,.csv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleImportFile(f);
          e.target.value = "";
        }}
      />

      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-bold text-white">Client Data Spreadsheet &amp; Vault</span>
          <span className="text-[11px] text-slate-400">({visibleRows.length} shown — click any cell to edit)</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button onClick={() => setShowNew(!showNew)} className="g-btn-primary px-2.5 py-1.5 text-xs inline-flex items-center gap-1">
            <Plus className="w-3.5 h-3.5" /> New
          </button>
          <button onClick={() => fileRef.current?.click()} className="g-btn-ghost px-2.5 py-1.5 text-xs inline-flex items-center gap-1" title="Import .xlsx or .csv">
            <Upload className="w-3.5 h-3.5" /> Import
          </button>
          <button onClick={() => downloadExport("xlsx")} className="g-btn-ghost px-2.5 py-1.5 text-xs inline-flex items-center gap-1 text-emerald-300" title="Export Excel .xlsx">
            <Download className="w-3.5 h-3.5" /> Excel
          </button>
          <button onClick={() => downloadExport("csv")} className="g-btn-ghost px-2.5 py-1.5 text-xs inline-flex items-center gap-1" title="Export CSV">
            CSV
          </button>
          <button
            onClick={() => setFullScreen(!fullScreen)}
            className="g-btn-ghost px-2.5 py-1.5 text-xs inline-flex items-center gap-1 text-blue-300"
            title={fullScreen ? "Exit Full Screen" : "Expand Full Screen"}
          >
            {fullScreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            {fullScreen ? "Collapse" : "Full Screen"}
          </button>
        </div>
      </div>

      {/* Search + Active/Historical + Easy Sort Tab Bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by name, case ID, parish, occupation..."
            className="g-input text-xs py-1.5 pl-8 w-full"
          />
        </div>
        <div className="flex gap-1 bg-white/5 p-0.5 rounded-lg border border-white/10 text-[11px]">
          {(["active", "historical", "all"] as const).map((g) => (
            <button
              key={g}
              onClick={() => setFilterGroup(g)}
              className={`px-2 py-1 rounded-md capitalize transition ${
                filterGroup === g ? "bg-blue-600 text-white font-semibold" : "text-slate-400 hover:text-white"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* Easy Sort Tab Strip */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1 text-[11px]">
        <span className="text-slate-500 font-semibold mr-1 inline-flex items-center gap-1 shrink-0">
          <ArrowUpDown className="w-3 h-3" /> Sort:
        </span>
        {SORT_TABS.map((st) => {
          const active = sortBy === st.id;
          return (
            <button
              key={st.id}
              onClick={() => toggleSort(st.id)}
              className={`px-2.5 py-1 rounded-full whitespace-nowrap border transition ${
                active
                  ? "bg-blue-500/20 border-blue-400/40 text-blue-200 font-semibold"
                  : "bg-white/[0.03] border-white/10 text-slate-400 hover:text-white"
              }`}
            >
              {st.label} {active ? (sortDir === "asc" ? "↑" : "↓") : ""}
            </button>
          );
        })}
      </div>

      {toast && <div className="p-2 rounded-xl bg-emerald-500/15 border border-emerald-400/30 text-xs text-emerald-200">{toast}</div>}

      {showNew && (
        <form onSubmit={createQuickClient} className="g-card p-3 grid grid-cols-2 sm:grid-cols-6 gap-2 items-center">
          <input required className="g-input text-xs sm:col-span-2" placeholder="Full Name*" value={newClient.full_name} onChange={(e) => setNewClient({ ...newClient, full_name: e.target.value })} />
          <input className="g-input text-xs" placeholder="Visa (B1/B2)" value={newClient.visa_class} onChange={(e) => setNewClient({ ...newClient, visa_class: e.target.value })} />
          <input className="g-input text-xs" placeholder="Parish" value={newClient.parish} onChange={(e) => setNewClient({ ...newClient, parish: e.target.value })} />
          <input className="g-input text-xs" placeholder="Destination" value={newClient.us_destination} onChange={(e) => setNewClient({ ...newClient, us_destination: e.target.value })} />
          <button type="submit" className="g-btn-primary py-1.5 text-xs">Add Row</button>
        </form>
      )}

      {/* Spreadsheet Grid */}
      <div className={`g-card overflow-auto ${fullScreen ? "flex-1" : "max-h-[540px]"}`}>
        <table className="w-full text-left border-collapse text-xs">
          <thead className="sticky top-0 bg-[#151821] border-b border-white/10 text-[11px] text-slate-400 z-10">
            <tr>
              <th className="py-2.5 px-3 font-semibold">Case</th>
              <th className="py-2.5 px-3 font-semibold">Client Name</th>
              <th className="py-2.5 px-2.5 font-semibold">Visa</th>
              <th className="py-2.5 px-2.5 font-semibold">Standing</th>
              <th className="py-2.5 px-2.5 font-semibold">Stage</th>
              <th className="py-2.5 px-2.5 font-semibold">Gross JMD</th>
              <th className="py-2.5 px-2.5 font-semibold">Parish</th>
              <th className="py-2.5 px-2.5 font-semibold">DS-160</th>
              <th className="py-2.5 px-2.5 font-semibold">Passport Exp</th>
              <th className="py-2.5 px-3 font-semibold">Documents &amp; Images</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {visibleRows.map((c) => (
              <tr key={c.case_id} className="hover:bg-white/[0.03] transition">
                <td className="py-2 px-3">
                  <button
                    onClick={() => onOpenProfile(c.case_id)}
                    className="px-2 py-0.5 rounded bg-blue-500/20 hover:bg-blue-500/35 text-blue-300 font-mono text-[11px] font-semibold inline-flex items-center gap-1"
                    title="Open Client Profile & Vault"
                  >
                    {c.case_id} <ExternalLink className="w-2.5 h-2.5" />
                  </button>
                </td>
                <td className="py-2 px-3 font-medium text-white">
                  <EditableCell c={c} field="full_name" display={c.full_name || c.pseudonym} raw={c.full_name || ""} />
                </td>
                <td className="py-2 px-2.5 text-slate-300">
                  <EditableCell c={c} field="visa_class" display={c.visa_class} raw={c.visa_class || ""} />
                </td>
                <td className="py-2 px-2.5">
                  <span
                    className={`px-2 py-0.5 rounded-full font-mono text-[11px] font-bold ${
                      c.standing_score >= 80
                        ? "bg-emerald-500/15 text-emerald-300"
                        : c.standing_score >= 60
                        ? "bg-amber-500/15 text-amber-300"
                        : "bg-red-500/15 text-red-300"
                    }`}
                  >
                    {c.standing_score}%
                  </span>
                </td>
                <td className="py-2 px-2.5 text-slate-300">
                  <EditableCell c={c} field="pipeline_stage" display={c.pipeline_stage.replace(/_/g, " ")} raw={c.pipeline_stage} />
                </td>
                <td className="py-2 px-2.5 text-slate-300 font-mono">
                  <EditableCell
                    c={c}
                    field="monthly_gross_jmd"
                    display={c.monthly_gross_jmd ? c.monthly_gross_jmd.toLocaleString() : ""}
                    raw={c.monthly_gross_jmd ? String(c.monthly_gross_jmd) : ""}
                  />
                </td>
                <td className="py-2 px-2.5 text-slate-300">
                  <EditableCell c={c} field="parish" display={c.parish || ""} raw={c.parish || ""} />
                </td>
                <td className="py-2 px-2.5 font-mono text-[11px] text-slate-300">
                  <EditableCell c={c} field="ds160_confirmation_id" display={c.ds160_confirmation_id || ""} raw={c.ds160_confirmation_id || ""} />
                </td>
                <td className="py-2 px-2.5 font-mono text-[11px] text-slate-300">
                  <EditableCell c={c} field="passport_expiry" display={c.passport_expiry || ""} raw={c.passport_expiry || ""} />
                </td>
                <td className="py-2 px-3">
                  <div className="flex items-center gap-1 flex-wrap">
                    {(c.doc_previews || []).slice(0, 3).map((dp) => (
                      <button
                        key={`${dp.source_type}-${dp.id}`}
                        onClick={() =>
                          onOpenStudio({
                            source_type: dp.source_type,
                            source_id: String(dp.id),
                            case_id: c.case_id,
                            title: dp.title,
                          })
                        }
                        className="px-1.5 py-0.5 rounded bg-white/5 hover:bg-blue-500/25 border border-white/10 text-[10px] text-slate-200 inline-flex items-center gap-1 max-w-[110px]"
                        title={`Open '${dp.title}' in Full-Screen Document Studio`}
                      >
                        {dp.mime_type.startsWith("image/") ? (
                          <ImageIcon className="w-2.5 h-2.5 text-amber-300 shrink-0" />
                        ) : (
                          <FileText className="w-2.5 h-2.5 text-blue-300 shrink-0" />
                        )}
                        <span className="truncate">{dp.title}</span>
                      </button>
                    ))}
                    {(!c.doc_previews || c.doc_previews.length === 0) && (
                      <button
                        onClick={() => onOpenProfile(c.case_id)}
                        className="text-[10px] text-slate-500 hover:text-blue-300"
                      >
                        + Add Docs
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
