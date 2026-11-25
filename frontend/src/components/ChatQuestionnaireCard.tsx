"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Lightbulb,
  List,
  Plus,
  Sparkles,
  Check,
  Search,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { ChatQuestionnairePayload } from "@/lib/types";

interface ChatQuestionnaireCardProps {
  initialData: ChatQuestionnairePayload;
  isStaffOrCeo: boolean;
  onSync?: (updated: ChatQuestionnairePayload) => void;
}

const LETTERS = ["A", "B", "C", "D", "E", "F"];

export function ChatQuestionnaireCard({
  initialData,
  isStaffOrCeo,
  onSync,
}: ChatQuestionnaireCardProps) {
  const [data, setData] = useState<ChatQuestionnairePayload>(initialData);
  const [index, setIndex] = useState<number>(() => {
    const firstOpen = initialData.items.findIndex((i) => !i.client_response?.trim() && !i.resolved);
    return firstOpen >= 0 ? firstOpen : 0;
  });
  const [showTip, setShowTip] = useState(false);
  const [showJumpList, setShowJumpList] = useState(false);
  const [jumpQuery, setJumpQuery] = useState("");
  const [draftAnswer, setDraftAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [genCount, setGenCount] = useState("10");
  const [genFocus, setGenFocus] = useState("");
  const [showGenBar, setShowGenBar] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  useEffect(() => {
    setData(initialData);
  }, [initialData]);

  const items = data.items || [];
  const safeIndex = Math.min(Math.max(0, index), Math.max(0, items.length - 1));
  const current = items[safeIndex] || null;

  useEffect(() => {
    if (current) {
      setDraftAnswer(current.client_response || "");
      setShowTip(false);
    }
  }, [safeIndex, current?.flag_id]);

  const flash = (msg: string) => {
    setStatusMsg(msg);
    setTimeout(() => setStatusMsg(""), 3000);
  };

  const refreshFromServer = async () => {
    const fresh = await apiFetch<ChatQuestionnairePayload>(`/api/clients/${data.case_id}/questionnaire`);
    setData(fresh);
    onSync?.(fresh);
    return fresh;
  };

  const saveAnswer = async (valueOverride?: string, autoAdvance = true) => {
    if (!current) return;
    const answerText = (valueOverride ?? draftAnswer).trim();
    if (!answerText) return;
    setSaving(true);
    try {
      await apiFetch(`/api/clients/${data.case_id}/questionnaire`, {
        method: "POST",
        body: JSON.stringify({
          flag_id: current.flag_id,
          client_response: answerText,
          mark_resolved: isStaffOrCeo,
        }),
      });
      const fresh = await refreshFromServer();
      flash("Saved & synced with side panel");
      if (autoAdvance && safeIndex < fresh.items.length - 1) {
        setIndex(safeIndex + 1);
      }
    } finally {
      setSaving(false);
    }
  };

  const generateMore = async (requestedCount?: number) => {
    const n = Math.max(1, Math.min(requestedCount ?? (parseInt(genCount, 10) || 10), 1000));
    setGenerating(true);
    try {
      const res = await apiFetch<{ questionnaire: ChatQuestionnairePayload; questions_added: unknown[] }>(
        `/api/clients/${data.case_id}/questionnaire/generate`,
        {
          method: "POST",
          body: JSON.stringify({ count: n, focus: genFocus.trim() }),
        }
      );
      const prevLen = items.length;
      setData(res.questionnaire);
      onSync?.(res.questionnaire);
      setIndex(Math.min(prevLen, Math.max(0, res.questionnaire.items.length - 1)));
      setShowGenBar(false);
      setGenFocus("");
      flash(`Added ${res.questions_added.length} new question(s)!`);
    } finally {
      setGenerating(false);
    }
  };

  const answeredCount = items.filter((i) => (i.client_response || "").trim() || i.resolved).length;
  const pct = items.length > 0 ? Math.round((answeredCount / items.length) * 100) : 0;

  const filteredJump = jumpQuery.trim()
    ? items
        .map((it, idx) => ({ it, idx }))
        .filter(({ it }) => `${it.title} ${it.question}`.toLowerCase().includes(jumpQuery.trim().toLowerCase()))
    : items.map((it, idx) => ({ it, idx }));

  return (
    <div className="mt-3 rounded-2xl bg-[#141720] border border-white/12 shadow-xl overflow-hidden text-slate-200">
      {/* Compact Header */}
      <div className="px-4 py-3 border-b border-white/10 flex flex-wrap items-center justify-between gap-2 bg-white/[0.02]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-300 font-mono text-[11px] font-semibold">
            {data.case_id}
          </span>
          <span className="text-xs font-semibold text-white truncate">Interactive Questionnaire</span>
          <span className="text-[11px] text-slate-400">
            {answeredCount}/{items.length} answered
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setShowJumpList(!showJumpList)}
            className={`px-2 py-1 rounded-lg text-[11px] inline-flex items-center gap-1 transition ${
              showJumpList
                ? "bg-blue-500/20 text-blue-200 border border-blue-400/30"
                : "bg-white/5 hover:bg-white/10 text-slate-300"
            }`}
            title="Browse or jump to any question"
          >
            <List className="w-3 h-3" /> {showJumpList ? "Card View" : `All (${items.length})`}
          </button>
          <button
            type="button"
            onClick={() => setShowGenBar(!showGenBar)}
            className={`px-2 py-1 rounded-lg text-[11px] inline-flex items-center gap-1 transition ${
              showGenBar
                ? "bg-emerald-500/20 text-emerald-200 border border-emerald-400/30"
                : "bg-white/5 hover:bg-white/10 text-emerald-300"
            }`}
            title="Generate more questions (unlimited)"
          >
            <Plus className="w-3 h-3" /> Add More
          </button>
        </div>
      </div>

      {/* Progress Hairline */}
      <div className="h-1 w-full bg-white/5">
        <div className="h-full bg-gradient-to-r from-blue-500 to-emerald-400 transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>

      {/* Collapsible Unlimited Generator Drawer */}
      {showGenBar && (
        <div className="px-4 py-3 border-b border-white/10 bg-black/25 space-y-2">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="text-slate-400 mr-1">Quick add:</span>
            {[5, 15, 50, 100, 250].map((n) => (
              <button
                key={n}
                type="button"
                disabled={generating}
                onClick={() => generateMore(n)}
                className="px-2 py-1 rounded-lg bg-white/5 hover:bg-blue-500/25 hover:text-blue-200 border border-white/10 text-slate-200 transition disabled:opacity-40"
              >
                +{n}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="number"
              min={1}
              max={1000}
              value={genCount}
              onChange={(e) => setGenCount(e.target.value)}
              className="g-input w-20 text-xs py-1.5 text-center"
              placeholder="Qty"
              title="Any number up to 1000 per batch (repeat infinitely)"
            />
            <input
              type="text"
              value={genFocus}
              onChange={(e) => setGenFocus(e.target.value)}
              className="g-input flex-1 min-w-[140px] text-xs py-1.5"
              placeholder="Optional topic focus (e.g. business ties, 214b, student F1)..."
            />
            <button
              type="button"
              disabled={generating}
              onClick={() => generateMore()}
              className="g-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1 shrink-0 disabled:opacity-40"
            >
              <Sparkles className="w-3.5 h-3.5" /> {generating ? "Generating…" : "Generate"}
            </button>
          </div>
        </div>
      )}

      {/* Jump List View (keeps even 500 questions clean & fast to navigate) */}
      {showJumpList ? (
        <div className="p-3 space-y-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              value={jumpQuery}
              onChange={(e) => setJumpQuery(e.target.value)}
              placeholder={`Search ${items.length} questions...`}
              className="g-input text-xs py-1.5 pl-8 w-full"
            />
          </div>
          <div className="max-h-64 overflow-y-auto space-y-1 pr-1">
            {filteredJump.slice(0, 120).map(({ it, idx }) => {
              const done = Boolean((it.client_response || "").trim() || it.resolved);
              return (
                <button
                  key={it.flag_id}
                  type="button"
                  onClick={() => {
                    setIndex(idx);
                    setShowJumpList(false);
                  }}
                  className={`w-full text-left px-2.5 py-2 rounded-xl text-xs flex items-center justify-between gap-2 transition ${
                    idx === safeIndex
                      ? "bg-blue-500/20 border border-blue-400/30 text-white"
                      : "bg-white/[0.02] hover:bg-white/[0.06] text-slate-300 border border-transparent"
                  }`}
                >
                  <div className="min-w-0 flex items-center gap-2">
                    <span className="font-mono text-[10px] text-slate-500 w-7 shrink-0">#{idx + 1}</span>
                    <span className="truncate">{it.question}</span>
                  </div>
                  {done && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                </button>
              );
            })}
            {filteredJump.length > 120 && (
              <div className="text-[11px] text-slate-500 text-center py-1">
                Showing first 120 matches — refine search or type a question # below.
              </div>
            )}
          </div>
        </div>
      ) : current ? (
        /* Clean Single-Question Interactive Step */
        <div className="p-4 space-y-3.5">
          {/* Question Meta + Tips Icon */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-mono text-slate-400">
                Q{safeIndex + 1} / {items.length}
              </span>
              <span className="px-2 py-0.5 rounded-full bg-white/[0.06] text-[11px] text-slate-300 font-medium">
                {current.title}
              </span>
              {(current.client_response || current.resolved) && (
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-[10px] font-semibold inline-flex items-center gap-1">
                  <Check className="w-2.5 h-2.5" /> Answered
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={() => setShowTip(!showTip)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium inline-flex items-center gap-1 shrink-0 transition ${
                showTip
                  ? "bg-amber-500/25 text-amber-200 border border-amber-400/40"
                  : "bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-400/20"
              }`}
              title="Show explanation & consular tip"
            >
              <Lightbulb className="w-3.5 h-3.5" /> Tips
            </button>
          </div>

          {/* Question Prompt */}
          <div className="text-sm font-medium text-white leading-relaxed">{current.question}</div>

          {/* Collapsible Tips & Explanation */}
          {showTip && (
            <div className="rounded-xl bg-amber-500/[0.08] border border-amber-400/25 p-3 space-y-1.5 text-xs">
              <div>
                <span className="font-semibold text-amber-300">Why this matters: </span>
                <span className="text-slate-200">{current.explanation}</span>
              </div>
              <div>
                <span className="font-semibold text-emerald-300">Consular Tip: </span>
                <span className="text-slate-200">{current.tip}</span>
              </div>
            </div>
          )}

          {/* Multiple Choice Options */}
          {current.options && current.options.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {current.options.map((opt, oi) => {
                const selected = draftAnswer.trim() === opt.trim();
                return (
                  <button
                    key={oi}
                    type="button"
                    onClick={() => setDraftAnswer(opt)}
                    className={`text-left px-3 py-2 rounded-xl border text-xs flex items-start gap-2 transition ${
                      selected
                        ? "bg-blue-500/20 border-blue-400/60 text-white"
                        : "bg-white/[0.03] hover:bg-white/[0.07] border-white/10 text-slate-300"
                    }`}
                  >
                    <span
                      className={`w-5 h-5 rounded-md text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5 ${
                        selected ? "bg-blue-500 text-white" : "bg-white/10 text-slate-400"
                      }`}
                    >
                      {LETTERS[oi] || oi + 1}
                    </span>
                    <span className="leading-snug">{opt}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Custom Answer Input + Save */}
          <div className="flex items-center gap-2 pt-1">
            <input
              type="text"
              value={draftAnswer}
              onChange={(e) => setDraftAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  saveAnswer();
                }
              }}
              placeholder="Type answer or pick above…"
              className="g-input flex-1 text-xs py-2"
            />
            <button
              type="button"
              disabled={saving || !draftAnswer.trim()}
              onClick={() => saveAnswer()}
              className="g-btn-primary px-3.5 py-2 text-xs font-semibold shrink-0 disabled:opacity-40"
            >
              {saving ? "Saving…" : safeIndex < items.length - 1 ? "Save & Next" : "Save"}
            </button>
          </div>
        </div>
      ) : (
        <div className="p-5 text-center space-y-2">
          <div className="text-xs text-slate-400">No questions yet for {data.case_id}.</div>
          <button
            type="button"
            disabled={generating}
            onClick={() => generateMore(5)}
            className="g-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1"
          >
            <Sparkles className="w-3.5 h-3.5" /> Generate 5 Questions
          </button>
        </div>
      )}

      {/* Clean Footer Navigation */}
      <div className="px-4 py-2.5 border-t border-white/10 bg-white/[0.02] flex items-center justify-between gap-2 text-xs">
        <button
          type="button"
          disabled={safeIndex <= 0}
          onClick={() => setIndex(Math.max(0, safeIndex - 1))}
          className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 disabled:opacity-30 inline-flex items-center gap-1"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Prev
        </button>

        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          {statusMsg ? (
            <span className="text-emerald-300 font-medium">{statusMsg}</span>
          ) : (
            <label className="inline-flex items-center gap-1">
              <span>Go to #</span>
              <input
                type="number"
                min={1}
                max={Math.max(1, items.length)}
                value={items.length ? safeIndex + 1 : 0}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!Number.isNaN(v) && v >= 1 && v <= items.length) {
                    setIndex(v - 1);
                  }
                }}
                className="w-12 bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-center text-slate-200 outline-none"
              />
              <span>of {items.length}</span>
            </label>
          )}
        </div>

        <button
          type="button"
          disabled={safeIndex >= items.length - 1}
          onClick={() => setIndex(Math.min(items.length - 1, safeIndex + 1))}
          className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 disabled:opacity-30 inline-flex items-center gap-1"
        >
          Next <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
