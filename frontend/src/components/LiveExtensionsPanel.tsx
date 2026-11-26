"use client";

import { useEffect, useRef, useState } from "react";
import {
  Sparkles,
  Power,
  RotateCcw,
  Trash2,
  ExternalLink,
  Download,
  Upload,
  RefreshCw,
  Shield,
  LayoutGrid,
  Users,
  FileText,
} from "lucide-react";
import { apiFetch, getStoredToken } from "@/lib/api";

export interface LiveExtensionItem {
  id: number;
  slug: string;
  name: string;
  ext_type: "widget" | "risk_rule" | "quiz_cohort" | "pdf_template";
  description: string;
  icon: string;
  enabled: boolean;
  version: number;
  config: Record<string, any>;
  has_rollback: boolean;
  created_by: string;
  updated_at: string | null;
}

export function LiveExtensionsSubPanel({
  refreshNonce = 0,
  onOpenWidget,
  onExtensionsChanged,
}: {
  refreshNonce?: number;
  onOpenWidget: (slug: string, name: string) => void;
  onExtensionsChanged: () => void;
}) {
  const [items, setItems] = useState<LiveExtensionItem[]>([]);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const importRef = useRef<HTMLInputElement | null>(null);

  const load = async () => {
    const list = await apiFetch<LiveExtensionItem[]>("/api/extensions");
    setItems(list);
  };

  useEffect(() => {
    load().catch(() => {});
  }, [refreshNonce]);

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(""), 4500);
  };

  const handleBuild = async (customPrompt?: string) => {
    const txt = (customPrompt ?? prompt).trim();
    if (!txt || busy) return;
    setBusy(true);
    try {
      const res = await apiFetch<{
        extension: LiveExtensionItem;
        provider_used: string;
        affected_cases: number;
      }>("/api/extensions/build", {
        method: "POST",
        body: JSON.stringify({ prompt: txt }),
      });
      setPrompt("");
      await load();
      onExtensionsChanged();
      const ext = res.extension;
      flash(
        ext.ext_type === "risk_rule"
          ? `Activated "${ext.name}" (v${ext.version}) — matched ${res.affected_cases} cases.`
          : `Built "${ext.name}" (v${ext.version}) live!`
      );
      if (ext.ext_type === "widget") {
        onOpenWidget(ext.slug, ext.name);
      }
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : "Could not build extension");
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    const pack = await apiFetch<Record<string, unknown>>("/api/extensions/export-pack");
    const blob = new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "agency-custom-modules.jahtaria-pack.json";
    a.click();
    URL.revokeObjectURL(url);
    flash("Exported portable .jahtaria-pack.json");
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const res = await apiFetch<{ imported_count: number }>("/api/extensions/import-pack", {
        method: "POST",
        body: JSON.stringify(parsed),
      });
      await load();
      onExtensionsChanged();
      flash(`Imported ${res.imported_count} live extension(s) cleanly!`);
    } catch {
      flash("Invalid .jahtaria-pack.json file.");
    }
  };

  const typeIcon = (t: string) => {
    if (t === "risk_rule") return <Shield className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
    if (t === "widget") return <LayoutGrid className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
    if (t === "quiz_cohort") return <Users className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
    return <FileText className="w-3.5 h-3.5 text-rose-400 shrink-0" />;
  };

  return (
    <div className="space-y-4">
      <input
        ref={importRef}
        type="file"
        accept=".json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleImport(f);
          e.target.value = "";
        }}
      />

      {/* Calm Builder Prompt Card */}
      <div className="g-card p-3.5 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold text-white flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-[#e5b84b]" /> Live Self-Evolving Extensions
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Core engine stays locked &amp; safe. Tell Hermes to build live risk rules, sidebar widgets, Quiz cohorts, or PDF checklists — instant reload with 1-click Rollback.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 bg-[#151a18] border border-[#e5b84b]/20 rounded-full px-3 py-1.5 focus-within:border-[#e5b84b]/55 transition">
          <input
            className="flex-1 min-w-0 bg-transparent border-0 outline-none text-xs text-slate-100 placeholder:text-slate-500 px-1"
            placeholder="Describe a rule, widget, cohort, or PDF note to build live…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleBuild()}
          />
          <button
            type="button"
            disabled={busy || !prompt.trim()}
            onClick={() => handleBuild()}
            className="px-3 py-1 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold disabled:opacity-40 transition shrink-0"
          >
            {busy ? "Building…" : "Build"}
          </button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {[
            "Build a Passport Expiry Tracker widget",
            "Build a Visa Fee & JMD Calculator widget",
            "Add a risk rule: flag -12 pts if self-employed without documents",
            "Add a cohort for Hospitality workers",
          ].map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => handleBuild(ex)}
              disabled={busy}
              className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.09] border border-white/[0.08] text-[10px] text-slate-300 transition"
            >
              + {ex}
            </button>
          ))}
        </div>
      </div>

      {msg && (
        <div className="p-2.5 rounded-xl bg-emerald-500/15 border border-emerald-400/30 text-xs text-emerald-200">
          {msg}
        </div>
      )}

      {/* Pack Export / Import Bar */}
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
          Installed Live Modules ({items.length})
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => importRef.current?.click()}
            className="g-btn-ghost px-2.5 py-1 text-[11px] inline-flex items-center gap-1"
          >
            <Upload className="w-3 h-3" /> Import Pack
          </button>
          <button
            type="button"
            onClick={handleExport}
            disabled={items.length === 0}
            className="g-btn-ghost px-2.5 py-1 text-[11px] inline-flex items-center gap-1 disabled:opacity-40"
          >
            <Download className="w-3 h-3" /> Export Pack
          </button>
        </div>
      </div>

      {/* Installed Extensions List */}
      {items.length === 0 ? (
        <div className="g-card p-6 text-center text-xs text-slate-500">
          No custom modules yet. Type what you want above — or ask in the main Chat — and Hermes will build &amp; mount it live.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((ext) => (
            <div
              key={ext.id}
              className={`g-card p-3 flex items-start justify-between gap-3 transition ${
                ext.enabled ? "border-white/12" : "opacity-55 border-white/5"
              }`}
            >
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  {typeIcon(ext.ext_type)}
                  <span className="text-xs font-semibold text-white truncate">{ext.name}</span>
                  <span className="text-[10px] font-mono text-slate-500">v{ext.version}</span>
                  <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400">
                    {ext.ext_type.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 line-clamp-2">{ext.description}</p>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                {ext.ext_type === "widget" && ext.enabled && (
                  <button
                    type="button"
                    onClick={() => onOpenWidget(ext.slug, ext.name)}
                    className="p-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 transition"
                    title="Open Custom Module"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={async () => {
                    await apiFetch(`/api/extensions/${ext.id}/toggle`, { method: "POST" });
                    await load();
                    onExtensionsChanged();
                  }}
                  className={`p-1.5 rounded-lg transition ${
                    ext.enabled
                      ? "bg-white/10 text-emerald-300 hover:bg-white/15"
                      : "bg-white/5 text-slate-500 hover:text-slate-200"
                  }`}
                  title={ext.enabled ? "Disable" : "Enable"}
                >
                  <Power className="w-3.5 h-3.5" />
                </button>
                {ext.has_rollback && (
                  <button
                    type="button"
                    onClick={async () => {
                      await apiFetch(`/api/extensions/${ext.id}/rollback`, { method: "POST" });
                      await load();
                      onExtensionsChanged();
                      flash(`Rolled back "${ext.name}" to previous snapshot.`);
                    }}
                    className="p-1.5 rounded-lg hover:bg-white/10 text-amber-300 transition"
                    title="Rollback to previous version"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={async () => {
                    await apiFetch(`/api/extensions/${ext.id}`, { method: "DELETE" });
                    await load();
                    onExtensionsChanged();
                  }}
                  className="p-1.5 rounded-lg hover:bg-red-500/20 text-slate-500 hover:text-red-300 transition"
                  title="Delete module"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CustomWidgetSubPanel({
  slug,
  refreshNonce = 0,
  onManageExtensions,
}: {
  slug: string;
  refreshNonce?: number;
  onManageExtensions: () => void;
}) {
  const [html, setHtml] = useState<string>("");
  const [meta, setMeta] = useState<LiveExtensionItem | null>(null);
  const [loading, setLoading] = useState(true);

  const loadWidget = async () => {
    setLoading(true);
    try {
      const m = await apiFetch<LiveExtensionItem>(`/api/extensions/${encodeURIComponent(slug)}`);
      setMeta(m);
      const token = getStoredToken();
      const res = await fetch(`/api/extensions/${encodeURIComponent(slug)}/render`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        setHtml(await res.text());
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWidget().catch(() => {});
  }, [slug, refreshNonce]);

  return (
    <div className="h-full min-h-[72vh] flex flex-col gap-2.5">
      <div className="flex items-center justify-between text-[11px] text-slate-400">
        <div className="flex items-center gap-2 min-w-0">
          <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-400/25 text-emerald-300 text-[10px]">
            Sandboxed Live Module{meta ? ` · v${meta.version}` : ""}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => loadWidget()}
            className="g-btn-ghost px-2 py-1 text-[10px] inline-flex items-center gap-1"
            title="Refresh live data"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
          <button
            type="button"
            onClick={onManageExtensions}
            className="g-btn-ghost px-2 py-1 text-[10px]"
          >
            Manage
          </button>
        </div>
      </div>

      {loading && !html ? (
        <div className="flex-1 flex items-center justify-center text-xs text-slate-500">
          Loading sandboxed module…
        </div>
      ) : (
        <iframe
          title={meta?.name || slug}
          sandbox="allow-scripts"
          srcDoc={html}
          className="flex-1 w-full min-h-[68vh] rounded-xl border border-white/10 bg-[#0d0f13]"
        />
      )}
    </div>
  );
}
