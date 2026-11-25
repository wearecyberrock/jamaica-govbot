"use client";

import { useEffect, useState } from "react";
import {
  Mail,
  Send,
  Clock,
  CheckCircle2,
  XCircle,
  Sparkles,
  RefreshCw,
  Copy,
  Check,
  Inbox,
  Terminal,
  Plus,
  Trash2,
  BellOff,
  Bell,
  Play,
  Settings,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface GmailConfig {
  gmail_address: string;
  app_password_configured: boolean;
  app_password_masked: string;
  smtp_ready: boolean;
  composio_gmail_ready: boolean;
  default_mode: "dual" | "auto" | "approval";
  sender_name: string;
  imap_enabled: boolean;
  hermes_cli_detected: boolean;
  hermes_cli_path: string;
}

interface AutomationRule {
  id: number;
  name: string;
  description: string;
  rule_type: string;
  enabled: boolean;
  send_mode: "auto" | "approval" | "dual";
  cron_expr: string;
  interval_minutes: number;
  cooldown_days: number;
  threshold_days: number;
  subject_template: string;
  body_template: string;
  use_ai_personalization: boolean;
  hermes_cron_synced: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

interface EmailLog {
  id: number;
  case_id: string | null;
  rule_id: number | null;
  direction: "outbound" | "inbound";
  status: string;
  to_email: string;
  from_email: string;
  subject: string;
  body_text: string;
  whatsapp_text: string;
  ai_reason: string;
  delivery_backend: string;
  error_detail: string;
  approved_by: string;
  sent_at: string | null;
  created_at: string | null;
}

interface EmailableClient {
  case_id: string;
  full_name: string;
  email: string;
  passport_expiry: string;
  embassy_interview_date: string;
  standing_score: number;
  email_muted: boolean;
}

interface GmailOverview {
  config: GmailConfig;
  stats: {
    queued_approval: number;
    sent_total: number;
    inbound_total: number;
    active_rules: number;
  };
  rules: AutomationRule[];
  messages: EmailLog[];
  emailable_clients: EmailableClient[];
}

export function GmailAutomationPanel({
  refreshNonce = 0,
  onOpenCase,
}: {
  refreshNonce?: number;
  onOpenCase?: (cid: string) => void;
}) {
  const [tab, setTab] = useState<"queue" | "rules" | "compose" | "connection">("queue");
  const [data, setData] = useState<GmailOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Inline edit state for queued messages
  const [editId, setEditId] = useState<number | null>(null);
  const [editSubj, setEditSubj] = useState("");
  const [editBody, setEditBody] = useState("");

  // Compose state
  const [compCaseId, setCompCaseId] = useState("");
  const [compTo, setCompTo] = useState("");
  const [compTopic, setCompTopic] = useState("");
  const [compSubj, setCompSubj] = useState("");
  const [compBody, setCompBody] = useState("");
  const [compWa, setCompWa] = useState("");

  // Connection state
  const [gmailAddr, setGmailAddr] = useState("");
  const [appPw, setAppPw] = useState("");
  const [senderName, setSenderName] = useState("Jahtaria Travel Services");
  const [defaultMode, setDefaultMode] = useState<"dual" | "auto" | "approval">("dual");
  const [imapEnabled, setImapEnabled] = useState(true);

  // New rule state
  const [showNewRule, setShowNewRule] = useState(false);
  const [nrName, setNrName] = useState("");
  const [nrType, setNrType] = useState("passport_expiry");
  const [nrMode, setNrMode] = useState<"auto" | "approval" | "dual">("dual");
  const [nrCron, setNrCron] = useState("0 9 * * *");
  const [nrThreshold, setNrThreshold] = useState(180);
  const [nrCooldown, setNrCooldown] = useState(14);
  const [nrSubj, setNrSubj] = useState("");
  const [nrBody, setNrBody] = useState("");

  // Hermes cron output
  const [hermesCmds, setHermesCmds] = useState<string[]>([]);

  const load = async () => {
    try {
      const res = await apiFetch<GmailOverview>("/api/gmail/overview");
      setData(res);
      setGmailAddr(res.config.gmail_address || "");
      setSenderName(res.config.sender_name || "Jahtaria Travel Services");
      setDefaultMode(res.config.default_mode || "dual");
      setImapEnabled(res.config.imap_enabled);
      if (!compCaseId && res.emailable_clients.length > 0) {
        setCompCaseId(res.emailable_clients[0].case_id);
        setCompTo(res.emailable_clients[0].email);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshNonce]);

  const copyWhatsApp = (text: string, id: number) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
  };

  const runAllRules = async () => {
    setBusy(true);
    setNotice("");
    try {
      const r = await apiFetch<{
        rules_evaluated: number;
        messages_sent: number;
        messages_queued: number;
        messages_dry_run: number;
      }>("/api/gmail/run-all", { method: "POST" });
      setNotice(
        `Cron scan finished: ${r.rules_evaluated} rule(s) checked • ${r.messages_sent} sent • ${r.messages_queued} queued for approval • ${r.messages_dry_run} dry-run preview(s).`
      );
      await load();
    } catch (e: unknown) {
      setNotice(e instanceof Error ? e.message : "Run failed");
    } finally {
      setBusy(false);
    }
  };

  const pollInbox = async () => {
    setBusy(true);
    setNotice("");
    try {
      const r = await apiFetch<{
        ok: boolean;
        checked: number;
        matched_messages: number;
        saved_attachments: number;
        error?: string;
      }>("/api/gmail/poll-inbox", { method: "POST" });
      setNotice(
        r.ok
          ? `Inbox synced: checked ${r.checked} email(s), matched ${r.matched_messages} client reply(s), auto-saved ${r.saved_attachments} attachment(s) into Client Vaults.`
          : r.error || "Inbox sync failed."
      );
      await load();
    } catch (e: unknown) {
      setNotice(e instanceof Error ? e.message : "Inbox poll failed");
    } finally {
      setBusy(false);
    }
  };

  if (!data) {
    return <div className="text-xs text-slate-400 p-4">Loading Gmail Automation &amp; Cron Hub…</div>;
  }

  const queued = data.messages.filter((m) => m.status === "queued_approval");
  const history = data.messages.filter((m) => m.status !== "queued_approval");

  return (
    <div className="space-y-3.5 text-xs">
      {/* Top Status Banner */}
      <div className="g-card p-3 border-[#e5b84b]/20 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-[#e5b84b]" />
            <div>
              <div className="font-semibold text-white">Gmail Automation &amp; Cron Hub</div>
              <div className="text-[11px] text-slate-400">
                {data.config.smtp_ready
                  ? `Connected via Gmail SMTP (${data.config.gmail_address})`
                  : data.config.composio_gmail_ready
                  ? "Connected via Composio Gmail"
                  : "Safe Dry-Run Preview Mode — connect Gmail App Password to send live"}
              </div>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-emerald-500/15 text-emerald-300 border border-emerald-400/25">
            Mode: {data.config.default_mode}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="p-2 rounded-lg bg-white/[0.04] border border-white/5">
            <div className="text-base font-bold text-amber-300">{data.stats.queued_approval}</div>
            <div className="text-[10px] text-slate-400">Waiting Approval</div>
          </div>
          <div className="p-2 rounded-lg bg-white/[0.04] border border-white/5">
            <div className="text-base font-bold text-emerald-300">{data.stats.sent_total}</div>
            <div className="text-[10px] text-slate-400">Sent Live</div>
          </div>
          <div className="p-2 rounded-lg bg-white/[0.04] border border-white/5">
            <div className="text-base font-bold text-blue-300">{data.stats.active_rules}</div>
            <div className="text-[10px] text-slate-400">Active Cron Rules</div>
          </div>
          <div className="p-2 rounded-lg bg-white/[0.04] border border-white/5">
            <div className="text-base font-bold text-purple-300">{data.stats.inbound_total}</div>
            <div className="text-[10px] text-slate-400">Inbox Synced</div>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 pt-1">
          <button
            onClick={runAllRules}
            disabled={busy}
            className="g-btn-primary px-2.5 py-1.5 text-[11px] inline-flex items-center gap-1"
          >
            <Play className="w-3 h-3" /> {busy ? "Running…" : "Run Cron Now"}
          </button>
          <button
            onClick={pollInbox}
            disabled={busy}
            className="g-btn-ghost px-2.5 py-1.5 text-[11px] inline-flex items-center gap-1"
          >
            <Inbox className="w-3 h-3" /> Poll Inbox → Vault
          </button>
          <button
            onClick={load}
            className="g-btn-ghost px-2 py-1.5 text-[11px] inline-flex items-center gap-1"
            title="Refresh"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {notice && (
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-400/25 text-[11px] text-emerald-200">
            {notice}
          </div>
        )}
      </div>

      {/* Sub-Tabs */}
      <div className="flex gap-1 bg-[#111318] p-1 rounded-xl border border-white/10">
        {(
          [
            ["queue", `Queue & Log (${queued.length})`],
            ["rules", `Cron Rules (${data.rules.length})`],
            ["compose", "AI Compose"],
            ["connection", "Connection"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`flex-1 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition ${
              tab === k ? "bg-emerald-500/20 text-emerald-200 border border-emerald-400/30" : "text-slate-400 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* TAB 1: APPROVAL QUEUE & SENT LOG */}
      {tab === "queue" && (
        <div className="space-y-3">
          {queued.length > 0 && (
            <div className="space-y-2">
              <div className="text-[11px] font-semibold text-amber-300 uppercase tracking-wider">
                Approval Queue ({queued.length})
              </div>
              {queued.map((m) => (
                <div key={m.id} className="g-card p-3 space-y-2 border-amber-400/30">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-semibold text-white truncate">{m.subject}</div>
                      <div className="text-[11px] text-slate-400">
                        To: <span className="text-slate-200">{m.to_email || "(no email)"}</span>
                        {m.case_id && (
                          <button
                            onClick={() => onOpenCase?.(m.case_id!)}
                            className="ml-2 text-emerald-400 hover:underline font-mono"
                          >
                            {m.case_id}
                          </button>
                        )}
                      </div>
                    </div>
                    <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-200 text-[10px] shrink-0">
                      Needs Approval
                    </span>
                  </div>
                  {m.ai_reason && (
                    <div className="text-[11px] text-blue-300 bg-blue-500/10 px-2 py-1 rounded">
                      Trigger: {m.ai_reason}
                    </div>
                  )}

                  {editId === m.id ? (
                    <div className="space-y-2">
                      <input
                        className="g-input text-xs"
                        value={editSubj}
                        onChange={(e) => setEditSubj(e.target.value)}
                      />
                      <textarea
                        className="g-input text-xs h-32"
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                      />
                    </div>
                  ) : (
                    <pre className="whitespace-pre-wrap font-sans text-[11px] text-slate-300 bg-black/30 p-2.5 rounded-lg max-h-40 overflow-y-auto">
                      {m.body_text}
                    </pre>
                  )}

                  <div className="flex flex-wrap gap-1.5">
                    <button
                      onClick={async () => {
                        setBusy(true);
                        await apiFetch(`/api/gmail/messages/${m.id}/approve`, {
                          method: "POST",
                          body: JSON.stringify(
                            editId === m.id ? { subject: editSubj, body_text: editBody } : {}
                          ),
                        });
                        setEditId(null);
                        setBusy(false);
                        load();
                      }}
                      className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold inline-flex items-center gap-1"
                    >
                      <CheckCircle2 className="w-3 h-3" /> Approve &amp; Send
                    </button>
                    {editId === m.id ? (
                      <button
                        onClick={() => setEditId(null)}
                        className="g-btn-ghost px-2 py-1 text-[11px]"
                      >
                        Cancel Edit
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setEditId(m.id);
                          setEditSubj(m.subject);
                          setEditBody(m.body_text);
                        }}
                        className="g-btn-ghost px-2 py-1 text-[11px]"
                      >
                        Edit Text
                      </button>
                    )}
                    <button
                      onClick={() => copyWhatsApp(m.whatsapp_text || m.body_text, m.id)}
                      className="g-btn-ghost px-2 py-1 text-[11px] inline-flex items-center gap-1 text-emerald-300"
                    >
                      {copiedId === m.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                      {copiedId === m.id ? "Copied WhatsApp!" : "Copy WhatsApp"}
                    </button>
                    <button
                      onClick={async () => {
                        await apiFetch(`/api/gmail/messages/${m.id}/reject`, { method: "POST" });
                        load();
                      }}
                      className="px-2 py-1 rounded-lg bg-red-500/15 hover:bg-red-500/25 text-red-300 text-[11px] inline-flex items-center gap-1"
                    >
                      <XCircle className="w-3 h-3" /> Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-2">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Message History &amp; Inbox ({history.length})
            </div>
            {history.length === 0 ? (
              <div className="g-card p-4 text-center text-slate-400">
                No emails sent or synced yet. Click <b>Run Cron Now</b> above to preview automatic triggers for your clients!
              </div>
            ) : (
              history.map((m) => (
                <div key={m.id} className="g-card p-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold text-slate-100 truncate">{m.subject}</div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase font-semibold shrink-0 ${
                        m.status === "sent"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : m.status === "received"
                          ? "bg-purple-500/20 text-purple-300"
                          : m.status === "dry_run"
                          ? "bg-blue-500/20 text-blue-300"
                          : m.status === "failed"
                          ? "bg-red-500/20 text-red-300"
                          : "bg-white/10 text-slate-400"
                      }`}
                    >
                      {m.direction === "inbound" ? "Inbox" : m.status.replace("_", " ")}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 flex items-center justify-between gap-2">
                    <span className="truncate">
                      {m.direction === "inbound" ? `From: ${m.from_email}` : `To: ${m.to_email}`}
                      {m.case_id ? ` • ${m.case_id}` : ""}
                    </span>
                    <button
                      onClick={() => copyWhatsApp(m.whatsapp_text || m.body_text, m.id)}
                      className="text-emerald-300 hover:underline inline-flex items-center gap-1 shrink-0"
                    >
                      {copiedId === m.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                      WhatsApp
                    </button>
                  </div>
                  {m.error_detail && (
                    <div className="text-[10px] text-amber-300 bg-amber-500/10 px-2 py-1 rounded">
                      {m.error_detail}
                    </div>
                  )}
                  <details className="text-[11px] text-slate-300">
                    <summary className="cursor-pointer text-slate-400 hover:text-slate-200">
                      View message body
                    </summary>
                    <pre className="mt-1.5 whitespace-pre-wrap font-sans bg-black/30 p-2 rounded">
                      {m.body_text}
                    </pre>
                  </details>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 2: AUTOMATION RULES & HERMES CRON */}
      {tab === "rules" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <button
              onClick={() => setShowNewRule(!showNewRule)}
              className="g-btn-primary px-2.5 py-1.5 text-[11px] inline-flex items-center gap-1"
            >
              <Plus className="w-3 h-3" /> New Automation Rule
            </button>
            <button
              onClick={async () => {
                setBusy(true);
                const r = await apiFetch<{ note: string; cli_commands: string[] }>(
                  "/api/gmail/sync-hermes-cron",
                  { method: "POST" }
                );
                setNotice(r.note);
                setHermesCmds(r.cli_commands || []);
                setBusy(false);
                load();
              }}
              className="g-btn-ghost px-2.5 py-1.5 text-[11px] inline-flex items-center gap-1 text-[#e5b84b]"
            >
              <Terminal className="w-3 h-3" /> Sync Hermes Cron
            </button>
          </div>

          {hermesCmds.length > 0 && (
            <div className="g-card p-3 space-y-1.5 border-[#e5b84b]/30">
              <div className="text-[11px] font-semibold text-[#e5b84b]">
                Hermes Cron CLI Commands (Built-in Desktop Scheduler Already Active)
              </div>
              <pre className="text-[10px] font-mono text-slate-300 bg-black/40 p-2 rounded overflow-x-auto">
                {hermesCmds.join("\n")}
              </pre>
            </div>
          )}

          {showNewRule && (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await apiFetch("/api/gmail/rules", {
                  method: "POST",
                  body: JSON.stringify({
                    name: nrName,
                    rule_type: nrType,
                    send_mode: nrMode,
                    cron_expr: nrCron,
                    threshold_days: Number(nrThreshold),
                    cooldown_days: Number(nrCooldown),
                    subject_template: nrSubj,
                    body_template: nrBody,
                    use_ai_personalization: true,
                  }),
                });
                setShowNewRule(false);
                setNrName("");
                setNrSubj("");
                setNrBody("");
                load();
              }}
              className="g-card p-3 space-y-2 border-emerald-400/30"
            >
              <div className="font-semibold text-white">Create Scheduled Email Rule</div>
              <input
                className="g-input text-xs"
                required
                placeholder="Rule Name (e.g. Passport 90-Day Final Warning)"
                value={nrName}
                onChange={(e) => setNrName(e.target.value)}
              />
              <div className="grid grid-cols-2 gap-2">
                <select className="g-input text-xs" value={nrType} onChange={(e) => setNrType(e.target.value)}>
                  <option value="passport_expiry">Passport Expiring Soon</option>
                  <option value="interview_countdown">Embassy Interview Countdown</option>
                  <option value="missing_docs_red_flags">Unresolved Red Flags</option>
                  <option value="questionnaire_nudge">Unanswered Questionnaire</option>
                  <option value="post_interview_checkin">Post-Interview Check-in</option>
                  <option value="ai_autonomous">AI Autonomous Scan</option>
                  <option value="custom">Custom Broadcast</option>
                </select>
                <select
                  className="g-input text-xs"
                  value={nrMode}
                  onChange={(e) => setNrMode(e.target.value as "auto" | "approval" | "dual")}
                >
                  <option value="auto">Auto-Send Immediately</option>
                  <option value="approval">Approval Queue First</option>
                  <option value="dual">Dual Mode (Smart)</option>
                </select>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-[10px] text-slate-400">Cron Expr</label>
                  <input className="g-input text-xs font-mono" value={nrCron} onChange={(e) => setNrCron(e.target.value)} />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Threshold Days</label>
                  <input
                    type="number"
                    className="g-input text-xs"
                    value={nrThreshold}
                    onChange={(e) => setNrThreshold(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Cooldown Days</label>
                  <input
                    type="number"
                    className="g-input text-xs"
                    value={nrCooldown}
                    onChange={(e) => setNrCooldown(Number(e.target.value))}
                  />
                </div>
              </div>
              <input
                className="g-input text-xs"
                placeholder="Subject template (optional — supports {full_name}, {case_id}, {passport_expiry})"
                value={nrSubj}
                onChange={(e) => setNrSubj(e.target.value)}
              />
              <textarea
                className="g-input text-xs h-20"
                placeholder="Body template (AI will personalize using live client profile)"
                value={nrBody}
                onChange={(e) => setNrBody(e.target.value)}
              />
              <button type="submit" className="g-btn-primary w-full py-1.5 text-xs">
                Save Rule
              </button>
            </form>
          )}

          {data.rules.map((r) => (
            <div key={r.id} className="g-card p-3 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-semibold text-white flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-[#e5b84b] shrink-0" />
                    <span className="truncate">{r.name}</span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">{r.description}</div>
                </div>
                <label className="inline-flex items-center gap-1.5 cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={r.enabled}
                    onChange={async (e) => {
                      await apiFetch(`/api/gmail/rules/${r.id}`, {
                        method: "PATCH",
                        body: JSON.stringify({ enabled: e.target.checked }),
                      });
                      load();
                    }}
                  />
                  <span className="text-[10px] text-slate-300">{r.enabled ? "ON" : "OFF"}</span>
                </label>
              </div>

              <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                <span className="px-2 py-0.5 rounded bg-white/5 font-mono">cron: {r.cron_expr}</span>
                <span className="px-2 py-0.5 rounded bg-white/5">window: {r.threshold_days}d</span>
                <span className="px-2 py-0.5 rounded bg-white/5">cooldown: {r.cooldown_days}d</span>
                <select
                  value={r.send_mode}
                  onChange={async (e) => {
                    await apiFetch(`/api/gmail/rules/${r.id}`, {
                      method: "PATCH",
                      body: JSON.stringify({ send_mode: e.target.value }),
                    });
                    load();
                  }}
                  className="bg-[#171a21] border border-white/10 rounded px-1.5 py-0.5 text-[10px] text-slate-200"
                >
                  <option value="auto">Auto-Send</option>
                  <option value="approval">Approval Queue</option>
                  <option value="dual">Dual Mode</option>
                </select>
              </div>

              <div className="flex items-center justify-between pt-1">
                <span className="text-[10px] text-slate-500">
                  {r.last_run_at ? `Last run: ${new Date(r.last_run_at).toLocaleString()}` : "Not run yet"}
                </span>
                <div className="flex gap-1.5">
                  <button
                    onClick={async () => {
                      setBusy(true);
                      const res = await apiFetch<{ messages_sent: number; messages_queued: number; messages_dry_run: number }>(
                        `/api/gmail/rules/${r.id}/run`,
                        { method: "POST" }
                      );
                      setNotice(`Rule '${r.name}': ${res.messages_sent} sent, ${res.messages_queued} queued, ${res.messages_dry_run} dry-run.`);
                      setBusy(false);
                      load();
                    }}
                    className="px-2 py-1 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 text-[10px] font-semibold inline-flex items-center gap-1"
                  >
                    <Play className="w-2.5 h-2.5" /> Run Now
                  </button>
                  <button
                    onClick={async () => {
                      await apiFetch(`/api/gmail/rules/${r.id}`, { method: "DELETE" });
                      load();
                    }}
                    className="p-1 text-red-400 hover:bg-red-500/15 rounded"
                    title="Delete rule"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* TAB 3: AI COMPOSE */}
      {tab === "compose" && (
        <div className="g-card p-3.5 space-y-2.5">
          <div className="font-semibold text-white">AI-Tailored Client Email &amp; WhatsApp Composer</div>
          <div className="grid grid-cols-2 gap-2">
            <select
              className="g-input text-xs"
              value={compCaseId}
              onChange={(e) => {
                const cid = e.target.value;
                setCompCaseId(cid);
                const found = data.emailable_clients.find((c) => c.case_id === cid);
                if (found) setCompTo(found.email);
              }}
            >
              <option value="">Select Client…</option>
              {data.emailable_clients.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} — {c.full_name}
                </option>
              ))}
            </select>
            <input
              className="g-input text-xs"
              placeholder="Recipient Email"
              value={compTo}
              onChange={(e) => setCompTo(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <input
              className="g-input text-xs flex-1"
              placeholder="Topic (e.g. Passport expires soon, bring 92% RGD copy, interview reminder)"
              value={compTopic}
              onChange={(e) => setCompTopic(e.target.value)}
            />
            <button
              type="button"
              disabled={busy || !compCaseId}
              onClick={async () => {
                setBusy(true);
                try {
                  const d = await apiFetch<{ subject: string; body_text: string; whatsapp_text: string; to_email: string }>(
                    "/api/gmail/ai-draft",
                    {
                      method: "POST",
                      body: JSON.stringify({ case_id: compCaseId, topic: compTopic }),
                    }
                  );
                  setCompSubj(d.subject);
                  setCompBody(d.body_text);
                  setCompWa(d.whatsapp_text);
                  if (d.to_email) setCompTo(d.to_email);
                } finally {
                  setBusy(false);
                }
              }}
              className="px-3 py-1.5 rounded-lg bg-[#e5b84b]/20 hover:bg-[#e5b84b]/30 text-[#f3d179] border border-[#e5b84b]/30 text-[11px] font-semibold inline-flex items-center gap-1 shrink-0"
            >
              <Sparkles className="w-3.5 h-3.5" /> AI Draft
            </button>
          </div>
          <input
            className="g-input text-xs"
            placeholder="Email Subject"
            value={compSubj}
            onChange={(e) => setCompSubj(e.target.value)}
          />
          <textarea
            className="g-input text-xs h-36"
            placeholder="Message body…"
            value={compBody}
            onChange={(e) => setCompBody(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <button
              disabled={busy || !compSubj || !compBody}
              onClick={async () => {
                setBusy(true);
                const res = await apiFetch<EmailLog>("/api/gmail/send", {
                  method: "POST",
                  body: JSON.stringify({
                    case_id: compCaseId || null,
                    to_email: compTo,
                    subject: compSubj,
                    body_text: compBody,
                    topic: compTopic,
                    send_immediately: true,
                  }),
                });
                setNotice(`Message ${res.status === "sent" ? "sent live!" : `saved as ${res.status}.`}`);
                setBusy(false);
                setTab("queue");
                load();
              }}
              className="g-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1"
            >
              <Send className="w-3.5 h-3.5" /> Send Now
            </button>
            <button
              disabled={busy || !compSubj || !compBody}
              onClick={async () => {
                setBusy(true);
                await apiFetch("/api/gmail/send", {
                  method: "POST",
                  body: JSON.stringify({
                    case_id: compCaseId || null,
                    to_email: compTo,
                    subject: compSubj,
                    body_text: compBody,
                    topic: compTopic,
                    send_immediately: false,
                  }),
                });
                setNotice("Saved to Approval Queue.");
                setBusy(false);
                setTab("queue");
                load();
              }}
              className="g-btn-ghost px-3 py-1.5 text-xs"
            >
              Save to Queue
            </button>
            {compBody && (
              <button
                onClick={() => copyWhatsApp(compWa || `*${compSubj}*\n\n${compBody}`, -1)}
                className="g-btn-ghost px-3 py-1.5 text-xs text-emerald-300 inline-flex items-center gap-1"
              >
                {copiedId === -1 ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedId === -1 ? "Copied WhatsApp!" : "Copy for WhatsApp"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: CONNECTION, MODE & CLIENT MUTE */}
      {tab === "connection" && (
        <div className="space-y-3">
          <div className="g-card p-3.5 space-y-2.5">
            <div className="font-semibold text-white flex items-center gap-1.5">
              <Settings className="w-3.5 h-3.5 text-[#e5b84b]" /> Gmail SMTP / IMAP Setup (Encrypted Local Storage)
            </div>
            <p className="text-[11px] text-slate-400">
              Use a free 16-character <b>Google App Password</b> (Google Account → Security → 2-Step Verification → App passwords) to enable instant real sending &amp; automatic Inbox attachment syncing to Client Vaults.
            </p>
            <input
              className="g-input text-xs"
              placeholder="agency@gmail.com"
              value={gmailAddr}
              onChange={(e) => setGmailAddr(e.target.value)}
            />
            <input
              className="g-input text-xs"
              type="password"
              placeholder={
                data.config.app_password_configured
                  ? `Saved (${data.config.app_password_masked}) — enter new to replace`
                  : "16-char Google App Password (xxxx xxxx xxxx xxxx)"
              }
              value={appPw}
              onChange={(e) => setAppPw(e.target.value)}
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                className="g-input text-xs"
                placeholder="Sender Display Name"
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
              />
              <select
                className="g-input text-xs"
                value={defaultMode}
                onChange={(e) => setDefaultMode(e.target.value as "dual" | "auto" | "approval")}
              >
                <option value="dual">Dual Mode (Recommended)</option>
                <option value="auto">Full Autopilot</option>
                <option value="approval">Approval Queue Only</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-[11px] text-slate-300">
              <input type="checkbox" checked={imapEnabled} onChange={(e) => setImapEnabled(e.target.checked)} />
              Auto-poll Gmail Inbox every 15 min &amp; save client attachments directly to Vault
            </label>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  setBusy(true);
                  await apiFetch("/api/gmail/config", {
                    method: "PUT",
                    body: JSON.stringify({
                      gmail_address: gmailAddr,
                      gmail_app_password: appPw || undefined,
                      sender_name: senderName,
                      default_mode: defaultMode,
                      imap_enabled: imapEnabled,
                    }),
                  });
                  setAppPw("");
                  setNotice("Gmail settings saved & encrypted.");
                  setBusy(false);
                  load();
                }}
                className="g-btn-primary px-3 py-1.5 text-xs"
              >
                Save Gmail Config
              </button>
              <button
                onClick={async () => {
                  setBusy(true);
                  const r = await apiFetch<{ ok: boolean; smtp_ok: boolean; imap_ok: boolean; error?: string }>(
                    "/api/gmail/test-connection",
                    { method: "POST" }
                  );
                  setNotice(
                    r.ok
                      ? `Gmail Verified! SMTP: ${r.smtp_ok ? "OK" : "Fail"} | IMAP Inbox: ${r.imap_ok ? "OK" : "Fail"}`
                      : `Connection failed: ${r.error}`
                  );
                  setBusy(false);
                }}
                className="g-btn-ghost px-3 py-1.5 text-xs"
              >
                Test SMTP &amp; IMAP
              </button>
            </div>
          </div>

          <div className="g-card p-3.5 space-y-2">
            <div className="font-semibold text-white">Per-Client Auto-Email Mute Controls</div>
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {data.emailable_clients.map((c) => (
                <div key={c.case_id} className="flex items-center justify-between gap-2 py-1 border-b border-white/5">
                  <div className="min-w-0">
                    <div className="text-slate-200 font-medium truncate">
                      {c.case_id} — {c.full_name}
                    </div>
                    <div className="text-[10px] text-slate-400 truncate">{c.email}</div>
                  </div>
                  <button
                    onClick={async () => {
                      await apiFetch(`/api/gmail/clients/${c.case_id}/mute?muted=${!c.email_muted}`, {
                        method: "POST",
                      });
                      load();
                    }}
                    className={`px-2 py-1 rounded text-[10px] inline-flex items-center gap-1 shrink-0 ${
                      c.email_muted
                        ? "bg-red-500/20 text-red-300"
                        : "bg-emerald-500/15 text-emerald-300"
                    }`}
                  >
                    {c.email_muted ? <BellOff className="w-3 h-3" /> : <Bell className="w-3 h-3" />}
                    {c.email_muted ? "Paused" : "Active"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
