"use client";

import { useState } from "react";
import { ArrowUpDown, Download, ExternalLink, FileSpreadsheet, Search } from "lucide-react";
import type { ChatDataTablePayload } from "@/lib/types";

export function ChatDataTableCard({
  data,
  onSelectCase,
  onOpenSpreadsheet,
}: {
  data: ChatDataTablePayload;
  onSelectCase: (caseId: string) => void;
  onOpenSpreadsheet: () => void;
}) {
  const [query, setQuery] = useState("");
  const [sortCol, setSortCol] = useState(data.sort_by || "standing_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">(data.sort_dir === "asc" ? "asc" : "desc");

  const filtered = (data.rows || []).filter((r) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return Object.values(r).some((v) => String(v ?? "").toLowerCase().includes(q));
  });

  const sorted = [...filtered].sort((a, b) => {
    const va = a[sortCol];
    const vb = b[sortCol];
    const na = typeof va === "number" ? va : Number(va);
    const nb = typeof vb === "number" ? vb : Number(vb);
    let cmp = 0;
    if (!Number.isNaN(na) && !Number.isNaN(nb) && va !== "" && vb !== "") {
      cmp = na - nb;
    } else {
      cmp = String(va ?? "").localeCompare(String(vb ?? ""));
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  const toggleSort = (col: string) => {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortCol(col);
      setSortDir("desc");
    }
  };

  const exportCsv = () => {
    const hdr = data.columns.map((c) => c.label).join(",");
    const body = sorted
      .map((r) => data.columns.map((c) => `"${String(r[c.key] ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([`${hdr}\n${body}`], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "jahtaria_filtered_clients.csv";
    a.click();
  };

  const chartItems = data.chart?.items || [];
  const maxChartVal = Math.max(1, ...chartItems.map((i) => i.value));

  return (
    <div className="mt-3 rounded-2xl bg-[#141720] border border-white/12 shadow-xl overflow-hidden text-slate-200">
      <div className="px-4 py-2.5 border-b border-white/10 bg-white/[0.02] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-semibold text-white">{data.title}</div>
          <div className="text-[11px] text-slate-400">{data.subtitle}</div>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={exportCsv} className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-[11px] text-slate-300 inline-flex items-center gap-1">
            <Download className="w-3 h-3" /> CSV
          </button>
          <button onClick={onOpenSpreadsheet} className="px-2.5 py-1 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 text-[11px] text-blue-200 inline-flex items-center gap-1">
            <FileSpreadsheet className="w-3 h-3" /> Full Spreadsheet
          </button>
        </div>
      </div>

      {/* Mini Bar Chart */}
      {chartItems.length > 0 && (
        <div className="px-4 py-2.5 border-b border-white/10 bg-black/20 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{data.chart?.title}</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1">
            {chartItems.map((it) => (
              <div key={it.label} className="flex items-center gap-2 text-[11px]">
                <span className="w-24 truncate text-slate-300">{it.label}</span>
                <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.max(8, (it.value / maxChartVal) * 100)}%`, background: it.color }} />
                </div>
                <span className="w-6 text-right font-mono text-slate-400">{it.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="px-3 py-2 border-b border-white/5">
        <div className="relative">
          <Search className="w-3 h-3 text-slate-500 absolute left-2.5 top-2" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Quick filter rows..."
            className="g-input text-[11px] py-1 pl-7 w-full"
          />
        </div>
      </div>

      {/* Interactive Table */}
      <div className="overflow-x-auto max-h-72 overflow-y-auto">
        <table className="w-full text-left border-collapse text-[11px]">
          <thead className="sticky top-0 bg-[#181c27] text-slate-400 border-b border-white/10">
            <tr>
              {data.columns.map((col) => (
                <th key={col.key} className="py-2 px-2.5 font-semibold whitespace-nowrap">
                  <button onClick={() => toggleSort(col.key)} className="inline-flex items-center gap-1 hover:text-white">
                    {col.label}
                    <ArrowUpDown className="w-2.5 h-2.5 opacity-60" />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {sorted.slice(0, 30).map((row, ri) => {
              const cid = String(row.case_id || "");
              return (
                <tr
                  key={cid || ri}
                  onClick={() => cid && onSelectCase(cid)}
                  className="hover:bg-blue-500/10 cursor-pointer transition"
                >
                  {data.columns.map((col) => {
                    const val = row[col.key];
                    if (col.key === "case_id") {
                      return (
                        <td key={col.key} className="py-1.5 px-2.5 font-mono text-blue-300 font-semibold whitespace-nowrap">
                          <span className="inline-flex items-center gap-1">
                            {String(val)} <ExternalLink className="w-2.5 h-2.5" />
                          </span>
                        </td>
                      );
                    }
                    if (col.key === "standing_score") {
                      const n = Number(val || 0);
                      return (
                        <td key={col.key} className={`py-1.5 px-2.5 font-mono font-bold ${n >= 80 ? "text-emerald-300" : n >= 60 ? "text-amber-300" : "text-red-300"}`}>
                          {n}%
                        </td>
                      );
                    }
                    if (col.key === "monthly_gross_jmd") {
                      return (
                        <td key={col.key} className="py-1.5 px-2.5 font-mono text-slate-300 whitespace-nowrap">
                          {val ? Number(val).toLocaleString() : "—"}
                        </td>
                      );
                    }
                    return (
                      <td key={col.key} className="py-1.5 px-2.5 text-slate-300 whitespace-nowrap max-w-[140px] truncate">
                        {String(val ?? "—").replace(/_/g, " ")}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
