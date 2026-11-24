"use client";

import { AlertTriangle, CheckCircle2, ShieldAlert, ExternalLink } from "lucide-react";
import type { RiskFlag } from "@/lib/types";

interface GoodStandingBarProps {
  score: number;
  riskLevel: string;
  flags: RiskFlag[];
  compact?: boolean;
}

export function GoodStandingBar({ score, riskLevel, flags, compact = false }: GoodStandingBarProps) {
  const redCount = flags.filter((f) => f.severity === "red" && !f.resolved).length;
  const amberCount = flags.filter((f) => f.severity === "amber" && !f.resolved).length;
  const greenCount = flags.filter((f) => f.severity === "green" || f.resolved).length;

  const barGradient =
    score >= 80
      ? "from-emerald-600 to-green-500"
      : score >= 60
      ? "from-amber-500 to-yellow-400"
      : "from-red-600 to-rose-500";

  const badgeStyle =
    score >= 80
      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
      : score >= 60
      ? "bg-amber-100 text-amber-900 border-amber-200"
      : "bg-red-100 text-red-800 border-red-200";

  return (
    <div className="ja-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div>
          <h3 className="text-sm font-extrabold uppercase tracking-wider text-ja-green">
            Good Standing &amp; Denial-Risk Readiness Bar
          </h3>
          <p className="text-xs text-slate-500">
            Mapped against U.S. Embassy Kingston rules (DS-160 AA barcode, 6-mo PICA passport, gross/net JMD &amp; RGD 92% copy rules)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-xs font-extrabold border uppercase ${badgeStyle}`}>
            {riskLevel} risk
          </span>
          <span className="text-2xl font-black text-slate-900">{score}%</span>
        </div>
      </div>

      <div className="w-full h-4 rounded-full bg-slate-200 overflow-hidden shadow-inner">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${barGradient} transition-all duration-500`}
          style={{ width: `${Math.max(6, Math.min(100, score))}%` }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-4 mt-3 text-xs font-bold">
        <span className="inline-flex items-center gap-1.5 text-ja-red">
          <ShieldAlert className="w-4 h-4" /> {redCount} Red Blocker{redCount === 1 ? "" : "s"}
        </span>
        <span className="inline-flex items-center gap-1.5 text-amber-600">
          <AlertTriangle className="w-4 h-4" /> {amberCount} Amber Warning{amberCount === 1 ? "" : "s"}
        </span>
        <span className="inline-flex items-center gap-1.5 text-emerald-700">
          <CheckCircle2 className="w-4 h-4" /> {greenCount} Verified / Clear
        </span>
      </div>

      {!compact && flags.length > 0 && (
        <div className="mt-4 space-y-2.5">
          {flags.map((f) => {
            const box =
              f.severity === "red"
                ? "border-red-200 bg-red-50/70"
                : f.severity === "amber"
                ? "border-amber-200 bg-amber-50/70"
                : "border-emerald-200 bg-emerald-50/60";
            return (
              <div key={f.id} className={`rounded-xl border p-3.5 ${box}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="font-bold text-sm text-slate-900 flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase text-white ${
                        f.severity === "red"
                          ? "bg-ja-red"
                          : f.severity === "amber"
                          ? "bg-amber-600"
                          : "bg-emerald-700"
                      }`}
                    >
                      {f.severity}
                    </span>
                    {f.title}
                  </div>
                  {f.source_url && (
                    <a
                      href={f.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] font-semibold text-ja-navy hover:underline inline-flex items-center gap-1 shrink-0"
                    >
                      {f.source_citation || "Official Source"} <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
                <p className="text-xs text-slate-700 mt-1.5 leading-relaxed">{f.detail}</p>
                {f.suggested_fix && (
                  <p className="text-xs text-slate-800 mt-1.5">
                    <span className="font-bold text-ja-green">Recommended Action:</span> {f.suggested_fix}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
