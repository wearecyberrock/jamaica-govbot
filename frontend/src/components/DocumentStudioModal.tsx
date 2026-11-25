"use client";

import { useEffect, useRef, useState } from "react";
import {
  X,
  Type,
  CheckSquare,
  Calendar,
  PenTool,
  Save,
  Download,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Trash2,
  MousePointer,
  Sparkles,
  RotateCcw,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { ClientDocumentItem, StudioTarget } from "@/lib/types";

interface StudioAnnotation {
  id: string;
  type: "text" | "check" | "date" | "signature";
  page: number;
  x: number; // 0..1 normalized
  y: number; // 0..1 normalized
  w?: number;
  h?: number;
  text?: string;
  font_size?: number;
  color?: string;
  bold?: boolean;
  data_url?: string;
}

interface DocMeta {
  source_type: string;
  source_id: string;
  case_id: string | null;
  title: string;
  filename: string;
  mime_type: string;
  file_format: string;
  page_count: number;
  docx_paragraphs: string[];
}

export function DocumentStudioModal({
  target,
  activeCaseId,
  onClose,
  onSaved,
}: {
  target: StudioTarget;
  activeCaseId?: string | null;
  onClose: () => void;
  onSaved?: (doc: ClientDocumentItem) => void;
}) {
  const [meta, setMeta] = useState<DocMeta | null>(null);
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(1.0);
  const [tool, setTool] = useState<"select" | "text" | "check" | "date" | "signature">("select");
  const [annotations, setAnnotations] = useState<StudioAnnotation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [docxParas, setDocxParas] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [fontColor, setFontColor] = useState("#0b3c68");
  const [fontSize, setFontSize] = useState(13);

  // Signature Pad Modal state
  const [showSigPad, setShowSigPad] = useState(false);
  const [sigMode, setSigMode] = useState<"draw" | "type">("draw");
  const [typedSig, setTypedSig] = useState("");
  const [sigInk, setSigInk] = useState("#0b3c68");
  const [pendingSigCoords, setPendingSigCoords] = useState<{ x: number; y: number } | null>(null);
  const sigCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const isDrawingRef = useRef(false);

  // Dragging annotation state
  const stageRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ id: string; startX: number; startY: number; origX: number; origY: number } | null>(null);

  useEffect(() => {
    apiFetch<DocMeta>(
      `/api/documents/meta?source_type=${encodeURIComponent(target.source_type)}&source_id=${encodeURIComponent(target.source_id)}`
    )
      .then((m) => {
        setMeta(m);
        setDocxParas(m.docx_paragraphs || []);
      })
      .catch((e) => setStatus(String(e)));
  }, [target]);

  const effectiveCaseId = target.case_id || meta?.case_id || activeCaseId || null;
  const isDocx = meta?.file_format === ".docx";
  const pageUrl = `/api/documents/render-page?source_type=${encodeURIComponent(target.source_type)}&source_id=${encodeURIComponent(target.source_id)}&page=${page}`;
  const downloadUrl =
    target.source_type === "vault"
      ? `/api/documents/vault/${target.source_id}/file`
      : target.source_type === "asset"
      ? `/api/assets/${target.source_id}/file`
      : `/api/documents/official/${target.source_id}/view`;

  const flash = (m: string) => {
    setStatus(m);
    setTimeout(() => setStatus(""), 4000);
  };

  const handleStageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (tool === "select" || !stageRef.current) return;
    const rect = stageRef.current.getBoundingClientRect();
    const nx = Math.max(0.01, Math.min(0.95, (e.clientX - rect.left) / rect.width));
    const ny = Math.max(0.01, Math.min(0.95, (e.clientY - rect.top) / rect.height));

    if (tool === "signature") {
      setPendingSigCoords({ x: nx, y: ny });
      setShowSigPad(true);
      return;
    }

    const id = `ann_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const today = new Date().toISOString().slice(0, 10);
    const ann: StudioAnnotation =
      tool === "check"
        ? { id, type: "check", page, x: nx, y: ny, text: "✓", font_size: 16, color: fontColor, bold: true }
        : tool === "date"
        ? { id, type: "date", page, x: nx, y: ny, text: today, font_size: fontSize, color: fontColor, bold: false }
        : { id, type: "text", page, x: nx, y: ny, text: "Type text...", font_size: fontSize, color: fontColor, bold: false };

    setAnnotations((prev) => [...prev, ann]);
    setSelectedId(id);
    setTool("select");
  };

  const startDrag = (e: React.MouseEvent, ann: StudioAnnotation) => {
    e.stopPropagation();
    setSelectedId(ann.id);
    dragRef.current = { id: ann.id, startX: e.clientX, startY: e.clientY, origX: ann.x, origY: ann.y };
  };

  const onStageMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current || !stageRef.current) return;
    const rect = stageRef.current.getBoundingClientRect();
    const dx = (e.clientX - dragRef.current.startX) / rect.width;
    const dy = (e.clientY - dragRef.current.startY) / rect.height;
    const nx = Math.max(0, Math.min(0.95, dragRef.current.origX + dx));
    const ny = Math.max(0, Math.min(0.95, dragRef.current.origY + dy));
    const dragId = dragRef.current.id;
    setAnnotations((prev) => prev.map((a) => (a.id === dragId ? { ...a, x: nx, y: ny } : a)));
  };

  const stopDrag = () => {
    dragRef.current = null;
  };

  const updateSelected = (patch: Partial<StudioAnnotation>) => {
    if (!selectedId) return;
    setAnnotations((prev) => prev.map((a) => (a.id === selectedId ? { ...a, ...patch } : a)));
  };

  // Signature drawing handlers
  const sigStart = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const cv = sigCanvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const r = cv.getBoundingClientRect();
    isDrawingRef.current = true;
    ctx.strokeStyle = sigInk;
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo((e.clientX - r.left) * (cv.width / r.width), (e.clientY - r.top) * (cv.height / r.height));
  };

  const sigMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawingRef.current || !sigCanvasRef.current) return;
    const cv = sigCanvasRef.current;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const r = cv.getBoundingClientRect();
    ctx.lineTo((e.clientX - r.left) * (cv.width / r.width), (e.clientY - r.top) * (cv.height / r.height));
    ctx.stroke();
  };

  const sigEnd = () => {
    isDrawingRef.current = false;
  };

  const clearSigCanvas = () => {
    const cv = sigCanvasRef.current;
    if (!cv) return;
    cv.getContext("2d")?.clearRect(0, 0, cv.width, cv.height);
  };

  const applySignature = () => {
    let dataUrl = "";
    if (sigMode === "draw" && sigCanvasRef.current) {
      dataUrl = sigCanvasRef.current.toDataURL("image/png");
    } else if (sigMode === "type" && typedSig.trim()) {
      const off = document.createElement("canvas");
      off.width = 480;
      off.height = 140;
      const ctx = off.getContext("2d");
      if (ctx) {
        ctx.fillStyle = sigInk;
        ctx.font = "italic 54px Georgia, 'Brush Script MT', cursive";
        ctx.fillText(typedSig.trim(), 16, 92);
        dataUrl = off.toDataURL("image/png");
      }
    }
    if (!dataUrl) return;
    const coords = pendingSigCoords || { x: 0.55, y: 0.78 };
    const id = `sig_${Date.now()}`;
    setAnnotations((prev) => [
      ...prev,
      { id, type: "signature", page, x: coords.x, y: coords.y, w: 0.26, h: 0.08, data_url: dataUrl },
    ]);
    setSelectedId(id);
    setShowSigPad(false);
    setTool("select");
    setPendingSigCoords(null);
  };

  const saveEditedVersion = async () => {
    setSaving(true);
    try {
      const res = await apiFetch<{ ok: boolean; document: ClientDocumentItem }>("/api/documents/studio/save", {
        method: "POST",
        body: JSON.stringify({
          source_type: target.source_type,
          source_id: target.source_id,
          case_id: effectiveCaseId,
          title: `${meta?.title || target.title || "Document"} (Edited)`,
          annotations,
          docx_paragraphs: isDocx ? docxParas : null,
        }),
      });
      flash(`Saved new version '${res.document.title}' to Vault (original preserved)!`);
      onSaved?.(res.document);
    } catch (err: unknown) {
      flash(`Save failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleAiFillOfficial = async () => {
    if (!effectiveCaseId || target.source_type !== "official") return;
    setSaving(true);
    try {
      const res = await apiFetch<{ ok: boolean; document: ClientDocumentItem }>(
        `/api/clients/${effectiveCaseId}/documents/fill-official`,
        { method: "POST", body: JSON.stringify({ doc_key: target.source_id }) }
      );
      flash(`AI Auto-Filled '${res.document.title}' into ${effectiveCaseId}'s Vault!`);
      onSaved?.(res.document);
    } finally {
      setSaving(false);
    }
  };

  const selectedAnn = annotations.find((a) => a.id === selectedId) || null;
  const pageAnns = annotations.filter((a) => a.page === page);

  return (
    <div className="fixed inset-0 z-50 bg-[#080a0e]/95 backdrop-blur-sm flex flex-col text-slate-100">
      {/* Top Studio Toolbar */}
      <header className="h-14 px-4 border-b border-white/10 bg-[#11141c] flex items-center justify-between gap-2 shrink-0 overflow-x-auto">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 text-[11px] font-mono shrink-0">
            STUDIO
          </span>
          <span className="text-sm font-semibold text-white truncate max-w-[260px]">
            {meta?.title || target.title || "Document Editor"}
          </span>
          {effectiveCaseId && (
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-[11px] font-mono shrink-0">
              {effectiveCaseId}
            </span>
          )}
        </div>

        {/* Editing Tools */}
        {!isDocx && (
          <div className="flex items-center gap-1 bg-black/30 p-1 rounded-xl border border-white/10 shrink-0">
            {[
              { id: "select", icon: MousePointer, label: "Move" },
              { id: "text", icon: Type, label: "Text" },
              { id: "check", icon: CheckSquare, label: "Check ✓" },
              { id: "date", icon: Calendar, label: "Date" },
              { id: "signature", icon: PenTool, label: "Sign" },
            ].map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    if (t.id === "signature") {
                      setPendingSigCoords({ x: 0.55, y: 0.78 });
                      setShowSigPad(true);
                    } else {
                      setTool(t.id as typeof tool);
                    }
                  }}
                  className={`px-2.5 py-1.5 rounded-lg text-xs inline-flex items-center gap-1.5 transition ${
                    tool === t.id ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-white/10"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" /> {t.label}
                </button>
              );
            })}
            <input
              type="color"
              value={fontColor}
              onChange={(e) => {
                setFontColor(e.target.value);
                if (selectedAnn) updateSelected({ color: e.target.value });
              }}
              className="w-7 h-7 rounded bg-transparent cursor-pointer ml-1"
              title="Ink / Text Color"
            />
          </div>
        )}

        {/* Right Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          {target.source_type === "official" && effectiveCaseId && (
            <button
              type="button"
              disabled={saving}
              onClick={handleAiFillOfficial}
              className="px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/30 text-amber-200 text-xs font-semibold inline-flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5" /> AI Auto-Fill ({effectiveCaseId})
            </button>
          )}
          <a href={downloadUrl} download={meta?.filename || "document"} className="g-btn-ghost px-2.5 py-1.5 text-xs inline-flex items-center gap-1">
            <Download className="w-3.5 h-3.5" /> Original
          </a>
          <button
            type="button"
            disabled={saving}
            onClick={saveEditedVersion}
            className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold inline-flex items-center gap-1.5 disabled:opacity-40"
          >
            <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save New Version"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/15 text-slate-300"
            title="Close Full-Screen Studio"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </header>

      {status && (
        <div className="px-4 py-2 bg-emerald-500/15 border-b border-emerald-400/30 text-xs text-emerald-200 text-center">
          {status}
        </div>
      )}

      {/* Selected Text Inspector Strip */}
      {selectedAnn && !isDocx && (
        <div className="px-4 py-2 bg-[#161a24] border-b border-white/10 flex flex-wrap items-center justify-center gap-3 text-xs">
          {selectedAnn.type !== "signature" ? (
            <>
              <input
                value={selectedAnn.text || ""}
                onChange={(e) => updateSelected({ text: e.target.value })}
                className="g-input text-xs py-1 w-64"
                placeholder="Edit overlay text..."
                autoFocus
              />
              <label className="inline-flex items-center gap-1 text-slate-400">
                Size
                <input
                  type="number"
                  min={8}
                  max={42}
                  value={selectedAnn.font_size || 13}
                  onChange={(e) => {
                    const sz = Number(e.target.value) || 13;
                    setFontSize(sz);
                    updateSelected({ font_size: sz });
                  }}
                  className="w-14 bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-center text-white"
                />
              </label>
              <button
                type="button"
                onClick={() => updateSelected({ bold: !selectedAnn.bold })}
                className={`px-2 py-1 rounded border text-xs font-bold ${
                  selectedAnn.bold ? "bg-blue-600 border-blue-400 text-white" : "border-white/15 text-slate-300"
                }`}
              >
                B
              </button>
            </>
          ) : (
            <div className="flex items-center gap-2 text-slate-300">
              <span>Signature Size:</span>
              <input
                type="range"
                min={12}
                max={50}
                value={Math.round((selectedAnn.w || 0.26) * 100)}
                onChange={(e) => {
                  const nw = Number(e.target.value) / 100;
                  updateSelected({ w: nw, h: nw * 0.32 });
                }}
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              setAnnotations((prev) => prev.filter((a) => a.id !== selectedAnn.id));
              setSelectedId(null);
            }}
            className="px-2 py-1 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300 inline-flex items-center gap-1"
          >
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </button>
        </div>
      )}

      {/* Main Canvas / DOCX Editor Stage */}
      <div className="flex-1 overflow-auto p-6 flex justify-center items-start">
        {isDocx ? (
          <div className="w-full max-w-3xl bg-white text-slate-900 rounded-2xl shadow-2xl p-8 space-y-3">
            <div className="text-xs font-semibold text-emerald-800 uppercase tracking-wider border-b pb-2">
              Inline DOCX Text Editor — Click any paragraph to edit, then Save New Version
            </div>
            {docxParas.map((p, i) => (
              <textarea
                key={i}
                rows={Math.max(1, Math.ceil(p.length / 85))}
                value={p}
                onChange={(e) => {
                  const next = [...docxParas];
                  next[i] = e.target.value;
                  setDocxParas(next);
                }}
                className="w-full border border-slate-200 hover:border-blue-400 focus:border-blue-600 rounded-lg p-2 text-sm text-slate-800 outline-none resize-y"
              />
            ))}
          </div>
        ) : (
          <div
            ref={stageRef}
            onClick={handleStageClick}
            onMouseMove={onStageMouseMove}
            onMouseUp={stopDrag}
            onMouseLeave={stopDrag}
            style={{ width: `${Math.round(780 * zoom)}px` }}
            className={`relative bg-white shadow-2xl rounded-lg overflow-hidden select-none ${
              tool !== "select" ? "cursor-crosshair ring-2 ring-blue-400" : ""
            }`}
          >
            <img src={pageUrl} alt={meta?.title || "Page"} className="w-full h-auto block pointer-events-none" />

            {/* Interactive Placed Overlays */}
            {pageAnns.map((ann) => (
              <div
                key={ann.id}
                onMouseDown={(e) => startDrag(e, ann)}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedId(ann.id);
                }}
                style={{
                  left: `${ann.x * 100}%`,
                  top: `${ann.y * 100}%`,
                  width: ann.type === "signature" ? `${(ann.w || 0.26) * 100}%` : undefined,
                }}
                className={`absolute cursor-move px-1 rounded ${
                  selectedId === ann.id
                    ? "ring-2 ring-blue-500 bg-blue-500/10"
                    : "hover:ring-1 hover:ring-blue-400/70"
                }`}
              >
                {ann.type === "signature" && ann.data_url ? (
                  <img src={ann.data_url} alt="Signature" className="w-full h-auto pointer-events-none" />
                ) : (
                  <span
                    style={{
                      color: ann.color || "#0b3c68",
                      fontSize: `${Math.round((ann.font_size || 13) * zoom)}px`,
                      fontWeight: ann.bold ? 700 : 400,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {ann.text}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom Page & Zoom Bar */}
      {!isDocx && (
        <footer className="h-12 px-4 border-t border-white/10 bg-[#11141c] flex items-center justify-between text-xs shrink-0">
          <div className="text-slate-400">
            {tool === "select"
              ? "Tip: Pick Text, Check ✓, Date, or Sign above, then click anywhere on the page."
              : `Click anywhere on the page to place ${tool.toUpperCase()}.`}
          </div>
          <div className="flex items-center gap-3">
            {meta && meta.page_count > 1 && (
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={page <= 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="p-1 rounded bg-white/5 hover:bg-white/10 disabled:opacity-30"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-slate-300 font-mono">
                  Page {page + 1} / {meta.page_count}
                </span>
                <button
                  type="button"
                  disabled={page >= meta.page_count - 1}
                  onClick={() => setPage((p) => Math.min(meta.page_count - 1, p + 1))}
                  className="p-1 rounded bg-white/5 hover:bg-white/10 disabled:opacity-30"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
            <div className="flex items-center gap-1">
              <button onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.15).toFixed(2)))} className="p-1 rounded bg-white/5 hover:bg-white/10">
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="w-11 text-center font-mono text-slate-300">{Math.round(zoom * 100)}%</span>
              <button onClick={() => setZoom((z) => Math.min(2.0, +(z + 0.15).toFixed(2)))} className="p-1 rounded bg-white/5 hover:bg-white/10">
                <ZoomIn className="w-4 h-4" />
              </button>
            </div>
          </div>
        </footer>
      )}

      {/* Signature Pad Sub-Modal */}
      {showSigPad && (
        <div className="fixed inset-0 z-60 bg-black/75 flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl bg-[#161a24] border border-white/15 p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-white">Add Signature</span>
              <button onClick={() => setShowSigPad(false)} className="p-1 text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex items-center justify-between gap-2">
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setSigMode("draw")}
                  className={`px-3 py-1 rounded-lg text-xs font-medium ${sigMode === "draw" ? "bg-blue-600 text-white" : "bg-white/5 text-slate-300"}`}
                >
                  Draw Signature
                </button>
                <button
                  type="button"
                  onClick={() => setSigMode("type")}
                  className={`px-3 py-1 rounded-lg text-xs font-medium ${sigMode === "type" ? "bg-blue-600 text-white" : "bg-white/5 text-slate-300"}`}
                >
                  Type Signature
                </button>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                Ink:
                {["#0b3c68", "#0f172a", "#1d4ed8"].map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setSigInk(c)}
                    style={{ background: c }}
                    className={`w-5 h-5 rounded-full border-2 ${sigInk === c ? "border-amber-300" : "border-white/20"}`}
                  />
                ))}
              </div>
            </div>

            {sigMode === "draw" ? (
              <div className="space-y-2">
                <canvas
                  ref={sigCanvasRef}
                  width={480}
                  height={160}
                  onPointerDown={sigStart}
                  onPointerMove={sigMove}
                  onPointerUp={sigEnd}
                  onPointerLeave={sigEnd}
                  className="w-full h-40 rounded-xl bg-white border border-white/20 cursor-crosshair touch-none"
                />
                <button type="button" onClick={clearSigCanvas} className="text-xs text-slate-400 hover:text-white inline-flex items-center gap-1">
                  <RotateCcw className="w-3 h-3" /> Clear Pad
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <input
                  value={typedSig}
                  onChange={(e) => setTypedSig(e.target.value)}
                  placeholder="Type full legal signature..."
                  className="g-input text-sm"
                />
                <div
                  className="h-24 rounded-xl bg-white flex items-center px-4 overflow-hidden"
                  style={{ color: sigInk, fontFamily: "Georgia, cursive", fontStyle: "italic", fontSize: "34px" }}
                >
                  {typedSig || "Signature Preview"}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowSigPad(false)} className="g-btn-ghost px-3 py-1.5 text-xs">
                Cancel
              </button>
              <button type="button" onClick={applySignature} className="g-btn-primary px-4 py-1.5 text-xs font-semibold">
                Place Signature on Page
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
