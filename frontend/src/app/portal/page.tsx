"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  MessageCircle,
  ClipboardList,
  Sparkles,
  FileCheck2,
  Send,
  ExternalLink,
  Download,
  CheckCircle2,
} from "lucide-react";
import { apiFetch, getStoredUser } from "@/lib/api";
import type { BrandingConfig, ClientDetail, UserAccount } from "@/lib/types";
import { AppShell } from "@/components/AppShell";
import { GoodStandingBar } from "@/components/GoodStandingBar";

interface ChatMsg {
  sender: string;
  content: string;
  citations?: Array<{ name: string; agency: string; url: string }>;
  provider_used?: string;
}

export default function CustomerPortalPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [branding, setBranding] = useState<BrandingConfig | null>(null);
  const [myCase, setMyCase] = useState<ClientDetail | null>(null);
  const [tab, setTab] = useState<"assistant" | "intake" | "practice" | "docs">("assistant");

  // Chat state
  const [messages, setMessages] = useState<ChatMsg[]>([
    {
      sender: "assistant",
      content:
        "Welcome to your Jahtaria U.S. Visa Preparation Portal! Ask me anything about U.S. Embassy Kingston requirements, DS-160 AA barcodes, MRV fees ($185 / $205), PICA passport validity, RGD 92% birth certificate copies, or what to bring on interview day.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);

  // Client Intake & Questionnaire state
  const [form, setForm] = useState<Record<string, string | number>>({});
  const [qResp, setQResp] = useState<Record<number, string>>({});
  const [savedMsg, setSavedMsg] = useState("");

  // Mock Practice state
  const [activeQ, setActiveQ] = useState<{ theme: string; question_text: string } | null>(null);
  const [practiceAns, setPracticeAns] = useState("");
  const [practiceFeedback, setPracticeFeedback] = useState("");

  const loadMyCase = async () => {
    const data = await apiFetch<ClientDetail>("/api/portal/my-case");
    setMyCase(data);
    setForm({
      full_name: data.full_name || "",
      phone: data.phone || "",
      parish: data.parish || "",
      passport_expiry: data.passport_expiry || "",
      ds160_confirmation_id: data.ds160_confirmation_id || "",
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
    });
    const rMap: Record<number, string> = {};
    data.risk_flags.forEach((f) => {
      rMap[f.id] = f.client_response || "";
    });
    setQResp(rMap);
    if (!activeQ && data.predictions.length > 0) {
      setActiveQ({ theme: data.predictions[0].theme_id, question_text: data.predictions[0].question_text });
    }
  };

  useEffect(() => {
    const u = getStoredUser<UserAccount>();
    if (!u) {
      router.replace("/login");
      return;
    }
    setUser(u);
    fetch("/api/branding").then((r) => r.json()).then(setBranding).catch(() => {});
    loadMyCase().catch(() => {});
  }, [router]);

  const sendChat = async (customPrompt?: string) => {
    const txt = (customPrompt ?? chatInput).trim();
    if (!txt) return;
    setChatInput("");
    setSending(true);
    setMessages((prev) => [...prev, { sender: "user", content: txt }]);
    try {
      const res = await apiFetch<{
        reply: string;
        citations: Array<{ name: string; agency: string; url: string }>;
        provider_used: string;
      }>("/api/agent/customer-chat", {
        method: "POST",
        body: JSON.stringify({ message: txt }),
      });
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", content: res.reply, citations: res.citations, provider_used: res.provider_used },
      ]);
    } finally {
      setSending(false);
    }
  };

  const saveClientIntake = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!myCase) return;
    await apiFetch(`/api/clients/${myCase.case_id}`, {
      method: "PATCH",
      body: JSON.stringify({
        ...form,
        monthly_gross_jmd: form.monthly_gross_jmd === "" ? null : Number(form.monthly_gross_jmd),
        monthly_net_jmd: form.monthly_net_jmd === "" ? null : Number(form.monthly_net_jmd),
      }),
    });
    await loadMyCase();
    setSavedMsg("Your details were saved securely and your Good Standing bar has been updated!");
    setTimeout(() => setSavedMsg(""), 4000);
  };

  const submitAnswer = async (flagId: number) => {
    if (!myCase) return;
    await apiFetch(`/api/clients/${myCase.case_id}/questionnaire`, {
      method: "POST",
      body: JSON.stringify({ flag_id: flagId, client_response: qResp[flagId] || "", mark_resolved: false }),
    });
    await loadMyCase();
    setSavedMsg("Response submitted for advisor review!");
    setTimeout(() => setSavedMsg(""), 4000);
  };

  const submitPractice = async () => {
    if (!myCase || !activeQ || !practiceAns.trim()) return;
    setSending(true);
    try {
      const res = await apiFetch<{ feedback: string }>(`/api/clients/${myCase.case_id}/mock-practice`, {
        method: "POST",
        body: JSON.stringify({ theme: activeQ.theme, question_text: activeQ.question_text, client_answer: practiceAns }),
      });
      setPracticeFeedback(res.feedback);
      setPracticeAns("");
    } finally {
      setSending(false);
    }
  };

  if (!user) return null;

  return (
    <AppShell user={user} branding={branding} activePortal="portal">
      <div className="space-y-5">
        {/* Welcome Banner */}
        <div className="rounded-2xl bg-gradient-to-r from-ja-green via-[#154225] to-ja-navy text-white p-6 shadow-lg flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="inline-block px-2.5 py-0.5 rounded-full bg-ja-goldBright text-ja-green text-[10px] font-extrabold uppercase tracking-wider">
              Customer Visa Portal • Case {myCase?.case_id || "Loading"}
            </span>
            <h1 className="text-2xl font-extrabold mt-1">
              Welcome, {myCase?.full_name || user.full_name}
            </h1>
            <p className="text-xs text-emerald-100/90 mt-0.5">
              Visa Type: <b>{myCase?.visa_class || "B1/B2"}</b> • Stage:{" "}
              <b className="uppercase">{(myCase?.pipeline_stage || "").replace(/_/g, " ")}</b> • Access Code:{" "}
              <code className="bg-white/15 px-1.5 py-0.5 rounded">{myCase?.access_code}</code>
            </p>
          </div>
          {myCase?.embassy_interview_date && (
            <div className="bg-white/10 backdrop-blur border border-white/20 rounded-xl px-4 py-2.5 text-right">
              <div className="text-[10px] uppercase tracking-wider text-ja-goldBright font-bold">Target Embassy Date</div>
              <div className="text-lg font-extrabold">{myCase.embassy_interview_date}</div>
            </div>
          )}
        </div>

        {myCase && <GoodStandingBar score={myCase.standing_score} riskLevel={myCase.denial_risk_level} flags={myCase.risk_flags} compact />}

        {/* Portal Tabs */}
        <div className="flex flex-wrap gap-1.5 bg-white p-1.5 rounded-2xl border border-slate-200 shadow-sm">
          {[
            { id: "assistant", label: "Ask Visa AI Assistant", icon: MessageCircle },
            { id: "intake", label: "My Details & Questionnaire", icon: ClipboardList },
            { id: "practice", label: "Practice Mock Interview", icon: Sparkles },
            { id: "docs", label: `My Approved Docs & Roadmap (${myCase?.assets.length || 0})`, icon: FileCheck2 },
          ].map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id as typeof tab)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition ${
                  tab === t.id ? "bg-ja-green text-ja-goldBright shadow" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>

        {/* TAB 1: CUSTOMER AI Q&A ASSISTANT */}
        {tab === "assistant" && (
          <div className="ja-card p-5 space-y-4">
            <div className="flex flex-wrap gap-2">
              {[
                "What are the 2026 U.S. visa fees & how do I book in Kingston?",
                "Explain the April 1, 2025 DS-160 barcode rule",
                "What documents must I bring to 142 Old Hope Road?",
                "How do I renew my Jamaican passport with PICA?",
              ].map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => sendChat(prompt)}
                  className="px-3 py-1.5 rounded-full bg-ja-greenLight text-ja-green text-xs font-bold hover:bg-ja-green hover:text-white transition"
                >
                  {prompt}
                </button>
              ))}
            </div>

            <div className="space-y-3 max-h-[440px] overflow-y-auto pr-1">
              {messages.map((m, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-2xl text-sm leading-relaxed ${
                    m.sender === "user"
                      ? "bg-ja-navy text-white ml-12"
                      : "bg-slate-50 border border-slate-200 mr-8 text-slate-800"
                  }`}
                >
                  <div className="whitespace-pre-wrap">{m.content}</div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-slate-200 flex flex-wrap gap-2">
                      {m.citations.map((c, ci) => (
                        <a
                          key={ci}
                          href={c.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] font-bold text-ja-green bg-ja-greenLight px-2.5 py-1 rounded-full inline-flex items-center gap-1 hover:underline"
                        >
                          {c.agency}: {c.name.slice(0, 34)} <ExternalLink className="w-3 h-3" />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <input
                className="ja-input"
                placeholder="Type your U.S. visa or Jamaican passport question here..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendChat()}
              />
              <button onClick={() => sendChat()} disabled={sending} className="ja-btn-primary px-5 text-xs inline-flex items-center gap-1.5 shrink-0">
                <Send className="w-4 h-4" /> Ask
              </button>
            </div>
          </div>
        )}

        {/* TAB 2: CLIENT INTAKE & ADAPTIVE QUESTIONNAIRE */}
        {tab === "intake" && myCase && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <form onSubmit={saveClientIntake} className="lg:col-span-7 ja-card p-5 space-y-3.5">
              <h3 className="font-extrabold text-sm text-ja-green border-b pb-2">My Travel &amp; DS-160 Preparation Details</h3>
              {savedMsg && (
                <div className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-bold text-emerald-800 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" /> {savedMsg}
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  ["full_name", "Full Legal Name (as on Passport)"],
                  ["phone", "WhatsApp / Phone"],
                  ["parish", "Jamaican Parish"],
                  ["passport_expiry", "Passport Expiry Date (YYYY-MM-DD)"],
                  ["ds160_confirmation_id", "DS-160 Barcode (starts with AA)"],
                  ["intended_travel_date", "Intended Travel Date"],
                  ["intended_return_date", "Intended Return Date"],
                  ["us_destination", "U.S. Destination City & State"],
                  ["occupation", "Current Job Title"],
                  ["employer_name", "Employer / Business Name"],
                  ["monthly_gross_jmd", "Monthly GROSS Salary (JMD)"],
                  ["monthly_net_jmd", "Monthly NET Take-Home (JMD)"],
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
                <label className="block text-xs font-bold text-slate-700 mb-1">Purpose of Visit</label>
                <textarea className="ja-input text-xs" rows={2} value={String(form.purpose_of_trip ?? "")} onChange={(e) => setForm({ ...form, purpose_of_trip: e.target.value })} />
              </div>
              <button type="submit" className="ja-btn-primary w-full py-2.5 text-xs">
                Save My Details &amp; Refresh Readiness Score
              </button>
            </form>

            <div className="lg:col-span-5 ja-card p-5 space-y-3">
              <h3 className="font-extrabold text-sm text-ja-navy border-b pb-2">Questions From Your Visa Advisor</h3>
              {myCase.risk_flags.filter((f) => f.follow_up_question).map((f) => (
                <div key={f.id} className="p-3.5 rounded-xl border bg-slate-50 space-y-2">
                  <div className="font-bold text-xs text-slate-900">{f.follow_up_question}</div>
                  <textarea
                    rows={2}
                    className="ja-input text-xs"
                    placeholder="Type your truthful answer..."
                    value={qResp[f.id] || ""}
                    onChange={(e) => setQResp({ ...qResp, [f.id]: e.target.value })}
                  />
                  <button onClick={() => submitAnswer(f.id)} className="px-3 py-1.5 rounded-lg bg-ja-green text-ja-goldBright text-xs font-bold">
                    Submit Answer
                  </button>
                </div>
              ))}
              {myCase.risk_flags.filter((f) => f.follow_up_question).length === 0 && (
                <p className="text-xs text-emerald-700 font-bold">All follow-up questions are cleared! You are in great standing.</p>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: PRACTICE MOCK INTERVIEW */}
        {tab === "practice" && myCase && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <div className="lg:col-span-5 ja-card p-5 space-y-2.5">
              <h3 className="font-extrabold text-sm text-ja-green border-b pb-2">Select a Practice Embassy Question</h3>
              {myCase.predictions.map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setActiveQ({ theme: p.theme_id, question_text: p.question_text });
                    setPracticeFeedback("");
                  }}
                  className={`w-full text-left p-3 rounded-xl border text-xs transition ${
                    activeQ?.theme === p.theme_id ? "border-ja-green bg-ja-greenLight" : "bg-white hover:border-slate-300"
                  }`}
                >
                  <div className="font-extrabold text-ja-navy uppercase text-[10px]">
                    {p.question_type === "policy_mandatory" ? "Standard Policy Question" : `Likely Question #${p.rank}`}
                  </div>
                  <div className="font-bold text-slate-900 mt-0.5">{p.question_text}</div>
                </button>
              ))}
            </div>
            <div className="lg:col-span-7 ja-card p-5 space-y-4">
              {activeQ && (
                <div className="p-4 rounded-xl bg-ja-green text-white">
                  <div className="text-[11px] font-bold uppercase text-ja-goldBright">Practice Officer Question</div>
                  <div className="text-base font-extrabold mt-1">&ldquo;{activeQ.question_text}&rdquo;</div>
                </div>
              )}
              <textarea
                rows={4}
                className="ja-input text-sm"
                placeholder="Type how you would naturally and truthfully answer the Consular Officer..."
                value={practiceAns}
                onChange={(e) => setPracticeAns(e.target.value)}
              />
              <button onClick={submitPractice} disabled={sending || !practiceAns.trim()} className="ja-btn-primary w-full py-2.5 text-xs">
                Get Truthful Coaching Feedback
              </button>
              {practiceFeedback && (
                <div className="p-4 rounded-xl bg-blue-50 border border-blue-200 text-sm text-slate-800 leading-relaxed">
                  <div className="font-extrabold text-ja-navy text-xs uppercase mb-1">Advisor Feedback</div>
                  {practiceFeedback}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: APPROVED CLIENT DOCUMENTS & VISUAL ROADMAP */}
        {tab === "docs" && myCase && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {myCase.assets.map((a) => (
              <div key={a.id} className="ja-card p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                      Advisor Approved
                    </span>
                    <h4 className="font-extrabold text-sm text-slate-900 mt-1">{a.title}</h4>
                  </div>
                  <a
                    href={`/api/assets/${a.id}/file`}
                    download={a.filename}
                    className="ja-btn-primary px-3 py-1.5 text-xs inline-flex items-center gap-1 shrink-0"
                  >
                    <Download className="w-3.5 h-3.5" /> Download
                  </a>
                </div>
                {a.mime_type === "image/png" && (
                  <img
                    src={`/api/assets/${a.id}/file`}
                    alt={a.title}
                    className="w-full rounded-xl border shadow-sm"
                  />
                )}
                {a.mime_type === "application/pdf" && (
                  <iframe
                    src={`/api/assets/${a.id}/file`}
                    title={a.title}
                    className="w-full h-80 rounded-xl border"
                  />
                )}
              </div>
            ))}
            {myCase.assets.length === 0 && (
              <div className="ja-card p-10 text-center text-sm text-slate-500 col-span-2">
                Your advisor is currently preparing and verifying your documents. Approved PDFs and your Visual Action Roadmap will appear right here!
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
