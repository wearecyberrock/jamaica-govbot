"use client";

import { useEffect, useState } from "react";
import {
  Database,
  FileText,
  Globe,
  ExternalLink,
  RefreshCw,
  Upload,
  Search,
  AlertTriangle,
  CheckCircle2,
  Eye,
  Download,
  Plus,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { GovSourceItem, OfficialDocItem } from "@/lib/types";

interface TableMeta {
  table: string;
  count: number;
  columns: string[];
}

export function DatabaseExplorer() {
  const [subTab, setSubTab] = useState<"pdfs" | "sources" | "tables">("pdfs");

  // Official PDFs state
  const [docs, setDocs] = useState<OfficialDocItem[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<OfficialDocItem | null>(null);
  const [uploading, setUploading] = useState(false);
  const [bpTitle, setBpTitle] = useState("");
  const [bpAgency, setBpAgency] = useState("Agency Blueprint");
  const [bpUrl, setBpUrl] = useState("");
  const [bpFile, setBpFile] = useState<File | null>(null);

  // Gov Sources state
  const [sources, setSources] = useState<GovSourceItem[]>([]);
  const [scrapingAll, setScrapingAll] = useState(false);
  const [scrapingKey, setScrapingKey] = useState<string | null>(null);
  const [newSrcName, setNewSrcName] = useState("");
  const [newSrcAgency, setNewSrcAgency] = useState("");
  const [newSrcUrl, setNewSrcUrl] = useState("");
  const [sourceMsg, setSourceMsg] = useState("");

  // SQL Tables state
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [activeTable, setActiveTable] = useState("clients");
  const [tableRows, setTableRows] = useState<Record<string, unknown>[]>([]);
  const [tableCols, setTableCols] = useState<string[]>([]);
  const [tableSearch, setTableSearch] = useState("");
  const [csvText, setCsvText] = useState("");
  const [csvStatus, setCsvStatus] = useState("");

  const loadDocs = async () => {
    const data = await apiFetch<OfficialDocItem[]>("/api/documents/official");
    setDocs(data);
    if (!selectedDoc && data.length > 0) {
      const firstPdf = data.find((d) => d.file_format === ".pdf") || data[0];
      setSelectedDoc(firstPdf);
    }
  };

  const loadSources = async () => {
    const data = await apiFetch<GovSourceItem[]>("/api/sources");
    setSources(data);
  };

  const loadTables = async () => {
    const meta = await apiFetch<TableMeta[]>("/api/database/tables");
    setTables(meta);
  };

  const loadTableRows = async (tbl: string, q: string) => {
    const res = await apiFetch<{ columns: string[]; rows: Record<string, unknown>[] }>(
      `/api/database/tables/${tbl}?search=${encodeURIComponent(q)}&limit=120`
    );
    setTableCols(res.columns);
    setTableRows(res.rows);
  };

  useEffect(() => {
    loadDocs().catch(() => {});
    loadSources().catch(() => {});
    loadTables().catch(() => {});
  }, []);

  useEffect(() => {
    if (subTab === "tables") {
      loadTableRows(activeTable, tableSearch).catch(() => {});
    }
  }, [subTab, activeTable, tableSearch]);

  const handleUploadBlueprint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bpFile) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", bpFile);
      fd.append("title", bpTitle || bpFile.name);
      fd.append("agency", bpAgency);
      fd.append("source_url", bpUrl);
      await apiFetch("/api/documents/blueprints/upload", { method: "POST", body: fd });
      setBpTitle("");
      setBpUrl("");
      setBpFile(null);
      await loadDocs();
      await loadTables();
    } finally {
      setUploading(false);
    }
  };

  const handleScrapeAll = async () => {
    setScrapingAll(true);
    setSourceMsg("");
    try {
      const res = await apiFetch<{ total_checked: number; changed_count: number }>("/api/sources/scrape-all", {
        method: "POST",
        body: JSON.stringify({ use_browser_fallback: false }),
      });
      setSourceMsg(`Checked ${res.total_checked} official sources (${res.changed_count} change diff(s) flagged).`);
      await loadSources();
    } catch (err: unknown) {
      setSourceMsg(err instanceof Error ? err.message : "Scrape failed");
    } finally {
      setScrapingAll(false);
    }
  };

  const handleScrapeOne = async (key: string) => {
    setScrapingKey(key);
    try {
      await apiFetch(`/api/sources/${key}/scrape`, {
        method: "POST",
        body: JSON.stringify({ use_browser_fallback: false }),
      });
      await loadSources();
    } finally {
      setScrapingKey(null);
    }
  };

  const handleAddSource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSrcName.trim() || !newSrcUrl.trim()) return;
    await apiFetch("/api/sources", {
      method: "POST",
      body: JSON.stringify({
        name: newSrcName,
        agency: newSrcAgency || "Official Agency",
        url: newSrcUrl,
      }),
    });
    setNewSrcName("");
    setNewSrcAgency("");
    setNewSrcUrl("");
    await loadSources();
  };

  const handleImportCsv = async () => {
    if (!csvText.trim()) return;
    const res = await apiFetch<{ imported_count: number; skipped_count: number }>("/api/database/import-csv", {
      method: "POST",
      body: JSON.stringify({ csv_text: csvText }),
    });
    setCsvStatus(`Imported ${res.imported_count} client row(s) (${res.skipped_count} skipped).`);
    setCsvText("");
    await loadTables();
    await loadTableRows(activeTable, tableSearch);
  };

  return (
    <div className="space-y-5">
      {/* Top Sub-Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-ja-green">
            Database Window, Official PDFs &amp; Scraped Government Sources
          </h2>
          <p className="text-xs text-slate-600">
            Verify live government links, view official PICA/U.S. Dept. of State PDFs inline, upload custom blueprints, and query all database tables cleanly.
          </p>
        </div>

        <div className="flex items-center gap-1.5 bg-white p-1.5 rounded-xl border border-slate-200 shadow-sm">
          <button
            onClick={() => setSubTab("pdfs")}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition ${
              subTab === "pdfs" ? "bg-ja-green text-ja-goldBright" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <FileText className="w-4 h-4" /> Official PDFs &amp; Blueprints ({docs.length})
          </button>
          <button
            onClick={() => setSubTab("sources")}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition ${
              subTab === "sources" ? "bg-ja-green text-ja-goldBright" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Globe className="w-4 h-4" /> Scraped Gov Sources ({sources.length})
          </button>
          <button
            onClick={() => setSubTab("tables")}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition ${
              subTab === "tables" ? "bg-ja-green text-ja-goldBright" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Database className="w-4 h-4" /> Live Database Tables ({tables.length})
          </button>
        </div>
      </div>

      {/* TAB 1: OFFICIAL PDFs & EMBEDDED VIEWER */}
      {subTab === "pdfs" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-5 space-y-4">
            <div className="ja-card p-4 max-h-[540px] overflow-y-auto space-y-2.5">
              <div className="text-xs font-extrabold uppercase tracking-wider text-ja-navy pb-2 border-b">
                Downloaded Official Forms &amp; Blueprints
              </div>
              {docs.map((d) => {
                const active = selectedDoc?.doc_key === d.doc_key;
                return (
                  <div
                    key={d.doc_key}
                    onClick={() => setSelectedDoc(d)}
                    className={`p-3 rounded-xl border cursor-pointer transition ${
                      active
                        ? "border-ja-green bg-ja-greenLight shadow-sm"
                        : "border-slate-200 bg-white hover:border-ja-green/50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="inline-block text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-ja-navy/10 text-ja-navy mb-1">
                          {d.agency} • {d.file_format.toUpperCase()}
                        </span>
                        <h4 className="font-bold text-sm text-slate-900">{d.title}</h4>
                      </div>
                      <span className="text-[11px] text-slate-500 shrink-0">
                        {(d.size_bytes / 1024).toFixed(0)} KB
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 mt-1 line-clamp-2">{d.description}</p>
                    <div className="flex items-center justify-between mt-2 text-[11px]">
                      <span className="text-slate-500">
                        {d.detected_fields.length} indexed field(s)
                      </span>
                      {d.source_url && (
                        <a
                          href={d.source_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-ja-green font-bold inline-flex items-center gap-1 hover:underline"
                        >
                          Official Link <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Upload Custom PDF / DOCX Blueprint */}
            <form onSubmit={handleUploadBlueprint} className="ja-card p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-ja-green">
                <Upload className="w-4 h-4" /> Upload Official PDF or DOCX Blueprint
              </div>
              <input
                className="ja-input"
                placeholder="Document title (e.g., Custom Embassy Cover Letter)"
                value={bpTitle}
                onChange={(e) => setBpTitle(e.target.value)}
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  className="ja-input"
                  placeholder="Agency / Source"
                  value={bpAgency}
                  onChange={(e) => setBpAgency(e.target.value)}
                />
                <input
                  className="ja-input"
                  placeholder="Official reference URL"
                  value={bpUrl}
                  onChange={(e) => setBpUrl(e.target.value)}
                />
              </div>
              <input
                type="file"
                accept=".pdf,.docx"
                onChange={(e) => setBpFile(e.target.files?.[0] || null)}
                className="block w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-ja-greenLight file:text-ja-green file:font-bold"
              />
              <button
                type="submit"
                disabled={!bpFile || uploading}
                className="ja-btn-primary w-full py-2 text-xs disabled:opacity-50"
              >
                {uploading ? "Inspecting & Indexing Blueprint..." : "Upload & Auto-Detect Fillable Fields"}
              </button>
            </form>
          </div>

          {/* Right Pane: Embedded Live PDF Viewer */}
          <div className="lg:col-span-7">
            {selectedDoc ? (
              <div className="ja-card p-4 flex flex-col h-[760px]">
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b">
                  <div>
                    <h3 className="font-extrabold text-base text-ja-green flex items-center gap-2">
                      <Eye className="w-4 h-4" /> {selectedDoc.title}
                    </h3>
                    <p className="text-xs text-slate-500">
                      File: <code>{selectedDoc.filename}</code> • SHA-256: <code>{selectedDoc.sha256.slice(0, 14)}…</code>
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedDoc.source_url && (
                      <a
                        href={selectedDoc.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded-lg border border-ja-navy text-ja-navy text-xs font-bold inline-flex items-center gap-1 hover:bg-ja-navy hover:text-white transition"
                      >
                        Verify Official URL <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                    <a
                      href={selectedDoc.view_url}
                      target="_blank"
                      rel="noreferrer"
                      download={selectedDoc.filename}
                      className="ja-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1"
                    >
                      <Download className="w-3.5 h-3.5" /> Open / Download
                    </a>
                  </div>
                </div>

                {selectedDoc.detected_fields.length > 0 && (
                  <div className="py-2 flex flex-wrap gap-1.5 border-b">
                    <span className="text-[11px] font-bold text-slate-500 mr-1">Indexed Fields:</span>
                    {selectedDoc.detected_fields.slice(0, 12).map((fld) => (
                      <span
                        key={fld}
                        className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border"
                      >
                        {fld}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex-1 mt-3 rounded-xl overflow-hidden border bg-slate-100">
                  {selectedDoc.file_format === ".pdf" ? (
                    <iframe
                      key={selectedDoc.doc_key}
                      src={selectedDoc.view_url}
                      title={selectedDoc.title}
                      className="w-full h-full border-0"
                    />
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center p-8 text-center gap-3">
                      <FileText className="w-12 h-12 text-ja-green" />
                      <h4 className="font-bold text-slate-800">{selectedDoc.title}</h4>
                      <p className="text-xs text-slate-600 max-w-md">{selectedDoc.description}</p>
                      <a href={selectedDoc.view_url} className="ja-btn-primary px-4 py-2 text-xs">
                        Download Editable DOCX Blueprint
                      </a>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="ja-card p-10 text-center text-sm text-slate-500">
                Select any official PDF or blueprint on the left to inspect it inline.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: SCRAPED OFFICIAL SOURCES & LIVE LINKS */}
      {subTab === "sources" && (
        <div className="space-y-4">
          <div className="ja-card p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-extrabold text-sm text-ja-green">
                Live Official U.S. Embassy Kingston, Dept. of State, PICA &amp; RGD Reference Registry
              </h3>
              <p className="text-xs text-slate-500">
                Every rule in our Good Standing Engine links back to these official pages with SHA-256 change-diff monitoring.
              </p>
              {sourceMsg && <p className="text-xs font-bold text-ja-navy mt-1">{sourceMsg}</p>}
            </div>
            <button
              onClick={handleScrapeAll}
              disabled={scrapingAll}
              className="ja-btn-primary px-4 py-2 text-xs inline-flex items-center gap-2 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${scrapingAll ? "animate-spin" : ""}`} />
              {scrapingAll ? "Scraping Official Sites..." : "Scrape & Verify All Official Sources"}
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sources.map((s) => (
              <div key={s.source_key} className="ja-card p-4 flex flex-col justify-between gap-3">
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-ja-greenLight text-ja-green">
                        {s.agency} • {s.category}
                      </span>
                      <h4 className="font-extrabold text-sm text-slate-900 mt-1">{s.name}</h4>
                    </div>
                    {s.diff_alert ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900">
                        <AlertTriangle className="w-3 h-3" /> Change Alert
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                        <CheckCircle2 className="w-3 h-3" /> Verified
                      </span>
                    )}
                  </div>

                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-bold text-ja-navy hover:underline inline-flex items-center gap-1 mt-1 break-all"
                  >
                    {s.url} <ExternalLink className="w-3 h-3 shrink-0" />
                  </a>

                  <p className="text-xs text-slate-700 mt-2 leading-relaxed">{s.verified_summary}</p>

                  {s.key_rules.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {s.key_rules.map((r, idx) => (
                        <li key={idx} className="text-[11px] text-slate-600 flex items-start gap-1.5">
                          <span className="text-ja-green font-bold">•</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {s.diff_alert && s.diff_summary && (
                    <div className="mt-2 p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900">
                      {s.diff_summary}
                    </div>
                  )}
                </div>

                <div className="pt-2 border-t flex items-center justify-between text-[11px] text-slate-500">
                  <span>
                    Status: <b className="text-slate-700">{s.scrape_status}</b> • Hash: <code>{s.content_hash}</code>
                  </span>
                  <button
                    onClick={() => handleScrapeOne(s.source_key)}
                    disabled={scrapingKey === s.source_key}
                    className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-ja-green hover:text-white font-bold text-slate-700 transition inline-flex items-center gap-1"
                  >
                    <RefreshCw className={`w-3 h-3 ${scrapingKey === s.source_key ? "animate-spin" : ""}`} />
                    Refresh
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Add Custom Official URL */}
          <form onSubmit={handleAddSource} className="ja-card p-4 grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Source Title</label>
              <input className="ja-input" placeholder="e.g., PICA Visa Extensions" value={newSrcName} onChange={(e) => setNewSrcName(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Agency</label>
              <input className="ja-input" placeholder="e.g., PICA Jamaica" value={newSrcAgency} onChange={(e) => setNewSrcAgency(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Official URL</label>
              <input className="ja-input" placeholder="https://..." value={newSrcUrl} onChange={(e) => setNewSrcUrl(e.target.value)} />
            </div>
            <button type="submit" className="ja-btn-primary py-2.5 text-xs inline-flex items-center justify-center gap-1.5">
              <Plus className="w-4 h-4" /> Add &amp; Scrape Source
            </button>
          </form>
        </div>
      )}

      {/* TAB 3: CLEAN INTERACTIVE DATABASE TABLE EXPLORER */}
      {subTab === "tables" && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {tables.map((t) => (
              <button
                key={t.table}
                onClick={() => setActiveTable(t.table)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition ${
                  activeTable === t.table
                    ? "bg-ja-green text-ja-goldBright border-ja-green"
                    : "bg-white text-slate-700 border-slate-200 hover:border-ja-green"
                }`}
              >
                {t.table} <span className="opacity-75">({t.count})</span>
              </button>
            ))}
          </div>

          <div className="ja-card p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="relative flex-1 min-w-[240px]">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  className="ja-input pl-9"
                  placeholder={`Search rows inside '${activeTable}'...`}
                  value={tableSearch}
                  onChange={(e) => setTableSearch(e.target.value)}
                />
              </div>
              <span className="text-xs font-bold text-slate-500">
                Showing {tableRows.length} row(s) in <code>{activeTable}</code>
              </span>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-200 max-h-[460px]">
              <table className="w-full text-left border-collapse text-xs">
                <thead className="bg-ja-green text-white sticky top-0">
                  <tr>
                    {tableCols.map((c) => (
                      <th key={c} className="px-3 py-2.5 font-bold whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {tableRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-ja-greenLight/40">
                      {tableCols.map((c) => {
                        const val = row[c];
                        const str = val === null || val === undefined ? "—" : String(val);
                        const isUrl = str.startsWith("http://") || str.startsWith("https://");
                        return (
                          <td key={c} className="px-3 py-2 max-w-[280px] truncate" title={str}>
                            {isUrl ? (
                              <a href={str} target="_blank" rel="noreferrer" className="text-ja-navy font-semibold hover:underline">
                                {str}
                              </a>
                            ) : (
                              str
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {tableRows.length === 0 && (
                    <tr>
                      <td colSpan={Math.max(1, tableCols.length)} className="px-4 py-8 text-center text-slate-400">
                        No matching rows found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Quick CSV / Google Sheet Importer */}
          <div className="ja-card p-4 space-y-2.5">
            <h4 className="font-extrabold text-xs uppercase tracking-wider text-ja-navy">
              Quick Company Spreadsheet / CSV Client Import
            </h4>
            <p className="text-xs text-slate-600">
              Paste CSV rows exported from Google Sheets or Excel (headers: <code>full_name,email,phone,parish,visa_class,purpose_of_trip,us_destination,occupation,employer</code>) to batch-create client cases.
            </p>
            <textarea
              rows={3}
              className="ja-input font-mono text-xs"
              placeholder="full_name,email,parish,visa_class,purpose_of_trip,us_destination,occupation&#10;Devon Brown,devon@example.com,St. Catherine,B1/B2,Family visit,Miami FL,Accountant"
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
            />
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-700">{csvStatus}</span>
              <button onClick={handleImportCsv} className="ja-btn-primary px-4 py-2 text-xs">
                Import Rows Into Pipeline
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
