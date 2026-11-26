"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  GitBranch,
  X,
  Send,
  ChevronDown,
  ChevronRight,
  PanelRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Volume2,
  Printer,
  Sparkles,
  Trash2,
  MessageSquare,
  Edit3,
  Route,
} from "lucide-react";
import { apiFetch, getStoredToken } from "@/lib/api";
import { RichMarkdown } from "./RichMarkdown";

interface LaneXItem {
  id: string;
  db_id: number;
  source_type: string;
  case_id: string;
  client_name: string;
  visa_class: string;
  theme_id: string;
  question_text: string;
  rationale: string;
  confidence: number;
  difficulty: string;
  frequency: number;
  is_weak: boolean;
  answer_strength: string;
}

interface LaneYItem {
  id: string;
  x_id: string;
  case_id: string;
  theme_id: string;
  answer_text: string;
  has_answer: boolean;
  strength: string;
  feedback: string;
  usage_count: number;
}

interface LaneZItem {
  id: string;
  db_id: number;
  theme_id: string;
  visa_class: string;
  question_text: string;
  difficulty: string;
  frequency: number;
  outcome_tag: string;
  profile_tags: string[];
  source_case_id: string | null;
  added_by: string;
}

interface LaneAItem {
  id: string;
  z_id: string;
  db_id: number;
  theme_id: string;
  answer_text: string;
  answer_quality: string;
  outcome_tag: string;
  usage_count: number;
  notes: string;
}

interface OutputNodeItem {
  id: string;
  theme_id: string;
  case_id: string;
  question_text: string;
  rationale: string;
  fresh?: boolean;
}

interface EdgeItem {
  from: string;
  to: string;
  kind: "x_to_y" | "x_to_z" | "z_to_a" | "a_to_out";
  theme_id: string;
  strength?: string;
  outcome_tag?: string;
}

interface CanvasResponse {
  scope: {
    case_id: string;
    cohort: string;
    q_filter: string;
    a_filter: string;
    visa_class: string;
    effective_mode: boolean;
    matched_clients: number;
  };
  lane_x: LaneXItem[];
  lane_y: LaneYItem[];
  lane_z: LaneZItem[];
  lane_a: LaneAItem[];
  edges: EdgeItem[];
  effective: {
    active: boolean;
    cohort_stats: Array<{
      cohort_id: string;
      label: string;
      approval_rate_pct: number | null;
      sample_label: string;
      avg_standing_score: number;
    }>;
  };
}

interface ChatMessage {
  sender: "user" | "assistant";
  content: string;
  print_pdf_url?: string | null;
}

interface ContextMenuState {
  x: number;
  y: number;
  nodeId: string;
  lane: "X" | "Y" | "Z" | "A" | "OUT";
  label: string;
  text: string;
  themeId: string;
  caseId?: string;
  dbId?: number;
  yNodeId?: string;
}

export function QuizBuilderModal({
  initialCaseId,
  onClose,
}: {
  initialCaseId: string | null;
  onClose: () => void;
}) {
  // Canvas scope & filters (controlled effortlessly via chat!)
  const [caseId, setCaseId] = useState<string>(initialCaseId || "ALL");
  const [cohort, setCohort] = useState<string>("all");
  const [qFilter, setQFilter] = useState<string>("all");
  const [aFilter, setAFilter] = useState<string>("all");
  const [visaClass, setVisaClass] = useState<string>("all");
  const [effectiveMode, setEffectiveMode] = useState<boolean>(false);

  const [data, setData] = useState<CanvasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [freshOutputs, setFreshOutputs] = useState<OutputNodeItem[]>([]);
  const [flowPulse, setFlowPulse] = useState(false);

  // Node UI state: minimal collapsed by default, dropdown or right-click to inspect
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  // Inline answer editor (inside Lane Y dropdown)
  const [editingYId, setEditingYId] = useState<string | null>(null);
  const [editingYText, setEditingYText] = useState<string>("");
  const [savingY, setSavingY] = useState(false);

  // Zoom & Pan canvas state
  const [zoom, setZoom] = useState<number>(0.78);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 24, y: 24 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // SVG lines measured in unscaled stage coordinates (100% zoom-invariant!)
  const [svgLines, setSvgLines] = useState<
    Array<{ id: string; d: string; kind: string; highlighted: boolean; dimmed: boolean; animated: boolean }>
  >([]);
  const [stageDims, setStageDims] = useState<{ w: number; h: number }>({ w: 1700, h: 1100 });

  // Clean Chat Side Panel state
  const [chatOpen, setChatOpen] = useState(true);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

  const loadCanvas = useCallback(
    async (overrides?: {
      caseId?: string;
      cohort?: string;
      qFilter?: string;
      aFilter?: string;
      visaClass?: string;
      effectiveMode?: boolean;
    }) => {
      const cid = overrides?.caseId ?? caseId;
      const coh = overrides?.cohort ?? cohort;
      const qf = overrides?.qFilter ?? qFilter;
      const af = overrides?.aFilter ?? aFilter;
      const vc = overrides?.visaClass ?? visaClass;
      const eff = overrides?.effectiveMode ?? effectiveMode;

      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (cid && cid !== "ALL") params.set("case_id", cid);
        params.set("cohort", coh);
        params.set("q_filter", qf);
        params.set("a_filter", af);
        params.set("visa_class", vc);
        params.set("effective_mode", String(eff));
        const res = await apiFetch<CanvasResponse>(`/api/quiz-builder/canvas?${params.toString()}`);
        setData(res);
      } finally {
        setLoading(false);
      }
    },
    [caseId, cohort, qFilter, aFilter, visaClass, effectiveMode]
  );

  useEffect(() => {
    loadCanvas().catch(() => {});
  }, [loadCanvas]);

  useEffect(() => {
    chatScrollRef.current?.scrollTo({ top: chatScrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, chatBusy]);

  // Close context menu on any outside click or Escape
  useEffect(() => {
    const close = () => setContextMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setContextMenu(null);
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  // Build visible lanes (compact slice so canvas stays calm & breathable; chat filters narrow further)
  const visibleX = useMemo(() => (data?.lane_x || []).slice(0, 10), [data]);
  const visibleY = useMemo(() => {
    const xIds = new Set(visibleX.map((x) => x.id));
    return (data?.lane_y || []).filter((y) => xIds.has(y.x_id));
  }, [data, visibleX]);
  const visibleZ = useMemo(() => (data?.lane_z || []).slice(0, 10), [data]);
  const visibleA = useMemo(() => {
    const zIds = new Set(visibleZ.map((z) => z.id));
    return (data?.lane_a || []).filter((a) => zIds.has(a.z_id));
  }, [data, visibleZ]);

  // Propagation Output Column: freshly generated questions from flow OR top prioritized readiness outputs
  const outputNodes: OutputNodeItem[] = useMemo(() => {
    if (freshOutputs.length > 0) return freshOutputs;
    return visibleX.slice(0, 4).map((x) => ({
      id: `OUT-${x.id}`,
      theme_id: x.theme_id,
      case_id: x.case_id,
      question_text: x.question_text,
      rationale: x.rationale || "Prioritized by relationship flow from Client Data (X/Y) × Embassy Archive (Z/A).",
      fresh: false,
    }));
  }, [freshOutputs, visibleX]);

  // Combine X→Y, X↔Z, Z→A, plus A→OUT propagation edges
  const allEdges: EdgeItem[] = useMemo(() => {
    if (!data) return [];
    const visIds = new Set([
      ...visibleX.map((n) => n.id),
      ...visibleY.map((n) => n.id),
      ...visibleZ.map((n) => n.id),
      ...visibleA.map((n) => n.id),
    ]);
    const base: EdgeItem[] = data.edges.filter((e) => visIds.has(e.from) && visIds.has(e.to));

    // Propagate matched A outcomes into Output nodes!
    for (const out of outputNodes) {
      const matchedA = visibleA.filter((a) => a.theme_id === out.theme_id);
      const sources = matchedA.length > 0 ? matchedA.slice(0, 2) : visibleA.slice(0, 1);
      for (const a of sources) {
        base.push({
          from: a.id,
          to: out.id,
          kind: "a_to_out",
          theme_id: out.theme_id,
          outcome_tag: a.outcome_tag,
        });
      }
    }
    return base;
  }, [data, visibleX, visibleY, visibleZ, visibleA, outputNodes]);

  // Connected chain set for click-highlight or Effective Pathway propagation
  const highlightedIds = useMemo(() => {
    if (!selectedNodeId) {
      if (!effectiveMode && !flowPulse) return new Set<string>();
      const active = new Set<string>();
      for (const out of outputNodes) active.add(out.id);
      for (const e of allEdges) {
        if (e.kind === "a_to_out" && active.has(e.to)) active.add(e.from);
      }
      for (const e of allEdges) {
        if (e.kind === "z_to_a" && active.has(e.to)) active.add(e.from);
      }
      for (const e of allEdges) {
        if (e.kind === "x_to_z" && active.has(e.to)) active.add(e.from);
      }
      for (const e of allEdges) {
        if (e.kind === "x_to_y" && active.has(e.from)) active.add(e.to);
      }
      return active;
    }

    const adj = new Map<string, Set<string>>();
    for (const e of allEdges) {
      if (!adj.has(e.from)) adj.set(e.from, new Set());
      if (!adj.has(e.to)) adj.set(e.to, new Set());
      adj.get(e.from)!.add(e.to);
      adj.get(e.to)!.add(e.from);
    }
    const visited = new Set<string>([selectedNodeId]);
    const q = [selectedNodeId];
    while (q.length > 0) {
      const cur = q.shift()!;
      for (const nxt of adj.get(cur) || []) {
        if (!visited.has(nxt)) {
          visited.add(nxt);
          q.push(nxt);
        }
      }
    }
    return visited;
  }, [selectedNodeId, effectiveMode, flowPulse, allEdges, outputNodes]);

  // Compute zoom-invariant Bezier wires in unscaled stage space!
  const recomputeEdges = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const getRelPos = (el: HTMLElement) => {
      let x = 0;
      let y = 0;
      let cur: HTMLElement | null = el;
      while (cur && cur !== stage) {
        x += cur.offsetLeft;
        y += cur.offsetTop;
        cur = cur.offsetParent as HTMLElement | null;
      }
      return { x, y, w: el.offsetWidth, h: el.offsetHeight };
    };

    const nextLines: typeof svgLines = [];
    const hasFilter = highlightedIds.size > 0;

    for (let i = 0; i < allEdges.length; i++) {
      const e = allEdges[i];
      const fromEl = nodeRefs.current[e.from];
      const toEl = nodeRefs.current[e.to];
      if (!fromEl || !toEl) continue;

      const a = getRelPos(fromEl);
      const b = getRelPos(toEl);
      const x1 = a.x + a.w;
      const y1 = a.y + a.h / 2;
      const x2 = b.x;
      const y2 = b.y + b.h / 2;
      const dx = Math.max(36, Math.abs(x2 - x1) * 0.45);
      const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

      const highlighted = hasFilter && highlightedIds.has(e.from) && highlightedIds.has(e.to);
      const dimmed = hasFilter && !highlighted;
      const animated = highlighted && (effectiveMode || flowPulse || e.kind === "a_to_out");
      nextLines.push({ id: `${e.from}-${e.to}-${i}`, d, kind: e.kind, highlighted, dimmed, animated });
    }

    setSvgLines(nextLines);
    setStageDims({
      w: Math.max(1680, stage.scrollWidth + 80),
      h: Math.max(920, stage.scrollHeight + 100),
    });
  }, [allEdges, highlightedIds, effectiveMode, flowPulse]);

  useLayoutEffect(() => {
    const raf = requestAnimationFrame(recomputeEdges);
    const t = setTimeout(recomputeEdges, 140);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t);
    };
  }, [recomputeEdges, expandedIds, editingYId, data, freshOutputs]);

  // Fit canvas cleanly into viewport
  const fitToView = useCallback(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const rect = vp.getBoundingClientRect();
    const targetZoom = Math.max(0.52, Math.min(0.95, (rect.width - 48) / 1600));
    setZoom(Number(targetZoom.toFixed(2)));
    setPan({ x: 24, y: 24 });
  }, []);

  useEffect(() => {
    const t = setTimeout(fitToView, 80);
    return () => clearTimeout(t);
  }, [fitToView, chatOpen]);

  // Mouse wheel zoom centered on cursor
  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const vp = viewportRef.current;
    if (!vp) return;
    const rect = vp.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const factor = e.deltaY < 0 ? 1.09 : 0.92;
    setZoom((prevZoom) => {
      const nextZoom = Math.max(0.4, Math.min(1.8, Number((prevZoom * factor).toFixed(3))));
      const ratio = nextZoom / prevZoom;
      setPan((prevPan) => ({
        x: mx - (mx - prevPan.x) * ratio,
        y: my - (my - prevPan.y) * ratio,
      }));
      return nextZoom;
    });
  };

  // Drag-to-pan on empty canvas background
  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (e.button === 0 && !target.closest("[data-qb-node='true']")) {
      setContextMenu(null);
      setIsPanning(true);
      panStartRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isPanning || !panStartRef.current) return;
    const dx = e.clientX - panStartRef.current.x;
    const dy = e.clientY - panStartRef.current.y;
    setPan({ x: panStartRef.current.panX + dx, y: panStartRef.current.panY + dy });
  };

  const handleCanvasMouseUp = () => {
    setIsPanning(false);
    panStartRef.current = null;
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const openContextMenu = (e: React.MouseEvent, payload: Omit<ContextMenuState, "x" | "y">) => {
    e.preventDefault();
    e.stopPropagation();
    const menuW = 220;
    const menuH = 230;
    const x = Math.min(e.clientX, window.innerWidth - menuW - 12);
    const y = Math.min(e.clientY, window.innerHeight - menuH - 12);
    setContextMenu({ x, y, ...payload });
  };

  const speakOfficer = async (text: string) => {
    try {
      const token = getStoredToken();
      const res = await fetch("/api/voice/speak", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ text, persona: "officer_us" }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      await audio.play();
    } catch {
      // ignore offline tts error
    }
  };

  const openPdfUrl = async (url: string) => {
    try {
      const token = getStoredToken();
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, "_blank");
    } catch {
      // ignore
    }
  };

  const handleSaveYAnswer = async (xNode: LaneXItem) => {
    if (!editingYText.trim()) return;
    setSavingY(true);
    try {
      const res = await apiFetch<{ standing_score: number; score_breakdown?: { practice_bonus: number } }>(
        "/api/quiz-builder/save-answer",
        {
          method: "POST",
          body: JSON.stringify({
            case_id: xNode.case_id,
            source_type: xNode.source_type,
            db_id: xNode.db_id,
            theme_id: xNode.theme_id,
            question_text: xNode.question_text,
            answer_text: editingYText.trim(),
          }),
        }
      );
      setEditingYId(null);
      setEditingYText("");
      await loadCanvas();
      setMessages((prev) => [
        ...prev,
        {
          sender: "assistant",
          content: `Saved client answer for **${xNode.case_id}** (\`${xNode.theme_id.replace(/_/g, " ")}\`). Docs/Data standing stays primary (**${res.standing_score}%** · practice lift \`+${res.score_breakdown?.practice_bonus ?? 0}/6\`).`,
        },
      ]);
    } finally {
      setSavingY(false);
    }
  };

  const handleDeleteOfficial = async (dbId: number) => {
    try {
      await apiFetch(`/api/quiz-builder/official-qa/${dbId}`, { method: "DELETE" });
      await loadCanvas();
    } catch {
      // ignore
    }
  };

  const sendChat = async (customText?: string) => {
    const text = (customText ?? chatInput).trim();
    if (!text || chatBusy) return;
    setChatInput("");
    setChatBusy(true);
    setMessages((prev) => [...prev, { sender: "user", content: text }]);

    try {
      const res = await apiFetch<{
        reply: string;
        canvas_state: {
          case_id: string;
          cohort: string;
          q_filter: string;
          a_filter: string;
          visa_class: string;
          effective_mode: boolean;
        };
        refresh_canvas: boolean;
        trigger_flow: boolean;
        output_questions: Array<{
          id: string;
          case_id: string;
          theme_id: string;
          question_text: string;
          rationale: string;
        }>;
        print_pdf_url: string | null;
      }>("/api/quiz-builder/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          case_id: caseId,
          cohort,
          q_filter: qFilter,
          a_filter: aFilter,
          visa_class: visaClass,
          effective_mode: effectiveMode,
        }),
      });

      const cs = res.canvas_state;
      setCaseId(cs.case_id);
      setCohort(cs.cohort);
      setQFilter(cs.q_filter);
      setAFilter(cs.a_filter);
      setVisaClass(cs.visa_class);
      setEffectiveMode(cs.effective_mode);

      if (res.output_questions && res.output_questions.length > 0) {
        setFreshOutputs(
          res.output_questions.map((q) => ({
            id: `OUT-${q.id}`,
            case_id: q.case_id,
            theme_id: q.theme_id,
            question_text: q.question_text,
            rationale: q.rationale,
            fresh: true,
          }))
        );
      }

      if (res.trigger_flow) {
        setFlowPulse(true);
        setSelectedNodeId(null);
      }

      if (res.refresh_canvas) {
        await loadCanvas({
          caseId: cs.case_id,
          cohort: cs.cohort,
          qFilter: cs.q_filter,
          aFilter: cs.a_filter,
          visaClass: cs.visa_class,
          effectiveMode: cs.effective_mode,
        });
      }

      if (res.print_pdf_url) {
        openPdfUrl(res.print_pdf_url);
      }

      setMessages((prev) => [
        ...prev,
        { sender: "assistant", content: res.reply, print_pdf_url: res.print_pdf_url },
      ]);
    } catch (err: unknown) {
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", content: `Error: ${err instanceof Error ? err.message : "Could not process command."}` },
      ]);
    } finally {
      setChatBusy(false);
    }
  };

  const activeFiltersCount =
    (caseId !== "ALL" ? 1 : 0) +
    (qFilter !== "all" ? 1 : 0) +
    (aFilter !== "all" ? 1 : 0) +
    (cohort !== "all" ? 1 : 0) +
    (visaClass !== "all" ? 1 : 0) +
    (effectiveMode ? 1 : 0);

  return (
    <div className="fixed inset-0 z-50 bg-[#0d0f13] text-slate-100 flex flex-col overflow-hidden select-none">
      {/* Flowing propagation dash animation */}
      <style>{`
        @keyframes qbFlowDash {
          to { stroke-dashoffset: -24; }
        }
        .qb-flow-wire {
          stroke-dasharray: 6 6;
          animation: qbFlowDash 1.1s linear infinite;
        }
      `}</style>

      <div className="h-[2px] w-full ja-ribbon shrink-0 opacity-80" />

      {/* ── ULTRA-MINIMAL TOP BAR (Matches Main Dashboard Simplicity) ─────── */}
      <header className="h-12 px-4 border-b border-[#e5b84b]/12 bg-[#0f1311] flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <GitBranch className="w-4 h-4 text-[#e5b84b] shrink-0" />
          <span className="text-xs font-semibold text-slate-100 tracking-tight">Quiz Builder</span>
          <span className="text-[11px] text-slate-500 hidden sm:inline">X → Y → Z → A → Output</span>

          {/* Subtle read-only pills showing active state driven by chat */}
          <div className="flex items-center gap-1.5 ml-2 overflow-x-auto">
            <span className="px-2 py-0.5 rounded-full bg-white/[0.05] border border-white/10 text-[10px] text-slate-300 font-mono">
              {caseId === "ALL" ? "All Clients" : caseId}
            </span>
            {qFilter !== "all" && (
              <span className="px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-400/25 text-[10px] text-blue-300">
                {qFilter.replace(/_/g, " ")}
              </span>
            )}
            {cohort !== "all" && (
              <span className="px-2 py-0.5 rounded-full bg-purple-500/15 border border-purple-400/25 text-[10px] text-purple-300">
                {cohort.replace(/_/g, " ")}
              </span>
            )}
            {effectiveMode && (
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-400/25 text-[10px] text-emerald-300">
                Effective Flow
              </span>
            )}
            {activeFiltersCount > 0 && (
              <button
                type="button"
                onClick={() => sendChat("reset canvas")}
                className="text-[10px] text-slate-500 hover:text-slate-200 px-1.5 transition"
                title="Reset filters"
              >
                reset
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => setChatOpen((v) => !v)}
            className={`p-1.5 rounded-lg transition ${
              chatOpen ? "bg-white/10 text-white" : "text-slate-400 hover:text-white hover:bg-white/[0.06]"
            }`}
            title={chatOpen ? "Hide Chat Panel" : "Show Chat Panel"}
          >
            <PanelRight className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.08] transition"
            title="Close Quiz Builder"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* ── WORKSPACE: ZOOMABLE FLOW CANVAS + CLEAN CHAT SIDE PANEL ───────── */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* LEFT/CENTER: INFINITE ZOOM/PAN NODE CANVAS */}
        <div
          ref={viewportRef}
          onWheel={handleWheel}
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          onMouseLeave={handleCanvasMouseUp}
          className={`flex-1 relative overflow-hidden bg-[#0d0f13] ${
            isPanning ? "cursor-grabbing" : "cursor-grab"
          }`}
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px)",
            backgroundSize: `${Math.max(12, 22 * zoom)}px ${Math.max(12, 22 * zoom)}px`,
            backgroundPosition: `${pan.x}px ${pan.y}px`,
          }}
        >
          {loading && !data ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-500">
              Loading node flow canvas…
            </div>
          ) : (
            /* TRANSFORM STAGE (Both SVG wires and Nodes share exact unscaled coordinates!) */
            <div
              ref={stageRef}
              style={{
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                transformOrigin: "0 0",
              }}
              className="relative inline-block p-6"
            >
              {/* SVG Propagation Curves */}
              <svg
                width={stageDims.w}
                height={stageDims.h}
                className="pointer-events-none absolute top-0 left-0 overflow-visible"
              >
                {svgLines.map((ln) => {
                  const stroke =
                    ln.kind === "x_to_y"
                      ? ln.highlighted
                        ? "#34d399"
                        : "rgba(52,211,153,0.22)"
                      : ln.kind === "x_to_z"
                      ? ln.highlighted
                        ? "#60a5fa"
                        : "rgba(96,165,250,0.18)"
                      : ln.kind === "z_to_a"
                      ? ln.highlighted
                        ? "#e5b84b"
                        : "rgba(229,184,75,0.22)"
                      : ln.highlighted
                      ? "#2dd4bf"
                      : "rgba(45,212,191,0.28)";

                  return (
                    <path
                      key={ln.id}
                      d={ln.d}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={ln.highlighted ? 2.2 : 1.25}
                      strokeOpacity={ln.dimmed ? 0.14 : 1}
                      className={ln.animated ? "qb-flow-wire" : ""}
                    />
                  );
                })}
              </svg>

              {/* 5 PROPAGATION COLUMNS: X → Y → Z → A → OUTPUT */}
              <div className="relative z-10 flex items-start gap-16">
                {/* ── LANE X: CLIENT QUESTIONS ── */}
                <div className="w-[248px] space-y-2.5 shrink-0">
                  <LaneHeader dot="bg-blue-400" code="X" title="Client Questions" count={visibleX.length} />
                  {visibleX.map((x) => {
                    const open = Boolean(expandedIds[x.id]);
                    const isHi = highlightedIds.has(x.id);
                    const isDim = highlightedIds.size > 0 && !isHi;
                    const linkedY = visibleY.find((y) => y.x_id === x.id);

                    return (
                      <div
                        key={x.id}
                        data-qb-node="true"
                        ref={(el) => {
                          nodeRefs.current[x.id] = el;
                        }}
                        onClick={() => setSelectedNodeId((p) => (p === x.id ? null : x.id))}
                        onDoubleClick={() => toggleExpand(x.id)}
                        onContextMenu={(e) =>
                          openContextMenu(e, {
                            nodeId: x.id,
                            lane: "X",
                            label: `${x.case_id} · ${x.theme_id.replace(/_/g, " ")}`,
                            text: x.question_text,
                            themeId: x.theme_id,
                            caseId: x.case_id,
                            dbId: x.db_id,
                            yNodeId: linkedY?.id,
                          })
                        }
                        className={`relative rounded-xl border bg-[#13171b]/95 px-3 py-2.5 transition cursor-pointer ${
                          isHi
                            ? "border-blue-400/70 shadow-lg shadow-blue-950/50"
                            : "border-white/10 hover:border-white/25"
                        } ${isDim ? "opacity-30" : "opacity-100"}`}
                      >
                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
                            <span className="text-[10px] font-mono text-slate-400 truncate">
                              {x.case_id} · {x.theme_id.replace(/_/g, " ")}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(x.id);
                            }}
                            className="p-0.5 text-slate-500 hover:text-slate-200 shrink-0"
                            title="Expand details"
                          >
                            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        <div className={`text-[12px] text-slate-100 mt-1 leading-snug ${open ? "" : "line-clamp-1"}`}>
                          {x.question_text}
                        </div>

                        {open && (
                          <div className="mt-2 pt-2 border-t border-white/10 space-y-1.5 text-[11px] text-slate-400">
                            {x.rationale && <p className="leading-relaxed">{x.rationale}</p>}
                            <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                              <span>
                                {x.difficulty.toUpperCase()} · {x.frequency}× · {Math.round(x.confidence * 100)}%
                              </span>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  speakOfficer(x.question_text);
                                }}
                                className="text-slate-300 hover:text-white inline-flex items-center gap-1"
                              >
                                <Volume2 className="w-3 h-3" /> Voice
                              </button>
                            </div>
                          </div>
                        )}

                        <span className="absolute -right-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-blue-400/80 border border-[#0d0f13]" />
                      </div>
                    );
                  })}
                </div>

                {/* ── LANE Y: CLIENT ANSWERS ── */}
                <div className="w-[238px] space-y-2.5 shrink-0">
                  <LaneHeader dot="bg-emerald-400" code="Y" title="Client Answers" count={visibleY.length} />
                  {visibleY.map((y) => {
                    const open = Boolean(expandedIds[y.id]) || editingYId === y.id;
                    const isHi = highlightedIds.has(y.id);
                    const isDim = highlightedIds.size > 0 && !isHi;
                    const xNode = visibleX.find((x) => x.id === y.x_id);

                    return (
                      <div
                        key={y.id}
                        data-qb-node="true"
                        ref={(el) => {
                          nodeRefs.current[y.id] = el;
                        }}
                        onClick={() => setSelectedNodeId((p) => (p === y.id ? null : y.id))}
                        onDoubleClick={() => toggleExpand(y.id)}
                        onContextMenu={(e) =>
                          openContextMenu(e, {
                            nodeId: y.id,
                            lane: "Y",
                            label: `${y.case_id} Answer · ${y.strength}`,
                            text: y.answer_text,
                            themeId: y.theme_id,
                            caseId: y.case_id,
                            yNodeId: y.id,
                          })
                        }
                        className={`relative rounded-xl border bg-[#13171b]/95 px-3 py-2.5 transition cursor-pointer ${
                          isHi
                            ? "border-emerald-400/70 shadow-lg shadow-emerald-950/50"
                            : "border-white/10 hover:border-white/25"
                        } ${isDim ? "opacity-30" : "opacity-100"}`}
                      >
                        <span className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-emerald-400/80 border border-[#0d0f13]" />

                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span
                              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                y.strength === "strong"
                                  ? "bg-emerald-400"
                                  : y.strength === "weak"
                                  ? "bg-amber-400"
                                  : "bg-slate-500"
                              }`}
                            />
                            <span className="text-[10px] font-mono text-slate-400 uppercase truncate">
                              {y.has_answer ? y.strength : "unanswered"}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(y.id);
                            }}
                            className="p-0.5 text-slate-500 hover:text-slate-200 shrink-0"
                          >
                            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        <div
                          className={`text-[12px] mt-1 leading-snug ${
                            y.has_answer ? "text-slate-200" : "text-slate-500 italic"
                          } ${open ? "" : "line-clamp-1"}`}
                        >
                          {y.has_answer ? y.answer_text : "No answer recorded yet"}
                        </div>

                        {open && (
                          <div
                            className="mt-2 pt-2 border-t border-white/10 space-y-2"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {editingYId === y.id && xNode ? (
                              <div className="space-y-1.5">
                                <textarea
                                  rows={3}
                                  className="g-input text-[11px] w-full select-text"
                                  placeholder="Type client's factual answer…"
                                  value={editingYText}
                                  onChange={(e) => setEditingYText(e.target.value)}
                                />
                                <div className="flex justify-end gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => setEditingYId(null)}
                                    className="px-2 py-1 rounded text-[10px] text-slate-400 hover:text-white"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    disabled={savingY}
                                    onClick={() => handleSaveYAnswer(xNode)}
                                    className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-semibold"
                                  >
                                    {savingY ? "Saving…" : "Save"}
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <>
                                {y.feedback && <p className="text-[10px] text-emerald-300/80">{y.feedback}</p>}
                                <button
                                  type="button"
                                  onClick={() => {
                                    setEditingYId(y.id);
                                    setEditingYText(y.has_answer ? y.answer_text : "");
                                  }}
                                  className="text-[10px] text-emerald-300 hover:text-emerald-200 inline-flex items-center gap-1"
                                >
                                  <Edit3 className="w-3 h-3" /> {y.has_answer ? "Edit Answer" : "Record Answer"}
                                </button>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* ── LANE Z: OFFICIAL EMBASSY QUESTIONS ── */}
                <div className="w-[248px] space-y-2.5 shrink-0">
                  <LaneHeader dot="bg-[#e5b84b]" code="Z" title="Official Questions" count={visibleZ.length} />
                  {visibleZ.map((z) => {
                    const open = Boolean(expandedIds[z.id]);
                    const isHi = highlightedIds.has(z.id);
                    const isDim = highlightedIds.size > 0 && !isHi;

                    return (
                      <div
                        key={z.id}
                        data-qb-node="true"
                        ref={(el) => {
                          nodeRefs.current[z.id] = el;
                        }}
                        onClick={() => setSelectedNodeId((p) => (p === z.id ? null : z.id))}
                        onDoubleClick={() => toggleExpand(z.id)}
                        onContextMenu={(e) =>
                          openContextMenu(e, {
                            nodeId: z.id,
                            lane: "Z",
                            label: `Official ${z.visa_class} · ${z.frequency}×`,
                            text: z.question_text,
                            themeId: z.theme_id,
                            dbId: z.db_id,
                          })
                        }
                        className={`relative rounded-xl border bg-[#13171b]/95 px-3 py-2.5 transition cursor-pointer ${
                          isHi
                            ? "border-[#e5b84b]/75 shadow-lg shadow-amber-950/40"
                            : "border-white/10 hover:border-white/25"
                        } ${isDim ? "opacity-30" : "opacity-100"}`}
                      >
                        <span className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-[#e5b84b]/80 border border-[#0d0f13]" />

                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#e5b84b] shrink-0" />
                            <span className="text-[10px] font-mono text-slate-400 truncate">
                              {z.visa_class} · {z.frequency}× · {z.difficulty}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(z.id);
                            }}
                            className="p-0.5 text-slate-500 hover:text-slate-200 shrink-0"
                          >
                            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        <div className={`text-[12px] text-slate-100 mt-1 leading-snug ${open ? "" : "line-clamp-1"}`}>
                          {z.question_text}
                        </div>

                        {open && (
                          <div className="mt-2 pt-2 border-t border-white/10 flex items-center justify-between text-[10px] font-mono text-slate-500">
                            <span>{z.theme_id.replace(/_/g, " ")}</span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                speakOfficer(z.question_text);
                              }}
                              className="text-slate-300 hover:text-white inline-flex items-center gap-1"
                            >
                              <Volume2 className="w-3 h-3" /> Voice
                            </button>
                          </div>
                        )}

                        <span className="absolute -right-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-[#e5b84b]/80 border border-[#0d0f13]" />
                      </div>
                    );
                  })}
                </div>

                {/* ── LANE A: OFFICIAL ANSWERS & OUTCOMES ── */}
                <div className="w-[248px] space-y-2.5 shrink-0">
                  <LaneHeader dot="bg-rose-400" code="A" title="Official Answers" count={visibleA.length} />
                  {visibleA.map((a) => {
                    const open = Boolean(expandedIds[a.id]);
                    const isHi = highlightedIds.has(a.id);
                    const isDim = highlightedIds.size > 0 && !isHi;

                    return (
                      <div
                        key={a.id}
                        data-qb-node="true"
                        ref={(el) => {
                          nodeRefs.current[a.id] = el;
                        }}
                        onClick={() => setSelectedNodeId((p) => (p === a.id ? null : a.id))}
                        onDoubleClick={() => toggleExpand(a.id)}
                        onContextMenu={(e) =>
                          openContextMenu(e, {
                            nodeId: a.id,
                            lane: "A",
                            label: `Outcome · ${a.outcome_tag.toUpperCase()}`,
                            text: a.answer_text,
                            themeId: a.theme_id,
                            dbId: a.db_id,
                          })
                        }
                        className={`relative rounded-xl border bg-[#13171b]/95 px-3 py-2.5 transition cursor-pointer ${
                          isHi
                            ? "border-rose-400/70 shadow-lg shadow-rose-950/40"
                            : "border-white/10 hover:border-white/25"
                        } ${isDim ? "opacity-30" : "opacity-100"}`}
                      >
                        <span className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-rose-400/80 border border-[#0d0f13]" />

                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span
                              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                a.outcome_tag === "approved"
                                  ? "bg-emerald-400"
                                  : a.outcome_tag === "refused"
                                  ? "bg-red-400"
                                  : "bg-blue-400"
                              }`}
                            />
                            <span className="text-[10px] font-mono uppercase text-slate-400 truncate">
                              {a.outcome_tag} · {a.usage_count}×
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(a.id);
                            }}
                            className="p-0.5 text-slate-500 hover:text-slate-200 shrink-0"
                          >
                            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        <div className={`text-[12px] text-slate-200 mt-1 leading-snug ${open ? "" : "line-clamp-1"}`}>
                          {a.answer_text}
                        </div>

                        {open && a.notes && (
                          <div className="mt-2 pt-2 border-t border-white/10 text-[10px] text-slate-400 italic leading-relaxed">
                            {a.notes}
                          </div>
                        )}

                        <span className="absolute -right-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-teal-400/80 border border-[#0d0f13]" />
                      </div>
                    );
                  })}
                </div>

                {/* ── LANE OUTPUT: PROPAGATION GENERATED QUESTIONS ── */}
                <div className="w-[260px] space-y-2.5 shrink-0">
                  <LaneHeader
                    dot="bg-teal-400"
                    code="OUT"
                    title={freshOutputs.length > 0 ? "Generated Output" : "Output Queue"}
                    count={outputNodes.length}
                  />
                  {outputNodes.map((out) => {
                    const open = Boolean(expandedIds[out.id]);
                    const isHi = highlightedIds.has(out.id);

                    return (
                      <div
                        key={out.id}
                        data-qb-node="true"
                        ref={(el) => {
                          nodeRefs.current[out.id] = el;
                        }}
                        onClick={() => setSelectedNodeId((p) => (p === out.id ? null : out.id))}
                        onDoubleClick={() => toggleExpand(out.id)}
                        onContextMenu={(e) =>
                          openContextMenu(e, {
                            nodeId: out.id,
                            lane: "OUT",
                            label: `Output · ${out.case_id}`,
                            text: out.question_text,
                            themeId: out.theme_id,
                            caseId: out.case_id,
                          })
                        }
                        className={`relative rounded-xl border bg-[#11191a]/95 px-3 py-2.5 transition cursor-pointer ${
                          out.fresh || isHi
                            ? "border-teal-400/75 shadow-lg shadow-teal-950/50"
                            : "border-teal-400/25 hover:border-teal-400/50"
                        }`}
                      >
                        <span className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-teal-400 border border-[#0d0f13]" />

                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <Sparkles className="w-3 h-3 text-teal-400 shrink-0" />
                            <span className="text-[10px] font-mono text-teal-300 truncate">
                              {out.fresh ? "NEW" : out.case_id} · {out.theme_id.replace(/_/g, " ")}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(out.id);
                            }}
                            className="p-0.5 text-slate-500 hover:text-slate-200 shrink-0"
                          >
                            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        <div className={`text-[12px] text-white mt-1 leading-snug ${open ? "" : "line-clamp-2"}`}>
                          {out.question_text}
                        </div>

                        {open && (
                          <div className="mt-2 pt-2 border-t border-white/10 space-y-1.5 text-[11px] text-slate-400">
                            <p className="leading-relaxed">{out.rationale}</p>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                speakOfficer(out.question_text);
                              }}
                              className="text-[10px] text-teal-300 hover:text-teal-200 inline-flex items-center gap-1"
                            >
                              <Volume2 className="w-3 h-3" /> Play Officer Voice
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Subtle Floating Zoom Controls (Bottom-Left) */}
          <div className="absolute bottom-4 left-4 z-20 flex items-center gap-1 bg-[#0f1311]/90 backdrop-blur border border-white/10 rounded-full px-2 py-1 shadow-xl text-[11px] text-slate-300">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(0.4, Number((z - 0.12).toFixed(2))))}
              className="p-1 rounded-full hover:bg-white/10 hover:text-white transition"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="font-mono w-10 text-center text-[10px] text-slate-400">
              {Math.round(zoom * 100)}%
            </span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(1.8, Number((z + 0.12).toFixed(2))))}
              className="p-1 rounded-full hover:bg-white/10 hover:text-white transition"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <div className="w-px h-3 bg-white/10 mx-0.5" />
            <button
              type="button"
              onClick={fitToView}
              className="p-1 rounded-full hover:bg-white/10 hover:text-white transition"
              title="Fit canvas to view"
            >
              <Maximize2 className="w-3 h-3" />
            </button>
          </div>

          {/* Subtle Hint Bottom-Right of Canvas */}
          <div className="absolute bottom-4 right-4 z-20 hidden md:block text-[10px] text-slate-600 pointer-events-none">
            Scroll to zoom · Drag to pan · Click ▾ or right-click any node
          </div>
        </div>

        {/* ── RIGHT: CLEAN CHAT SIDE PANEL (No extra buttons/tabs — just text!) ── */}
        {chatOpen && (
          <aside className="w-[340px] lg:w-[370px] h-full bg-[#0f1311] border-l border-[#e5b84b]/12 flex flex-col shrink-0 select-text">
            <div className="h-11 px-4 border-b border-white/5 flex items-center justify-between shrink-0">
              <span className="text-xs font-semibold text-slate-200">Quiz Chat</span>
              <span className="text-[10px] text-slate-500">Type to control flow</span>
            </div>

            <div ref={chatScrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col justify-center space-y-4">
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-slate-200">Control the canvas by texting.</p>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      Filter questions, trace effective pathways, generate new output questions, mine hidden patterns, add official Q&amp;As, or print PDFs.
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    {[
                      "Generate 4 questions for C034",
                      "Trace effective pathway & who gets approved most",
                      "Find all hidden patterns",
                      "Filter hardest questions",
                      "Print questions PDF",
                    ].map((hint) => (
                      <button
                        key={hint}
                        type="button"
                        onClick={() => sendChat(hint)}
                        className="w-full text-left px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.07] text-[11px] text-slate-300 transition"
                      >
                        {hint}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m, idx) => (
                  <div
                    key={idx}
                    className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
                  >
                    <div
                      className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed ${
                        m.sender === "user"
                          ? "bg-white/[0.09] text-white"
                          : "bg-[#151a18] border border-white/[0.07] text-slate-200"
                      }`}
                    >
                      {m.sender === "assistant" ? <RichMarkdown content={m.content} /> : m.content}
                      {m.print_pdf_url && (
                        <button
                          type="button"
                          onClick={() => openPdfUrl(m.print_pdf_url!)}
                          className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#e5b84b]/15 border border-[#e5b84b]/30 text-[#e5b84b] text-[11px] font-medium hover:bg-[#e5b84b]/25 transition"
                        >
                          <Printer className="w-3 h-3" /> Open Printable PDF
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}

              {chatBusy && (
                <div className="text-[11px] text-slate-500 animate-pulse px-1">Updating flow…</div>
              )}
            </div>

            {/* Signature Rounded Graphite Prompt Pill */}
            <div className="p-3 border-t border-white/5 shrink-0">
              <div className="flex items-center gap-1.5 bg-[#151a18] border border-[#e5b84b]/20 rounded-full px-3 py-1.5 focus-within:border-[#e5b84b]/55 transition">
                <input
                  className="flex-1 min-w-0 bg-transparent border-0 outline-none text-xs text-slate-100 placeholder:text-slate-500 px-1"
                  placeholder="Generate, filter, trace, print…"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendChat()}
                />
                <button
                  type="button"
                  disabled={chatBusy || !chatInput.trim()}
                  onClick={() => sendChat()}
                  className="p-1.5 rounded-full bg-white/10 hover:bg-emerald-600 text-white disabled:opacity-40 transition shrink-0"
                  title="Send"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* ── RIGHT-CLICK NODE CONTEXT MENU ──────────────────────────────────── */}
      {contextMenu && (
        <div
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
          className="fixed z-[60] w-52 rounded-xl bg-[#151a18] border border-white/15 shadow-2xl p-1.5 text-xs text-slate-200 space-y-0.5"
        >
          <div className="px-2.5 py-1 text-[10px] font-mono text-slate-500 truncate border-b border-white/10 mb-1">
            {contextMenu.label}
          </div>

          <button
            type="button"
            onClick={() => {
              toggleExpand(contextMenu.nodeId);
              setContextMenu(null);
            }}
            className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/10 flex items-center gap-2"
          >
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            {expandedIds[contextMenu.nodeId] ? "Collapse Details" : "Expand Details"}
          </button>

          <button
            type="button"
            onClick={() => {
              setSelectedNodeId(contextMenu.nodeId);
              setFlowPulse(true);
              setContextMenu(null);
            }}
            className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/10 flex items-center gap-2"
          >
            <Route className="w-3.5 h-3.5 text-emerald-400" />
            Trace Propagation Flow
          </button>

          {(contextMenu.lane === "X" || contextMenu.lane === "Z" || contextMenu.lane === "OUT") && (
            <button
              type="button"
              onClick={() => {
                speakOfficer(contextMenu.text);
                setContextMenu(null);
              }}
              className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/10 flex items-center gap-2"
            >
              <Volume2 className="w-3.5 h-3.5 text-blue-400" />
              Play Officer Voice
            </button>
          )}

          {(contextMenu.lane === "X" || contextMenu.lane === "Y") && contextMenu.yNodeId && (
            <button
              type="button"
              onClick={() => {
                const yId = contextMenu.yNodeId!;
                const yObj = visibleY.find((i) => i.id === yId);
                setExpandedIds((p) => ({ ...p, [yId]: true }));
                setEditingYId(yId);
                setEditingYText(yObj?.has_answer ? yObj.answer_text : "");
                setContextMenu(null);
              }}
              className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/10 flex items-center gap-2"
            >
              <Edit3 className="w-3.5 h-3.5 text-[#e5b84b]" />
              Record / Edit Answer
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              setChatOpen(true);
              setChatInput(`Explain and coach on: "${contextMenu.text.slice(0, 90)}"`);
              setContextMenu(null);
            }}
            className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/10 flex items-center gap-2"
          >
            <MessageSquare className="w-3.5 h-3.5 text-teal-400" />
            Ask Chat About Node
          </button>

          {(contextMenu.lane === "Z" || contextMenu.lane === "A") && contextMenu.dbId && (
            <button
              type="button"
              onClick={() => {
                handleDeleteOfficial(contextMenu.dbId!);
                setContextMenu(null);
              }}
              className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-red-500/20 text-red-300 flex items-center gap-2"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete Official Q&amp;A
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function LaneHeader({
  dot,
  code,
  title,
  count,
}: {
  dot: string;
  code: string;
  title: string;
  count: number;
}) {
  return (
    <div className="flex items-center justify-between px-1 pb-1.5 border-b border-white/[0.07]">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        <span className="text-[10px] font-mono font-bold text-slate-400">{code}</span>
        <span className="text-[11px] font-semibold text-slate-200">{title}</span>
      </div>
      <span className="text-[10px] font-mono text-slate-500">{count}</span>
    </div>
  );
}
