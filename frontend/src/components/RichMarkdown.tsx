"use client";

import React from "react";

function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let k = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(
        <strong key={k++} className="font-semibold text-white">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code key={k++} className="px-1.5 py-0.5 rounded bg-white/10 text-blue-300 font-mono text-[12px]">
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith("*") && token.endsWith("*")) {
      parts.push(
        <em key={k++} className="italic text-slate-300">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith("[")) {
      const m = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (m) {
        parts.push(
          <a key={k++} href={m[2]} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
            {m[1]}
          </a>
        );
      } else {
        parts.push(token);
      }
    }
    last = regex.lastIndex;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts;
}

export function RichMarkdown({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="space-y-1.5 text-sm leading-relaxed text-slate-200">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-1" />;
        if (trimmed.startsWith("### ")) {
          return (
            <h4 key={i} className="text-sm font-bold text-white pt-1">
              {renderInline(trimmed.slice(4))}
            </h4>
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <h3 key={i} className="text-base font-bold text-white pt-1">
              {renderInline(trimmed.slice(3))}
            </h3>
          );
        }
        if (trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
          return (
            <div key={i} className="flex items-start gap-2 pl-1">
              <span className="text-blue-400 mt-0.5">•</span>
              <span className="flex-1">{renderInline(trimmed.slice(2))}</span>
            </div>
          );
        }
        if (trimmed.startsWith("> ")) {
          return (
            <div key={i} className="border-l-2 border-amber-400/60 pl-3 text-slate-300 italic text-xs py-0.5">
              {renderInline(trimmed.slice(2))}
            </div>
          );
        }
        return <p key={i}>{renderInline(line)}</p>;
      })}
    </div>
  );
}
