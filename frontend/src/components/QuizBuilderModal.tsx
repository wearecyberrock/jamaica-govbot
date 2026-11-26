"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Sparkles,
  GitBranch,
  Filter,
  Printer,
  Plus,
  Search,
  Volume2,
  X,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  Layers,
  Trash2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
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

interface EdgeItem {
  from: string;
  to: string;
  kind: "x_to_y" | "x_to_z" | "z_to_a";
  theme_id: string;
  strength?: string;
  outcome_tag?: string;
  weight?: number;
}

interface CohortStat {
  cohort_id: string;
  label: string;
  summary: string;
  total_clients: number;
  decided_cases: number;
  approved_count: number;
  refused_count: number;
  approval_rate_pct: number | null;
  avg_standing_score: number;
  top_themes: string[];
  sample_label: string;
}

interface CanvasResponse {
  scope: {
    case_id: string;
    client_name: string;
    standing_score: number | null;
    denial_risk_level: string | null;
    cohort: string;
    q_filter: string;
    a_filter: string;
    visa_class: string;
  };
  lane_x: LaneXItem[];
  lane_y: LaneYItem[];
  lane_z: LaneZItem[];
  lane_a: LaneAItem[];
  edges: EdgeItem[];
  effective: {
    enabled: boolean;
    pathway_node_ids: string[];
    pathway_steps: Array<{
      theme_id: string;
      x_question: string;
      y_answer: string;
      y_strength: string;
      z_official_question: string;
      a_winning_pattern: string;
      outcome_tag: string;
    }>;
    cohort_stats: CohortStat[];
    top_approving_profile: CohortStat | null;
  };
  clients_picker: Array<{
    case_id: string;
    full_name: string;
    visa_class: string;
    standing_score: number;
    outcome: string;
  }>;
}

interface PatternAnalysis {
  provider_used: string;
  dataset_summary: {
    total_cases: number;
    approved_cases: number;
    refused_cases: number;
    embassy_events: number;
    official_qa_count: number;
    avg_approved_standing: number;
    avg_refused_standing: number;
  };
  cohort_stats: CohortStat[];
  trait_patterns: Array<{
    trait: string;
    approved: number;
    refused: number;
    total: number;
    approval_rate_pct: number;
    signal: string;
  }>;
  question_chains: Array<{
    from_theme: string;
    to_theme: string;
    occurrences: number;
    insight: string;
  }>;
  co_occurring_risks: Array<{
    flag_a: string;
    flag_b: string;
    cases_affected: number;
    insight: string;
  }>;
  anomalies: string[];
  executive_summary: string;
}

export function QuizBuilderModal({
  initialCaseId,
  onClose,
}: {
  initialCaseId: string | null;
  onClose: () => void;
}) {
  const [caseId, setCaseId] = useState<string>(initialCaseId || "ALL");
  const [cohort, setCohort] = useState<string>("all");
  const [qFilter, setQFilter] = useState<string>("all");
  const [aFilter, setAFilter] = useState<string>("all");
  const [visaClass, setVisaClass] = useState<string>("all");
  const [effectiveMode, setEffectiveMode] = useState<boolean>(false);

  const [data, setData] = useState<CanvasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyGen, setBusyGen] = useState(false);
  const [busyPatterns, setBusyPatterns] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  // Active node selection for relationship highlighting
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Inline Y answer editing
  const [editingYId, setEditingYId] = useState<string | null>(null);
  const [draftAnswer, setDraftAnswer] = useState("");

  // Add Official Q&A (Z + A) modal drawer
  const [showAddOfficial, setShowAddOfficial] = useState(false);
  const [newTheme, setNewTheme] = useState("purpose_of_trip");
  const [newVisa, setNewVisa] = useState("B1/B2");
  const [newDiff, setNewDiff] = useState("hard");
  const [newOutcome, setNewOutcome] = useState("approved");
  const [newQText, setNewQText] = useState("");
  const [newAText, setNewAText] = useState("");
  const [newNotes, setNewNotes] = useState("");

  // Hidden Patterns Analysis panel
  const [patterns, setPatterns] = useState<PatternAnalysis | null>(null);

  // SVG relationship connector lines
  const canvasWrapRef = useRef<HTMLDivElement | null>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [svgLines, setSvgLines] = useState<
    Array<{
      key: string;
      d: string;
      kind: EdgeItem["kind"];
      highlighted: boolean;
      dimmed: boolean;
    }>
  >([]);
  const [svgSize, setSvgSize] = useState({ w: 1200, h: 800 });

  const flash = (msg: string) => {
    setStatusMsg(msg);
    setTimeout(() => setStatusMsg(""), 4500);
  };

  const loadCanvas = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({
        case_id: caseId,
        cohort,
        q_filter: qFilter,
        a_filter: aFilter,
        visa_class: visaClass,
        effective_mode: String(effectiveMode),
      });
      const res = await apiFetch<CanvasResponse>(`/api/quiz-builder/canvas?${qs.toString()}`);
      setData(res);
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : "Failed to load Quiz Builder canvas");
    } finally {
      setLoading(false);
    }
  }, [caseId, cohort, qFilter, aFilter, visaClass, effectiveMode]);

  useEffect(() => {
    loadCanvas();
  }, [loadCanvas]);

  // Compute connected node set for interactive highlighting
  const activeChain = useMemo(() => {
    const edges = data?.edges || [];
    if (selectedNodeId) {
      const visited = new Set<string>([selectedNodeId]);
      // BFS up to 3 hops across X <-> Y <-> Z <-> A
      for (let hop = 0; hop < 3; hop++) {
        for (const e of edges) {
          if (visited.has(e.from)) visited.add(e.to);
          if (visited.has(e.to)) visited.add(e.from);
        }
      }
      return visited;
    }
    if (effectiveMode && data?.effective.pathway_node_ids.length) {
      return new Set<string>(data.effective.pathway_node_ids);
    }
    return null;
  }, [selectedNodeId, effectiveMode, data]);

  // Measure real card centers and compute smooth SVG Bezier edges
  const recomputeLines = useCallback(() => {
    const wrap = canvasWrapRef.current;
    if (!wrap || !data) return;
    const wrapRect = wrap.getBoundingClientRect();
    setSvgSize({ w: wrap.scrollWidth, h: wrap.scrollHeight });

    const nextLines: typeof svgLines = [];
    for (const e of data.edges) {
      const elA = nodeRefs.current[e.from];
      const elB = nodeRefs.current[e.to];
      if (!elA || !elB) continue;
      const rA = elA.getBoundingClientRect();
      const rB = elB.getBoundingClientRect();

      const x1 = rA.right - wrapRect.left + wrap.scrollLeft;
      const y1 = rA.top - wrapRect.top + wrap.scrollTop + rA.height / 2;
      const x2 = rB.left - wrapRect.left + wrap.scrollLeft;
      const y2 = rB.top - wrapRect.top + wrap.scrollTop + rB.height / 2;

      const dx = Math.max(28, Math.abs(x2 - x1) * 0.45);
      const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

      const highlighted = Boolean(activeChain && activeChain.has(e.from) && activeChain.has(e.to));
      const dimmed = Boolean(activeChain && !highlighted);
      nextLines.push({ key: `${e.from}__${e.to}`, d, kind: e.kind, highlighted, dimmed });
    }
    setSvgLines(nextLines);
  }, [data, activeChain]);

  useLayoutEffect(() => {
    const t = setTimeout(recomputeLines, 60);
    window.addEventListener("resize", recomputeLines);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", recomputeLines);
    };
  }, [recomputeLines]);

  const handleGenerate = async () => {
    setBusyGen(true);
    try {
      const target = caseId !== "ALL" ? caseId : data?.clients_picker?.[0]?.case_id || "C034";
      const res = await apiFetch<{ case_id: string; provider: string; generated: unknown[] }>(
        "/api/quiz-builder/generate",
        {
          method: "POST",
          body: JSON.stringify({ case_id: target, count: 4, focus: qFilter }),
        }
      );
      flash(`Generated ${res.generated.length} relationship-mapped questions for ${res.case_id} (${res.provider})!`);
      await loadCanvas();
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setBusyGen(false);
    }
  };

  const handleAnalyzePatterns = async () => {
    setBusyPatterns(true);
    try {
      const res = await apiFetch<PatternAnalysis>("/api/quiz-builder/analyze-patterns", {
        method: "POST",
        body: JSON.stringify({ case_id: caseId !== "ALL" ? caseId : null }),
      });
      setPatterns(res);
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : "Pattern analysis failed");
    } finally {
      setBusyPatterns(false);
    }
  };

  const handlePrintPdf = async (includeAnswers = true) => {
    const token = localStorage.getItem("jahtaria_govbot_token") || "";
    const qs = new URLSearchParams({
      case_id: caseId,
      q_filter: qFilter,
      include_answers: String(includeAnswers),
    });
    const res = await fetch(`/api/quiz-builder/print-pdf?${qs.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      flash("Could not generate printable PDF.");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const handleSaveOfficialQA = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newQText.trim()) return;
    await apiFetch("/api/quiz-builder/official-qa", {
      method: "POST",
      body: JSON.stringify({
        theme_id: newTheme,
        visa_class: newVisa,
        difficulty: newDiff,
        outcome_tag: newOutcome,
        question_text: newQText,
        answer_text: newAText,
        answer_quality: newOutcome === "refused" ? "weak" : "strong",
        notes: newNotes,
      }),
    });
    setNewQText("");
    setNewAText("");
    setNewNotes("");
    setShowAddOfficial(false);
    flash("Added Official Question (Z) & Answer Pattern (A) to relationship canvas!");
    await loadCanvas();
  };

  const handleSaveYAnswer = async (yItem: LaneYItem) => {
    const xItem = data?.lane_x.find((x) => x.id === yItem.x_id);
    if (!xItem) return;
    const res = await apiFetch<{ standing_score: number; score_breakdown?: { data_and_docs_score: number; practice_bonus: number } }>(
      "/api/quiz-builder/save-answer",
      {
        method: "POST",
        body: JSON.stringify({
          case_id: xItem.case_id,
          source_type: xItem.source_type,
          db_id: xItem.db_id,
          theme_id: xItem.theme_id,
          question_text: xItem.question_text,
          answer_text: draftAnswer,
        }),
      }
    );
    setEditingYId(null);
    setDraftAnswer("");
    const bd = res.score_breakdown;
    flash(
      bd
        ? `Saved practice answer! Standing: ${res.standing_score}% (Docs/Data ${bd.data_and_docs_score}% + Practice +${bd.practice_bonus})`
        : "Saved practice answer!"
    );
    await loadCanvas();
  };

  const speakOfficer = async (text: string) => {
    try {
      const token = localStorage.getItem("jahtaria_govbot_token") || "";
      const r = await fetch("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ text, persona: "officer_us" }),
      });
      if (r.ok) {
        const audio = new Audio(URL.createObjectURL(await r.blob()));
        audio.play();
      }
    } catch {
      // ignore audio playback error
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#0b0d12]/96 backdrop-blur-md flex flex-col text-slate-100">
      {/* ── TOP COMMAND HEADER ────────────────────────────────────────────── */}
      <div className="px-4 py-3 border-b border-white/10 bg-[#11141c] flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-blue-300 shrink-0">
            <GitBranch className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-white truncate">
              Quiz Builder — Interview Prediction &amp; Relationship Studio (X · Y · Z · A)
            </h2>
            <p className="text-[11px] text-slate-400 truncate">
              Map Generated Questions (X) → Client Answers (Y) ↔ Official Embassy Questions (Z) → Winning Proof Outcomes (A)
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={busyGen}
            className="g-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5"
            id="quiz-generate-btn"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {busyGen ? "Generating…" : "Generate Questions"}
          </button>

          <button
            type="button"
            onClick={() => setEffectiveMode((v) => !v)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold border inline-flex items-center gap-1.5 transition ${
              effectiveMode
                ? "bg-emerald-500/20 border-emerald-400/50 text-emerald-200"
                : "bg-white/5 border-white/10 text-slate-300 hover:bg-white/10"
            }`}
            id="quiz-effective-btn"
          >
            <TrendingUp className="w-3.5 h-3.5" />
            Effective Pathway {effectiveMode ? "ON" : "OFF"}
          </button>

          <button
            type="button"
            onClick={handleAnalyzePatterns}
            disabled={busyPatterns}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-amber-500/15 hover:bg-amber-500/25 border border-amber-400/40 text-amber-200 inline-flex items-center gap-1.5 transition"
            id="quiz-patterns-btn"
          >
            <Search className="w-3.5 h-3.5" />
            {busyPatterns ? "Mining Patterns…" : "Analyze Hidden Patterns"}
          </button>

          <button
            type="button"
            onClick={() => handlePrintPdf(true)}
            className="g-btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5"
            title="Download / Print Formatted Question Sheet PDF"
            id="quiz-print-btn"
          >
            <Printer className="w-3.5 h-3.5" />
            Print Questions
          </button>

          <button
            type="button"
            onClick={() => setShowAddOfficial((v) => !v)}
            className="g-btn-ghost px-3 py-1.5 text-xs inline-flex items-center gap-1.5"
            id="quiz-add-official-btn"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Official Q&amp;A (Z/A)
          </button>

          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl bg-white/5 hover:bg-red-500/20 text-slate-300 hover:text-red-300 transition"
            title="Close Quiz Builder"
            id="quiz-close-btn"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── FILTER & SCOPE TOOLBAR ────────────────────────────────────────── */}
      <div className="px-4 py-2.5 border-b border-white/10 bg-[#0e1017] flex flex-wrap items-center gap-2.5 text-xs shrink-0">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Filter className="w-3.5 h-3.5" />
          <span className="font-semibold">Scope:</span>
        </div>

        <select
          value={caseId}
          onChange={(e) => {
            setCaseId(e.target.value);
            setSelectedNodeId(null);
          }}
          className="bg-[#181c26] border border-white/15 rounded-lg px-2.5 py-1 text-xs text-white outline-none max-w-[230px]"
          aria-label="Client Scope"
          id="quiz-client-select"
        >
          <option value="ALL">All Clients (General Question Bank)</option>
          {(data?.clients_picker || []).map((c) => (
            <option key={c.case_id} value={c.case_id}>
              {c.case_id} — {c.full_name} ({c.standing_score}%)
            </option>
          ))}
        </select>

        {caseId === "ALL" && (
          <select
            value={cohort}
            onChange={(e) => setCohort(e.target.value)}
            className="bg-[#181c26] border border-white/15 rounded-lg px-2.5 py-1 text-xs text-slate-200 outline-none"
            aria-label="Client Cohort"
          >
            <option value="all">All Client Types</option>
            <option value="employed_b1b2">Employed Professionals (B1/B2)</option>
            <option value="first_time">First-Time Applicants</option>
            <option value="self_employed">Self-Employed / Business</option>
            <option value="prior_refusal">Prior Refusals</option>
            <option value="us_relatives">Has U.S. Relatives</option>
            <option value="student_f1">Students (F-1)</option>
          </select>
        )}

        <div className="flex items-center gap-1 bg-[#181c26] p-0.5 rounded-lg border border-white/10">
          {[
            ["all", "All Qs"],
            ["most_common", "Most Common"],
            ["hardest", "Hardest"],
            ["weak", "Weak / Risky"],
            ["most_used", "Most Used"],
          ].map(([k, lbl]) => (
            <button
              key={k}
              type="button"
              onClick={() => setQFilter(k)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition ${
                qFilter === k ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              {lbl}
            </button>
          ))}
        </div>

        <select
          value={aFilter}
          onChange={(e) => setAFilter(e.target.value)}
          className="bg-[#181c26] border border-white/15 rounded-lg px-2.5 py-1 text-xs text-slate-200 outline-none"
          aria-label="Answer Filter"
        >
          <option value="all">All Answers</option>
          <option value="most_common">Most Common Answers</option>
          <option value="approved">Approved / Strong Patterns</option>
          <option value="weak">Weak / Needs Work</option>
        </select>

        <select
          value={visaClass}
          onChange={(e) => setVisaClass(e.target.value)}
          className="bg-[#181c26] border border-white/15 rounded-lg px-2.5 py-1 text-xs text-slate-200 outline-none"
          aria-label="Visa Class Filter"
        >
          <option value="all">All Visa Classes</option>
          <option value="B1/B2">B1/B2 Visitor</option>
          <option value="F-1">F-1 Student</option>
          <option value="H-2B">H-2B Work</option>
        </select>

        {selectedNodeId && (
          <button
            type="button"
            onClick={() => setSelectedNodeId(null)}
            className="text-[11px] text-amber-300 hover:underline ml-auto"
          >
            Clear Highlight ({selectedNodeId})
          </button>
        )}
      </div>

      {statusMsg && (
        <div className="px-4 py-2 bg-emerald-500/15 border-b border-emerald-400/30 text-xs text-emerald-200 shrink-0">
          {statusMsg}
        </div>
      )}

      {/* ── INLINE ADD OFFICIAL Q&A FORM (LANES Z & A) ────────────────────── */}
      {showAddOfficial && (
        <form
          onSubmit={handleSaveOfficialQA}
          className="px-4 py-3 bg-[#151923] border-b border-blue-400/30 grid grid-cols-1 md:grid-cols-6 gap-2.5 text-xs shrink-0"
        >
          <input
            className="g-input text-xs md:col-span-2"
            required
            placeholder="Official Embassy / Organization Question (Lane Z)..."
            value={newQText}
            onChange={(e) => setNewQText(e.target.value)}
          />
          <input
            className="g-input text-xs md:col-span-2"
            placeholder="Official / Winning Answer Pattern or Reported Answer (Lane A)..."
            value={newAText}
            onChange={(e) => setNewAText(e.target.value)}
          />
          <div className="flex gap-1.5">
            <select className="g-input text-xs" value={newTheme} onChange={(e) => setNewTheme(e.target.value)}>
              <option value="purpose_of_trip">Purpose</option>
              <option value="employment">Employment</option>
              <option value="monthly_income">Income (JMD)</option>
              <option value="funding_trip">Funding</option>
              <option value="us_relatives">U.S. Relatives</option>
              <option value="prior_refusal">Prior Refusal</option>
              <option value="business_income">Business</option>
              <option value="travel_history">Travel History</option>
              <option value="study_plan">F-1 Study</option>
            </select>
            <select className="g-input text-xs" value={newDiff} onChange={(e) => setNewDiff(e.target.value)}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </div>
          <div className="flex gap-1.5">
            <select className="g-input text-xs" value={newOutcome} onChange={(e) => setNewOutcome(e.target.value)}>
              <option value="approved">Approved</option>
              <option value="refused">Refused (214b)</option>
              <option value="policy">Policy</option>
            </select>
            <button type="submit" className="g-btn-primary px-3 text-xs shrink-0">
              Save Z/A
            </button>
          </div>
        </form>
      )}

      {/* ── EFFECTIVE PATHWAY & TOP APPROVING CLIENT TYPES STRIP ─────────── */}
      {effectiveMode && data && (
        <div className="px-4 py-3 bg-[#101820] border-b border-emerald-400/25 space-y-2.5 shrink-0 max-h-[230px] overflow-y-auto">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4" />
              Effective Pathway &amp; Client Types Getting Approved Most ({data.scope.client_name})
            </div>
            <div className="text-[11px] text-slate-400">
              Glowing lines below trace the active pathway from X → Y → Z → A
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-2">
            {data.effective.cohort_stats.map((cs) => (
              <button
                key={cs.cohort_id}
                type="button"
                onClick={() => {
                  setCaseId("ALL");
                  setCohort(cs.cohort_id);
                }}
                className={`text-left p-2.5 rounded-xl border transition ${
                  cohort === cs.cohort_id
                    ? "bg-emerald-500/20 border-emerald-400/50"
                    : "bg-white/[0.03] border-white/10 hover:bg-white/[0.07]"
                }`}
              >
                <div className="text-[11px] font-semibold text-white truncate">{cs.label}</div>
                <div className="flex items-baseline justify-between mt-1">
                  <span className="text-base font-extrabold text-emerald-400">
                    {cs.approval_rate_pct !== null ? `${cs.approval_rate_pct}%` : "Prep"}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">{cs.sample_label}</span>
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                  Avg Docs/Data: {cs.avg_standing_score}%
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── MAIN 4-COLUMN RELATIONSHIP DIAGRAM CANVAS (X · Y · Z · A) ────── */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        <div
          ref={canvasWrapRef}
          onScroll={recomputeLines}
          className="flex-1 relative overflow-auto p-5"
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)",
            backgroundSize: "20px 20px",
          }}
        >
          {/* SVG Relationship Connector Layer */}
          <svg
            width={svgSize.w}
            height={svgSize.h}
            className="pointer-events-none absolute top-0 left-0 z-0"
          >
            {svgLines.map((ln) => {
              const stroke =
                ln.kind === "x_to_z"
                  ? ln.highlighted
                    ? "#38bdf8"
                    : "rgba(56,189,248,0.28)"
                  : ln.kind === "x_to_y"
                  ? ln.highlighted
                    ? "#34d399"
                    : "rgba(148,163,184,0.26)"
                  : ln.highlighted
                  ? "#fbbf24"
                  : "rgba(251,191,36,0.28)";
              return (
                <path
                  key={ln.key}
                  d={ln.d}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={ln.highlighted ? 2.6 : 1.3}
                  strokeDasharray={ln.kind === "x_to_z" ? "5 4" : undefined}
                  opacity={ln.dimmed ? 0.14 : 1}
                />
              );
            })}
          </svg>

          {loading ? (
            <div className="h-full flex items-center justify-center text-sm text-slate-400">
              Mapping relationship canvas across database…
            </div>
          ) : (
            <div className="relative z-10 grid grid-cols-4 gap-8 min-w-[1140px]">
              {/* LANE X: GENERATED QUESTIONS */}
              <div className="space-y-3">
                <div className="sticky top-0 z-20 px-3 py-2 rounded-xl bg-[#131a28]/95 border border-blue-400/35 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-mono uppercase text-blue-300 font-bold">Lane X</div>
                    <div className="text-xs font-bold text-white">Generated Questions ({data?.lane_x.length || 0})</div>
                  </div>
                  <Layers className="w-4 h-4 text-blue-400" />
                </div>

                {(data?.lane_x || []).map((x) => {
                  const isHi = activeChain?.has(x.id);
                  const isDim = Boolean(activeChain && !isHi);
                  return (
                    <div
                      key={x.id}
                      ref={(el) => {
                        nodeRefs.current[x.id] = el;
                      }}
                      onClick={() => setSelectedNodeId(selectedNodeId === x.id ? null : x.id)}
                      className={`p-3 rounded-xl border cursor-pointer transition bg-[#151a24] ${
                        isHi
                          ? "border-blue-400 shadow-lg shadow-blue-500/15"
                          : "border-white/10 hover:border-blue-400/50"
                      } ${isDim ? "opacity-30" : ""}`}
                    >
                      <div className="flex items-center justify-between gap-1.5 mb-1.5">
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">
                          {x.case_id} · {x.theme_id.replace(/_/g, " ")}
                        </span>
                        <div className="flex items-center gap-1">
                          <span
                            className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                              x.difficulty === "hard"
                                ? "bg-red-500/20 text-red-300"
                                : x.difficulty === "medium"
                                ? "bg-amber-500/20 text-amber-300"
                                : "bg-emerald-500/20 text-emerald-300"
                            }`}
                          >
                            {x.difficulty}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              speakOfficer(x.question_text);
                            }}
                            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white"
                            title="Play in U.S. Officer Voice"
                          >
                            <Volume2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                      <div className="text-xs text-slate-100 leading-relaxed font-medium">{x.question_text}</div>
                      <div className="mt-1.5 text-[10px] text-slate-400 flex justify-between">
                        <span>Freq: {x.frequency}×</span>
                        <span>Conf: {Math.round(x.confidence * 100)}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* LANE Y: CLIENT / PRACTICE ANSWERS */}
              <div className="space-y-3">
                <div className="sticky top-0 z-20 px-3 py-2 rounded-xl bg-[#11201a]/95 border border-emerald-400/35 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-mono uppercase text-emerald-300 font-bold">Lane Y</div>
                    <div className="text-xs font-bold text-white">Client Answers ({data?.lane_y.length || 0})</div>
                  </div>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                </div>

                {(data?.lane_y || []).map((y) => {
                  const isHi = activeChain?.has(y.id);
                  const isDim = Boolean(activeChain && !isHi);
                  const isEditing = editingYId === y.id;
                  return (
                    <div
                      key={y.id}
                      ref={(el) => {
                        nodeRefs.current[y.id] = el;
                      }}
                      onClick={() => setSelectedNodeId(selectedNodeId === y.id ? null : y.id)}
                      className={`p-3 rounded-xl border cursor-pointer transition bg-[#141a1d] ${
                        isHi
                          ? "border-emerald-400 shadow-lg shadow-emerald-500/15"
                          : "border-white/10 hover:border-emerald-400/50"
                      } ${isDim ? "opacity-30" : ""}`}
                    >
                      <div className="flex items-center justify-between gap-1.5 mb-1.5">
                        <span
                          className={`text-[10px] font-mono uppercase font-bold px-1.5 py-0.5 rounded ${
                            y.strength === "strong"
                              ? "bg-emerald-500/20 text-emerald-300"
                              : y.strength === "weak"
                              ? "bg-amber-500/20 text-amber-300"
                              : "bg-white/10 text-slate-400"
                          }`}
                        >
                          {y.strength}
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingYId(isEditing ? null : y.id);
                            setDraftAnswer(y.has_answer ? y.answer_text : "");
                          }}
                          className="text-[10px] text-blue-300 hover:underline"
                        >
                          {isEditing ? "Cancel" : y.has_answer ? "Edit" : "+ Record Answer"}
                        </button>
                      </div>

                      {isEditing ? (
                        <div className="space-y-1.5" onClick={(e) => e.stopPropagation()}>
                          <textarea
                            rows={2}
                            className="g-input text-xs"
                            placeholder="Type client's live practice answer..."
                            value={draftAnswer}
                            onChange={(e) => setDraftAnswer(e.target.value)}
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveYAnswer(y)}
                            className="g-btn-primary w-full py-1 text-[11px]"
                          >
                            Save Answer (+1 Readiness Only)
                          </button>
                        </div>
                      ) : (
                        <div className={`text-xs leading-relaxed ${y.has_answer ? "text-slate-200" : "text-slate-500 italic"}`}>
                          {y.answer_text}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* LANE Z: OFFICIAL EMBASSY / ORGANIZATION QUESTIONS */}
              <div className="space-y-3">
                <div className="sticky top-0 z-20 px-3 py-2 rounded-xl bg-[#221a10]/95 border border-amber-400/35 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-mono uppercase text-amber-300 font-bold">Lane Z</div>
                    <div className="text-xs font-bold text-white">Official Questions ({data?.lane_z.length || 0})</div>
                  </div>
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                </div>

                {(data?.lane_z || []).map((z) => {
                  const isHi = activeChain?.has(z.id);
                  const isDim = Boolean(activeChain && !isHi);
                  return (
                    <div
                      key={z.id}
                      ref={(el) => {
                        nodeRefs.current[z.id] = el;
                      }}
                      onClick={() => setSelectedNodeId(selectedNodeId === z.id ? null : z.id)}
                      className={`p-3 rounded-xl border cursor-pointer transition bg-[#1b1815] ${
                        isHi
                          ? "border-amber-400 shadow-lg shadow-amber-500/15"
                          : "border-white/10 hover:border-amber-400/50"
                      } ${isDim ? "opacity-30" : ""}`}
                    >
                      <div className="flex items-center justify-between gap-1.5 mb-1.5">
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-200">
                          {z.visa_class} · {z.frequency}× asked
                        </span>
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] uppercase font-bold text-slate-400">{z.difficulty}</span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              speakOfficer(z.question_text);
                            }}
                            className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white"
                            title="Play Official Question Aloud"
                          >
                            <Volume2 className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={async (e) => {
                              e.stopPropagation();
                              await apiFetch(`/api/quiz-builder/official-qa/${z.db_id}`, { method: "DELETE" });
                              loadCanvas();
                            }}
                            className="p-1 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-300"
                            title="Delete Official Q&A"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                      <div className="text-xs text-slate-100 leading-relaxed font-medium">{z.question_text}</div>
                      <div className="mt-1.5 text-[10px] text-slate-400 truncate">
                        Theme: {z.theme_id.replace(/_/g, " ")} · {z.added_by}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* LANE A: OFFICIAL / OUTCOME ANSWERS & WINNING PROOF POINTS */}
              <div className="space-y-3">
                <div className="sticky top-0 z-20 px-3 py-2 rounded-xl bg-[#22121a]/95 border border-rose-400/35 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-mono uppercase text-rose-300 font-bold">Lane A</div>
                    <div className="text-xs font-bold text-white">Official Answers &amp; Outcomes ({data?.lane_a.length || 0})</div>
                  </div>
                  <Sparkles className="w-4 h-4 text-rose-400" />
                </div>

                {(data?.lane_a || []).map((a) => {
                  const isHi = activeChain?.has(a.id);
                  const isDim = Boolean(activeChain && !isHi);
                  return (
                    <div
                      key={a.id}
                      ref={(el) => {
                        nodeRefs.current[a.id] = el;
                      }}
                      onClick={() => setSelectedNodeId(selectedNodeId === a.id ? null : a.id)}
                      className={`p-3 rounded-xl border cursor-pointer transition bg-[#1c1519] ${
                        isHi
                          ? "border-rose-400 shadow-lg shadow-rose-500/15"
                          : "border-white/10 hover:border-rose-400/50"
                      } ${isDim ? "opacity-30" : ""}`}
                    >
                      <div className="flex items-center justify-between gap-1.5 mb-1.5">
                        <span
                          className={`text-[10px] font-mono uppercase font-bold px-1.5 py-0.5 rounded ${
                            a.outcome_tag === "approved"
                              ? "bg-emerald-500/20 text-emerald-300"
                              : a.outcome_tag === "refused"
                              ? "bg-red-500/20 text-red-300"
                              : "bg-blue-500/20 text-blue-300"
                          }`}
                        >
                          {a.outcome_tag}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">{a.usage_count}× pattern</span>
                      </div>
                      <div className="text-xs text-slate-200 leading-relaxed">{a.answer_text}</div>
                      {a.notes && <div className="mt-1.5 text-[10px] text-slate-400 italic">{a.notes}</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ── HIDDEN PATTERNS ANALYZER DRAWER ──────────────────────────────── */}
        {patterns && (
          <aside className="w-full max-w-[440px] border-l border-white/10 bg-[#11141c] flex flex-col shrink-0">
            <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                  <Search className="w-3.5 h-3.5" /> Hidden Patterns Analysis
                </div>
                <div className="text-[10px] text-slate-400">
                  Mined {patterns.dataset_summary.total_cases} cases · {patterns.dataset_summary.embassy_events} Embassy Qs ({patterns.provider_used})
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPatterns(null)}
                className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-400/25 space-y-1.5">
                <div className="text-[11px] font-bold text-amber-200">Executive Pattern Summary</div>
                <div className="text-slate-200 leading-relaxed">
                  <RichMarkdown content={patterns.executive_summary} />
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-[11px] uppercase tracking-wider font-bold text-emerald-300">
                  Client Traits Driving Approvals vs. Refusals
                </div>
                {patterns.trait_patterns.map((tp) => (
                  <div key={tp.trait} className="p-2.5 rounded-lg bg-white/[0.03] border border-white/10 flex items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold text-white">{tp.trait}</div>
                      <div className="text-[10px] text-slate-400">
                        {tp.approved} approved · {tp.refused} refused (n={tp.total})
                      </div>
                    </div>
                    <span
                      className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                        tp.signal === "positive_driver"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : tp.signal === "risk_driver"
                          ? "bg-red-500/20 text-red-300"
                          : "bg-white/10 text-slate-300"
                      }`}
                    >
                      {tp.approval_rate_pct}%
                    </span>
                  </div>
                ))}
              </div>

              {patterns.question_chains.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] uppercase tracking-wider font-bold text-blue-300">
                    Hidden Embassy Follow-Up Chains (Z1 → Z2)
                  </div>
                  {patterns.question_chains.map((ch, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg bg-white/[0.03] border border-white/10 text-slate-300">
                      <span className="font-mono text-blue-300 font-semibold">
                        {ch.from_theme.replace(/_/g, " ")} → {ch.to_theme.replace(/_/g, " ")}
                      </span>{" "}
                      <span className="text-slate-400">({ch.occurrences}×)</span>
                      <div className="text-[11px] text-slate-400 mt-0.5">{ch.insight}</div>
                    </div>
                  ))}
                </div>
              )}

              {patterns.co_occurring_risks.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] uppercase tracking-wider font-bold text-rose-300">
                    Co-Occurring Risk Flag Clusters
                  </div>
                  {patterns.co_occurring_risks.map((cr, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg bg-white/[0.03] border border-white/10 text-[11px] text-slate-300">
                      {cr.insight}
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-1.5">
                <div className="text-[11px] uppercase tracking-wider font-bold text-slate-300">
                  Anomalies &amp; Key Insights
                </div>
                {patterns.anomalies.map((an, idx) => (
                  <div key={idx} className="p-2.5 rounded-lg bg-white/[0.03] border border-white/10 text-[11px] text-slate-300">
                    {an}
                  </div>
                ))}
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
