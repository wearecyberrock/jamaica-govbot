"use client";

import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ShieldCheck,
  FileText,
  MessageSquare,
  Clock,
  Bot,
  Lock,
  CheckCircle2,
  XCircle,
  Download,
  RefreshCw,
  BookOpen,
  Sparkles,
  Send,
  Image as ImageIcon,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { ClientDetail, OfficialDocItem } from "@/lib/types";
import { GoodStandingBar } from "./GoodStandingBar";

const STAGES = [
  { id: "new_intake", label: "New Intake" },
  { id: "data_synced", label: "Data Synced" },
  { id: "risk_audit", label: "Rule & Risk Audit" },
  { id: "questionnaire", label: "Questionnaire" },
  { id: "review_approval", label: "Review & Approval" },
  { id: "docs_ready", label: "Docs Ready" },
  { id: "embassy_scheduled", label: "Embassy Scheduled" },
  { id: "completed", label: "Completed" },
];

export function ClientWorkspace({
  caseId,
  onBack,
  onUpdated,
}: {
  caseId: string;
  onBack: () => void;
  onUpdated?: () => void;
}) {
  const [tab, setTab] = useState<"overview" | "intake" | "interview" | "blueprints" | "journal" | "agent">("overview");
  const [client, setClient] = useState<ClientDetail | null>(null);
  const [blueprints, setBlueprints] = useState<OfficialDocItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  // Editable intake state
  const [form, setForm] = useState<Record<string, string | number | boolean>>({});
  const [qAnswers, setQAnswers] = useState<Record<number, string>>({});

  // Interview mock & outcome state
  const [mockQ, setMockQ] = useState<{ theme: string; question_text: string } | null>(null);
  const [mockAns, setMockAns] = useState("");
  const [mockFeedback, setMockFeedback] = useState("");
  const [outcomeVal, setOutcomeVal] = useState("approved");
  const [refusalStatute, setRefusalStatute] = useState("");

  // Blueprint preview state
  const [previewAsset, setPreviewAsset] = useState<{ id: number; title: string; mime_type: string } | null>(null);
  const [selectedBpKey, setSelectedBpKey] = useState("");

  // Journal note state
  const [journalNote, setJournalNote] = useState("");

  // Hermes Agent state
  const [agentInput, setAgentInput] = useState("");
  const [agentHistory, setAgentHistory] = useState<
    Array<{ sender: string; content: string; trace?: Array<{ step: number; tool: string; status: string; detail: string }>; provider_used?: string }>
  >([]);

  const loadClient = async () => {
    const data = await apiFetch<ClientDetail>(`/api/clients/${caseId}`);
    setClient(data);
    setForm({
      full_name: data.full_name || "",
      email: data.email || "",
      phone: data.phone || "",
      parish: data.parish || "",
      visa_class: data.visa_class || "B1/B2",
      passport_number: data.passport_number || "",
      passport_expiry: data.passport_expiry || "",
      dob: data.dob || "",
      ds160_confirmation_id: data.ds160_confirmation_id || "",
      ais_appointment_barcode: data.ais_appointment_barcode || "",
      intended_travel_date: data.intended_travel_date || "",
      intended_return_date: data.intended_return_date || "",
      purpose_of_trip: data.purpose_of_trip || "",
      us_destination: data.us_destination || "",
      us_host_contact: data.us_host_contact || "",
      occupation: data.occupation || "",
      employer_name: data.employer_name || "",
      monthly_gross_jmd: data.monthly_gross_jmd ?? "",
      monthly_net_jmd: data.monthly_net_jmd ?? "",
      marital_status: data.marital_status || "",
      children_count: data.children_count || 0,
      prior_us_refusals: data.prior_us_refusals || 0,
      has_us_relatives: data.has_us_relatives,
      us_relatives_details: data.us_relatives_details || "",
      embassy_interview_date: data.embassy_interview_date || "",
      open_verification_items: data.open_verification_items || "",
    });
    const ansMap: Record<number, string> = {};
    data.risk_flags.forEach((f) => {
      ansMap[f.id] = f.client_response || "";
    });
    setQAnswers(ansMap);
    if (!mockQ && data.predictions.length > 0) {
      setMockQ({ theme: data.predictions[0].theme_id, question_text: data.predictions[0].question_text });
    }
  };

  useEffect(() => {
    loadClient().catch(() => {});
    apiFetch<OfficialDocItem[]>("/api/documents/official")
      .then((list) => {
        setBlueprints(list);
        const docx = list.find((d) => d.file_format === ".docx") || list[0];
        if (docx) setSelectedBpKey(docx.doc_key);
      })
      .catch(() => {});
    apiFetch<Array<{ sender: string; content: string; trace: Array<{ step: number; tool: string; status: string; detail: string }>; provider_used: string }>>(
      `/api/agent/history?case_id=${caseId}&mode=staff`
    )
      .then(setAgentHistory)
      .catch(() => {});
  }, [caseId]);

  const notify = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 5000);
  };

  const changeStage = async (stage: string) => {
    await apiFetch(`/api/clients/${caseId}`, { method: "PATCH", body: JSON.stringify({ pipeline_stage: stage }) });
    await loadClient();
    onUpdated?.();
    notify(`Pipeline stage updated to '${stage.replace("_", " ")}'.`);
  };

  const saveIntake = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload: Record<string, unknown> = { ...form };
      payload.monthly_gross_jmd = form.monthly_gross_jmd === "" ? null : Number(form.monthly_gross_jmd);
      payload.monthly_net_jmd = form.monthly_net_jmd === "" ? null : Number(form.monthly_net_jmd);
      payload.children_count = Number(form.children_count || 0);
      payload.prior_us_refusals = Number(form.prior_us_refusals || 0);
      await apiFetch(`/api/clients/${caseId}`, { method: "PATCH", body: JSON.stringify(payload) });
      await loadClient();
      onUpdated?.();
      notify("Client profile saved, encrypted PII updated, and Good Standing re-evaluated.");
    } finally {
      setBusy(false);
    }
  };

  const saveQuestionAnswer = async (flagId: number, resolve: boolean) => {
    await apiFetch(`/api/clients/${caseId}/questionnaire`, {
      method: "POST",
      body: JSON.stringify({
        flag_id: flagId,
        client_response: qAnswers[flagId] || "Verified by staff",
        mark_resolved: resolve,
      }),
    });
    await loadClient();
    onUpdated?.();
    notify(resolve ? "Flag resolved & Good Standing score updated!" : "Response recorded.");
  };

  const runAuditNow = async () => {
    setBusy(true);
    try {
      await apiFetch(`/api/clients/${caseId}/audit`, { method: "POST" });
      await loadClient();
      onUpdated?.();
      notify("Re-ran Kingston Embassy Good Standing audit.");
    } finally {
      setBusy(false);
    }
  };

  const syncObsidian = async () => {
    const res = await apiFetch<{ path: string }>(`/api/obsidian/sync-client/${caseId}`, { method: "POST" });
    notify(`Synced dossier to Obsidian Vault: ${res.path}`);
  };

  const freezePredictions = async () => {
    await apiFetch(`/api/clients/${caseId}/predictions/freeze`, { method: "POST" });
    await loadClient();
    notify("Pre-interview predictions FROZEN with author + UTC timestamp.");
  };

  const submitMockPractice = async () => {
    if (!mockQ || !mockAns.trim()) return;
    setBusy(true);
    try {
      const res = await apiFetch<{ feedback: string }>(`/api/clients/${caseId}/mock-practice`, {
        method: "POST",
        body: JSON.stringify({ theme: mockQ.theme, question_text: mockQ.question_text, client_answer: mockAns }),
      });
      setMockFeedback(res.feedback);
      setMockAns("");
      await loadClient();
    } finally {
      setBusy(false);
    }
  };

  const submitOutcome = async () => {
    await apiFetch(`/api/clients/${caseId}/embassy-outcome`, {
      method: "POST",
      body: JSON.stringify({ outcome: outcomeVal, refusal_statute: refusalStatute, outcome_evidence: "staff_recorded" }),
    });
    await loadClient();
    onUpdated?.();
    notify(`Recorded embassy outcome: ${outcomeVal.toUpperCase()}`);
  };

  const generateAsset = async (assetType: string, bpKey?: string) => {
    setBusy(true);
    try {
      const res = await apiFetch<{ id: number; title: string; mime_type: string }>(`/api/clients/${caseId}/assets/generate`, {
        method: "POST",
        body: JSON.stringify({ asset_type: assetType, blueprint_doc_key: bpKey }),
      });
      await loadClient();
      setPreviewAsset(res);
      notify(`Drafted '${res.title}' — review & click Approve to unlock for Client Portal.`);
    } finally {
      setBusy(false);
    }
  };

  const decideAsset = async (assetId: number, decision: "approved" | "rejected") => {
    await apiFetch(`/api/assets/${assetId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision, visible_to_client: decision === "approved" }),
    });
    await loadClient();
    onUpdated?.();
    notify(decision === "approved" ? "Asset APPROVED & shared to Client Portal!" : "Asset marked rejected.");
  };

  const addJournalNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!journalNote.trim()) return;
    await apiFetch(`/api/clients/${caseId}/journal`, { method: "POST", body: JSON.stringify({ summary: journalNote }) });
    setJournalNote("");
    await loadClient();
    notify("Journal entry added & synced to Obsidian.");
  };

  const runHermesAgent = async (instructionText?: string) => {
    const cmd = (instructionText ?? agentInput).trim();
    if (!cmd) return;
    setBusy(true);
    setAgentInput("");
    setAgentHistory((prev) => [...prev, { sender: "user", content: cmd }]);
    try {
      const res = await apiFetch<{
        reply: string;
        provider_used: string;
        tool_trace: Array<{ step: number; tool: string; status: string; detail: string }>;
      }>("/api/agent/staff-run", {
        method: "POST",
        body: JSON.stringify({ case_id: caseId, instruction: cmd }),
      });
      setAgentHistory((prev) => [
        ...prev,
        { sender: "assistant", content: res.reply, trace: res.tool_trace, provider_used: res.provider_used },
      ]);
      await loadClient();
      onUpdated?.();
    } finally {
      setBusy(false);
    }
  };

  if (!client) {
    return <div className="ja-card p-10 text-center text-sm text-slate-500">Loading client workspace {caseId}…</div>;
  }

  const profilePreds = client.predictions.filter((p) => p.question_type === "profile_driven");
  const policyPreds = client.predictions.filter((p) => p.question_type === "policy_mandatory");

  return (
    <div className="space-y-5">
      {/* Header Bar */}
      <div className="ja-card p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-2 rounded-xl border border-slate-200 hover:bg-ja-greenLight text-ja-green transition"
            title="Back to Pipeline"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full bg-ja-green text-ja-goldBright text-xs font-extrabold">
                {client.case_id}
              </span>
              <h2 className="text-lg font-extrabold text-slate-900">{client.full_name || client.pseudonym}</h2>
              <span className="px-2 py-0.5 rounded-full bg-ja-navy/10 text-ja-navy text-xs font-bold">
                {client.visa_class}
              </span>
              <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600">
                Portal Code: {client.access_code}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {client.parish || "Jamaica"} • {client.occupation || "Occupation pending"} • Outcome:{" "}
              <b className="uppercase text-slate-800">{client.outcome}</b>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={client.pipeline_stage}
            onChange={(e) => changeStage(e.target.value)}
            className="ja-input w-44 text-xs font-bold"
          >
            {STAGES.map((st) => (
              <option key={st.id} value={st.id}>
                Stage: {st.label}
              </option>
            ))}
          </select>
          <button onClick={runAuditNow} disabled={busy} className="px-3 py-2 rounded-xl border border-ja-green text-ja-green text-xs font-bold hover:bg-ja-greenLight inline-flex items-center gap-1.5">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Audit
          </button>
          <button onClick={syncObsidian} className="px-3 py-2 rounded-xl bg-ja-navy text-white text-xs font-bold hover:opacity-90 inline-flex items-center gap-1.5">
            <BookOpen className="w-3.5 h-3.5" /> Sync Obsidian
          </button>
        </div>
      </div>

      {toast && (
        <div className="rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 px-4 py-2.5 text-xs font-bold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-700" /> {toast}
        </div>
      )}

      {/* 6-Tab Workspace Switcher */}
      <div className="flex flex-wrap gap-1.5 bg-white p-1.5 rounded-2xl border border-slate-200 shadow-sm">
        {[
          { id: "overview", label: "Overview & Standing", icon: ShieldCheck },
          { id: "intake", label: "Intake & Questionnaire", icon: FileText },
          { id: "interview", label: "Interview Prep & Freeze", icon: MessageSquare },
          { id: "blueprints", label: `Blueprints & Approval (${client.assets.length})`, icon: ImageIcon },
          { id: "journal", label: `Pipeline Journal (${client.journal?.length || 0})`, icon: Clock },
          { id: "agent", label: "Hermes Agent (Hands)", icon: Bot },
        ].map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setTab(item.id as typeof tab)}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition ${
                active ? "bg-ja-green text-ja-goldBright shadow" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <Icon className="w-4 h-4" /> {item.label}
            </button>
          );
        })}
      </div>

      {/* TAB 1: OVERVIEW & GOOD STANDING */}
      {tab === "overview" && (
        <div className="space-y-5">
          <GoodStandingBar score={client.standing_score} riskLevel={client.denial_risk_level} flags={client.risk_flags} />
          {client.open_verification_items && (
            <div className="ja-card p-4 border-l-4 border-ja-gold">
              <div className="text-xs font-extrabold uppercase text-ja-navy">Open Staff Verification Notes</div>
              <p className="text-sm text-slate-800 mt-1">{client.open_verification_items}</p>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: INTAKE FORM & ADAPTIVE QUESTIONNAIRE */}
      {tab === "intake" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <form onSubmit={saveIntake} className="lg:col-span-7 ja-card p-5 space-y-4">
            <h3 className="font-extrabold text-sm text-ja-green uppercase tracking-wider border-b pb-2">
              Structured Client Intake &amp; Encrypted PII Verification
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                ["full_name", "Full Legal Name"],
                ["email", "Email"],
                ["phone", "Phone / WhatsApp"],
                ["parish", "Jamaican Parish"],
                ["passport_number", "Passport Number (Encrypted)"],
                ["passport_expiry", "Passport Expiry (YYYY-MM-DD)"],
                ["dob", "Date of Birth (Encrypted)"],
                ["ds160_confirmation_id", "DS-160 Barcode (AA...)"],
                ["ais_appointment_barcode", "AIS Appointment Barcode"],
                ["embassy_interview_date", "Embassy Interview Date"],
                ["intended_travel_date", "Intended Travel Date"],
                ["intended_return_date", "Intended Return Date"],
                ["us_destination", "U.S. Destination City/State"],
                ["us_host_contact", "U.S. Host / Hotel Address"],
                ["occupation", "Occupation"],
                ["employer_name", "Employer / Business Name"],
                ["monthly_gross_jmd", "Monthly GROSS Salary (JMD)"],
                ["monthly_net_jmd", "Monthly NET Take-Home (JMD)"],
                ["marital_status", "Legal Marital Status"],
                ["children_count", "Children Count"],
                ["prior_us_refusals", "Prior U.S. Refusals Count"],
              ].map(([key, label]) => (
                <div key={key}>
                  <label className="block text-xs font-bold text-slate-700 mb-1">{label}</label>
                  <input
                    className="ja-input text-xs"
                    value={String(form[key] ?? "")}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Purpose of Trip</label>
              <textarea className="ja-input text-xs" rows={2} value={String(form.purpose_of_trip ?? "")} onChange={(e) => setForm({ ...form, purpose_of_trip: e.target.value })} />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(form.has_us_relatives)}
                onChange={(e) => setForm({ ...form, has_us_relatives: e.target.checked })}
              />
              <label className="text-xs font-bold text-slate-800">Has U.S. Relatives / Partner (must disclose truthfully on DS-160)</label>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">U.S. Relatives / Partner Verified Details</label>
              <textarea className="ja-input text-xs" rows={2} value={String(form.us_relatives_details ?? "")} onChange={(e) => setForm({ ...form, us_relatives_details: e.target.value })} />
            </div>
            <button type="submit" disabled={busy} className="ja-btn-primary w-full py-2.5 text-xs">
              {busy ? "Saving & Auditing..." : "Save Client Profile & Re-Calculate Good Standing"}
            </button>
          </form>

          {/* Right: Adaptive Follow-Up Questionnaire triggered by Red/Amber flags */}
          <div className="lg:col-span-5 ja-card p-5 space-y-3">
            <h3 className="font-extrabold text-sm text-ja-navy uppercase tracking-wider border-b pb-2">
              Adaptive Follow-Up Questionnaire (Flag Clearer)
            </h3>
            <p className="text-xs text-slate-500">
              Automatically generated from this client&apos;s missing items and potential contradictions. Record verified responses and mark clear to raise Good Standing.
            </p>
            <div className="space-y-3 max-h-[650px] overflow-y-auto pr-1">
              {client.risk_flags
                .filter((f) => f.follow_up_question)
                .map((f) => (
                  <div key={f.id} className="p-3.5 rounded-xl border bg-slate-50/80 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded text-white ${f.resolved ? "bg-emerald-700" : f.severity === "red" ? "bg-ja-red" : "bg-amber-600"}`}>
                        {f.resolved ? "RESOLVED" : f.severity}
                      </span>
                      <span className="text-[11px] font-bold text-slate-600">{f.code}</span>
                    </div>
                    <p className="text-xs font-bold text-slate-900">{f.follow_up_question}</p>
                    <textarea
                      rows={2}
                      className="ja-input text-xs"
                      placeholder="Enter client's truthful verified answer..."
                      value={qAnswers[f.id] || ""}
                      onChange={(e) => setQAnswers({ ...qAnswers, [f.id]: e.target.value })}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => saveQuestionAnswer(f.id, false)}
                        className="px-3 py-1.5 rounded-lg bg-white border text-xs font-bold text-slate-700 hover:bg-slate-100"
                      >
                        Save Note
                      </button>
                      <button
                        type="button"
                        onClick={() => saveQuestionAnswer(f.id, true)}
                        className="px-3 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-bold hover:bg-emerald-800"
                      >
                        Verify &amp; Mark Resolved
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: INTERVIEW PREDICTIONS, PRE-INTERVIEW FREEZE & MOCK SIMULATOR */}
      {tab === "interview" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-6 space-y-4">
            <div className="ja-card p-5 space-y-3">
              <div className="flex items-center justify-between border-b pb-2.5">
                <div>
                  <h3 className="font-extrabold text-sm text-ja-green">Profile-Driven Ranked Predictions</h3>
                  <p className="text-[11px] text-slate-500">Freeze predictions BEFORE embassy date per Jahtaria evaluation rules.</p>
                </div>
                {client.predictions_frozen ? (
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-extrabold">
                    <Lock className="w-3.5 h-3.5" /> Frozen ({client.predictions_frozen_by})
                  </span>
                ) : (
                  <button onClick={freezePredictions} className="ja-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" /> Freeze Pre-Interview
                  </button>
                )}
              </div>
              <div className="space-y-2">
                {profilePreds.map((p) => (
                  <div
                    key={p.id}
                    onClick={() => setMockQ({ theme: p.theme_id, question_text: p.question_text })}
                    className={`p-3 rounded-xl border cursor-pointer transition ${
                      mockQ?.theme === p.theme_id ? "border-ja-green bg-ja-greenLight" : "bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-extrabold text-ja-green">
                        #{p.rank} • {p.theme_id.replace(/_/g, " ").toUpperCase()}
                      </span>
                      <span className="font-bold text-ja-navy">{Math.round(p.confidence * 100)}% likelihood</span>
                    </div>
                    <p className="text-sm font-bold text-slate-900 mt-1">{p.question_text}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">{p.rationale}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="ja-card p-4 border-l-4 border-ja-navy space-y-2">
              <h4 className="font-extrabold text-xs uppercase text-ja-navy">
                Mandatory Policy Checklist (Tracked Separately from Profile Recall)
              </h4>
              {policyPreds.map((p) => (
                <div key={p.id} className="p-2.5 rounded-lg bg-slate-50 text-xs">
                  <div className="font-bold text-slate-900">{p.question_text}</div>
                  <div className="text-[11px] text-slate-500">{p.rationale}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Mock Interview Simulator + Post-Interview Outcome Recorder */}
          <div className="lg:col-span-6 space-y-4">
            <div className="ja-card p-5 space-y-3">
              <h3 className="font-extrabold text-sm text-ja-navy flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-ja-gold" /> Live Mock Interview Simulator (Truthful Consistency Check)
              </h3>
              {mockQ && (
                <div className="p-3.5 rounded-xl bg-ja-green text-white">
                  <div className="text-[10px] uppercase font-bold text-ja-goldBright">Consular Officer Question ({mockQ.theme})</div>
                  <div className="text-sm font-bold mt-1">&ldquo;{mockQ.question_text}&rdquo;</div>
                </div>
              )}
              <textarea
                rows={3}
                className="ja-input text-xs"
                placeholder="Type client's practice answer to check conciseness & DS-160 alignment..."
                value={mockAns}
                onChange={(e) => setMockAns(e.target.value)}
              />
              <button onClick={submitMockPractice} disabled={busy || !mockAns.trim()} className="ja-btn-primary w-full py-2 text-xs">
                Evaluate Practice Answer
              </button>
              {mockFeedback && (
                <div className="p-3 rounded-xl bg-blue-50 border border-blue-200 text-xs text-slate-800 leading-relaxed">
                  <div className="font-extrabold text-ja-navy mb-1">Advisor Coaching Feedback:</div>
                  {mockFeedback}
                </div>
              )}
            </div>

            <div className="ja-card p-5 space-y-3">
              <h3 className="font-extrabold text-sm text-ja-green">Record Post-Interview Embassy Outcome</h3>
              <div className="grid grid-cols-2 gap-3">
                <select className="ja-input text-xs" value={outcomeVal} onChange={(e) => setOutcomeVal(e.target.value)}>
                  <option value="approved">Approved</option>
                  <option value="refused">Refused</option>
                  <option value="221g">221(g) Administrative Processing</option>
                  <option value="pending">Pending</option>
                </select>
                <input
                  className="ja-input text-xs"
                  placeholder="Refusal Statute (e.g. INA 214(b)) if documented"
                  value={refusalStatute}
                  onChange={(e) => setRefusalStatute(e.target.value)}
                />
              </div>
              <button onClick={submitOutcome} className="px-4 py-2 rounded-xl bg-ja-navy text-white text-xs font-bold w-full hover:opacity-90">
                Log Embassy Outcome
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: BLUEPRINTS, DOCUMENT AUTO-FILL, VISUAL ROADMAP & APPROVAL GATE */}
      {tab === "blueprints" && (
        <div className="space-y-5">
          <div className="ja-card p-5 space-y-4">
            <div>
              <h3 className="font-extrabold text-sm text-ja-green">
                Auto-Fill Engine — Generate Drafts (Human Approval Gate Required Before Client Release)
              </h3>
              <p className="text-xs text-slate-500">
                Every generated file starts as <b>Pending Approval</b>. Preview the document below and click <b>Approve &amp; Share</b> to unlock it in the Customer Portal.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <button onClick={() => generateAsset("ds160_worksheet_pdf")} disabled={busy} className="p-3.5 rounded-xl border-2 border-ja-green/20 hover:border-ja-green bg-ja-greenLight/40 text-left transition">
                <div className="font-extrabold text-xs text-ja-green">1. DS-160 Worksheet (PDF)</div>
                <div className="text-[11px] text-slate-600 mt-1">Auto-filled profile, Gross/Net JMD &amp; Risk Findings</div>
              </button>
              <button onClick={() => generateAsset("checklist_pdf")} disabled={busy} className="p-3.5 rounded-xl border-2 border-ja-navy/20 hover:border-ja-navy bg-blue-50/40 text-left transition">
                <div className="font-extrabold text-xs text-ja-navy">2. Kingston Checklist (PDF)</div>
                <div className="text-[11px] text-slate-600 mt-1">Embassy docs, 92% RGD rule &amp; ranked Q&amp;A</div>
              </button>
              <button onClick={() => generateAsset("cover_letter_docx")} disabled={busy} className="p-3.5 rounded-xl border-2 border-amber-300 hover:border-amber-500 bg-amber-50/40 text-left transition">
                <div className="font-extrabold text-xs text-amber-900">3. Support Packet (DOCX)</div>
                <div className="text-[11px] text-slate-600 mt-1">Editable Word/Google Docs verification cover packet</div>
              </button>
              <button onClick={() => generateAsset("visual_roadmap_png")} disabled={busy} className="p-3.5 rounded-xl border-2 border-emerald-300 hover:border-emerald-600 bg-emerald-50/50 text-left transition">
                <div className="font-extrabold text-xs text-emerald-900">4. Visual Roadmap (PNG)</div>
                <div className="text-[11px] text-slate-600 mt-1">Jamaican-themed 5-step client visual guide image</div>
              </button>
            </div>

            {blueprints.length > 0 && (
              <div className="pt-3 border-t flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-slate-700">Fill Custom Uploaded Blueprint:</span>
                <select className="ja-input w-80 text-xs" value={selectedBpKey} onChange={(e) => setSelectedBpKey(e.target.value)}>
                  {blueprints.map((b) => (
                    <option key={b.doc_key} value={b.doc_key}>
                      {b.title} ({b.file_format})
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => generateAsset("custom_blueprint", selectedBpKey)}
                  disabled={busy || !selectedBpKey}
                  className="ja-btn-primary px-4 py-2 text-xs"
                >
                  Auto-Fill Selected Blueprint
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <div className="lg:col-span-5 ja-card p-4 space-y-2.5 max-h-[600px] overflow-y-auto">
              <h4 className="font-extrabold text-xs uppercase text-ja-navy border-b pb-2">
                Generated Case Deliverables ({client.assets.length})
              </h4>
              {client.assets.map((a) => (
                <div key={a.id} className="p-3 rounded-xl border bg-white space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-bold text-xs text-slate-900">{a.title}</div>
                      <div className="text-[11px] text-slate-500">{a.filename}</div>
                    </div>
                    <span
                      className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full ${
                        a.approval_status === "approved"
                          ? "bg-emerald-100 text-emerald-800"
                          : a.approval_status === "rejected"
                          ? "bg-red-100 text-red-800"
                          : "bg-amber-100 text-amber-900"
                      }`}
                    >
                      {a.approval_status.replace("_", " ")}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      onClick={() => setPreviewAsset({ id: a.id, title: a.title, mime_type: a.mime_type })}
                      className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-700"
                    >
                      Preview
                    </button>
                    <a
                      href={`/api/assets/${a.id}/file`}
                      download={a.filename}
                      className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-ja-navy hover:text-white text-xs font-bold text-slate-700 inline-flex items-center gap-1"
                    >
                      <Download className="w-3 h-3" /> Download
                    </a>
                    {a.approval_status !== "approved" && (
                      <button
                        onClick={() => decideAsset(a.id, "approved")}
                        className="px-2.5 py-1 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold inline-flex items-center gap-1"
                      >
                        <CheckCircle2 className="w-3 h-3" /> Approve &amp; Share
                      </button>
                    )}
                    {a.approval_status === "pending_approval" && (
                      <button
                        onClick={() => decideAsset(a.id, "rejected")}
                        className="px-2.5 py-1 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold inline-flex items-center gap-1"
                      >
                        <XCircle className="w-3 h-3" /> Reject
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {client.assets.length === 0 && (
                <p className="text-xs text-slate-400 py-8 text-center">Click any generator card above to create a draft document or visual roadmap.</p>
              )}
            </div>

            <div className="lg:col-span-7 ja-card p-4 h-[600px] flex flex-col">
              {previewAsset ? (
                <>
                  <div className="font-bold text-sm text-ja-green pb-2 border-b">{previewAsset.title}</div>
                  <div className="flex-1 mt-3 rounded-xl overflow-hidden border bg-slate-100 flex items-center justify-center">
                    {previewAsset.mime_type === "application/pdf" ? (
                      <iframe src={`/api/assets/${previewAsset.id}/file`} className="w-full h-full border-0" title={previewAsset.title} />
                    ) : previewAsset.mime_type === "image/png" ? (
                      <img src={`/api/assets/${previewAsset.id}/file`} alt={previewAsset.title} className="max-w-full max-h-full object-contain" />
                    ) : (
                      <div className="text-center p-6 space-y-3">
                        <FileText className="w-12 h-12 text-ja-navy mx-auto" />
                        <p className="text-xs text-slate-600">DOCX document ready for Microsoft Word or Google Docs.</p>
                        <a href={`/api/assets/${previewAsset.id}/file`} className="ja-btn-primary px-4 py-2 text-xs inline-block">
                          Download DOCX
                        </a>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-slate-400">
                  Select or generate a PDF / Visual Roadmap PNG to preview before approving.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: CHRONOLOGICAL PIPELINE JOURNAL */}
      {tab === "journal" && (
        <div className="ja-card p-5 space-y-4">
          <h3 className="font-extrabold text-sm text-ja-green">Chronological Customer Pipeline Journal</h3>
          <form onSubmit={addJournalNote} className="flex gap-2">
            <input
              className="ja-input text-xs"
              placeholder="Add staff call note, Gmail follow-up summary, or verification milestone..."
              value={journalNote}
              onChange={(e) => setJournalNote(e.target.value)}
            />
            <button type="submit" className="ja-btn-primary px-4 text-xs shrink-0">
              Log Entry
            </button>
          </form>
          <div className="space-y-2.5 max-h-[520px] overflow-y-auto">
            {(client.journal || []).map((j) => (
              <div key={j.id} className="p-3.5 rounded-xl border bg-slate-50/80 flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-ja-greenLight text-ja-green text-[10px] font-extrabold uppercase">
                      {j.event_type.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs font-bold text-slate-700">{j.actor}</span>
                  </div>
                  <p className="text-xs text-slate-800 mt-1">{j.summary}</p>
                </div>
                <span className="text-[11px] text-slate-400 shrink-0">
                  {j.created_at ? new Date(j.created_at).toLocaleString() : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 6: HERMES AUTONOMOUS AGENT CONSOLE ("HANDS") */}
      {tab === "agent" && (
        <div className="ja-card p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
            <div>
              <h3 className="font-extrabold text-sm text-ja-green flex items-center gap-2">
                <Bot className="w-4 h-4" /> Hermes Autonomous Agent Console (&ldquo;Hands&rdquo;) — Case {client.case_id}
              </h3>
              <p className="text-xs text-slate-500">
                Runs multi-step tool loops (Audit → Official Gov Check → Self-Correction → Draft Packet → Obsidian Sync) and pauses at the Human Approval Gate.
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => runHermesAgent(`Audit ${client.case_id}, check official Kingston Embassy rules, generate full draft packet and visual roadmap, and sync Obsidian`)}
                disabled={busy}
                className="px-3 py-1.5 rounded-lg bg-ja-greenLight text-ja-green text-xs font-bold hover:bg-ja-green hover:text-white transition"
              >
                1-Click Full Audit &amp; Draft Packet
              </button>
              <button
                onClick={() => runHermesAgent(`Scrape latest PICA passport & Kingston Embassy barcode rules for ${client.case_id}`)}
                disabled={busy}
                className="px-3 py-1.5 rounded-lg bg-blue-50 text-ja-navy text-xs font-bold hover:bg-ja-navy hover:text-white transition"
              >
                Verify Live Gov Rules
              </button>
            </div>
          </div>

          <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
            {agentHistory.map((m, i) => (
              <div key={i} className={`p-3.5 rounded-xl text-xs ${m.sender === "user" ? "bg-ja-navy text-white ml-12" : "bg-slate-50 border mr-6"}`}>
                <div className="font-extrabold mb-1 flex items-center justify-between">
                  <span>{m.sender === "user" ? "Staff Instruction" : "Hermes Agent"}</span>
                  {m.provider_used && <span className="text-[10px] opacity-70">{m.provider_used}</span>}
                </div>
                {m.trace && m.trace.length > 0 && (
                  <div className="mb-2.5 space-y-1 bg-slate-900 text-emerald-300 p-2.5 rounded-lg font-mono text-[11px]">
                    {m.trace.map((t) => (
                      <div key={t.step}>
                        [{t.step}] {t.tool} ({t.status}) → {t.detail}
                      </div>
                    ))}
                  </div>
                )}
                <div className="whitespace-pre-wrap leading-relaxed">{m.content}</div>
              </div>
            ))}
            {agentHistory.length === 0 && (
              <div className="text-center text-xs text-slate-400 py-10">
                Give Hermes a mission for {client.case_id} (e.g. &ldquo;Audit income contradictions, generate DS-160 worksheet &amp; visual roadmap, and sync Obsidian&rdquo;).
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <input
              className="ja-input text-xs"
              placeholder={`Command Hermes for ${client.case_id}...`}
              value={agentInput}
              onChange={(e) => setAgentInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runHermesAgent()}
            />
            <button onClick={() => runHermesAgent()} disabled={busy} className="ja-btn-primary px-4 text-xs inline-flex items-center gap-1.5 shrink-0">
              <Send className="w-3.5 h-3.5" /> {busy ? "Running..." : "Run Agent"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
