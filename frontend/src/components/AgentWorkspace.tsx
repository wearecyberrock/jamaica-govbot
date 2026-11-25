"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  PanelLeft,
  PanelRight,
  Users,
  FileText,
  Globe,
  Database,
  BookOpen,
  BarChart3,
  Settings,
  LogOut,
  Send,
  ChevronDown,
  UserPlus,
  Sparkles,
  ExternalLink,
  Image as ImageIcon,
  ShieldCheck,
  MessageSquare,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Paperclip,
  Trash2,
  CheckCircle2,
  RotateCcw,
} from "lucide-react";
import { apiFetch, clearAuthSession, getStoredToken, getStoredUser } from "@/lib/api";
import type { BrandingConfig, ClientSummary, UserAccount } from "@/lib/types";
import { RightSidePanel, type PanelRequest } from "./RightSidePanel";
import { RichMarkdown } from "./RichMarkdown";

interface PendingActionData {
  id: number;
  action_type: string;
  target_ref: string;
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  status: string;
}

interface ChatTurn {
  sender: "user" | "assistant";
  content: string;
  provider_used?: string;
  tool_trace?: Array<{ step: number; tool: string; status: string; detail: string }>;
  citations?: Array<{ name: string; agency: string; url: string }>;
  created_assets?: Array<{ id: number; title: string; mime_type: string; file_url: string }>;
  panel?: PanelRequest | null;
  pending_action?: PendingActionData | null;
}

interface SavedConv {
  id: string;
  title: string;
  case_id: string | null;
  updated_at: string | null;
}

export function AgentWorkspace({ requiredRole }: { requiredRole?: "ceo" | "staff" | "customer" }) {
  const router = useRouter();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [branding, setBranding] = useState<BrandingConfig | null>(null);

  // Sidebars & panels
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightPanel, setRightPanel] = useState<PanelRequest | null>(null);
  const [recentPanels, setRecentPanels] = useState<PanelRequest[]>([]);

  // Saved multi-conversation history + clean Active Clients list
  const [conversations, setConversations] = useState<SavedConv[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [activeClients, setActiveClients] = useState<ClientSummary[]>([]);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);

  // Grouped Model Catalog (loaded from /api/models/catalog — zero "Hermes" mention!)
  const [modelCatalog, setModelCatalog] = useState<any>(null);
  const [activeProvider, setActiveProvider] = useState("auto");
  const [activeModel, setActiveModel] = useState("consular-auto");

  // Voice Mode (available to CEO, Staff & Customers!)
  const [voiceMode, setVoiceMode] = useState(false);
  const [voicePersona, setVoicePersona] = useState("advisor_ja");
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<any>(null);

  // Chat state
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"chat" | "task">("chat");
  const [busy, setBusy] = useState(false);
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [panelRefreshNonce, setPanelRefreshNonce] = useState(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const loadConversations = () => {
    apiFetch<SavedConv[]>("/api/conversations").then(setConversations).catch(() => {});
  };

  const loadModelCatalog = () => {
    apiFetch<any>("/api/models/catalog")
      .then((cat) => {
        setModelCatalog(cat);
        setActiveProvider(cat.active_provider || "auto");
        setActiveModel(cat.active_model || "consular-auto");
      })
      .catch(() => {});
  };

  useEffect(() => {
    const u = getStoredUser<UserAccount>();
    if (!u) {
      router.replace("/login");
      return;
    }
    if (requiredRole && u.role !== requiredRole && !(u.role === "ceo" && requiredRole === "staff")) {
      if (u.role === "ceo") router.replace("/ceo");
      else if (u.role === "staff") router.replace("/staff");
      else router.replace("/portal");
      return;
    }
    setUser(u);
    if (u.role === "customer" && u.linked_case_id) {
      setActiveCaseId(u.linked_case_id);
      setVoicePersona("officer_us");
    }

    fetch("/api/branding").then((r) => r.json()).then(setBranding).catch(() => {});
    loadConversations();
    loadModelCatalog();

    if (u.role === "ceo" || u.role === "staff") {
      apiFetch<ClientSummary[]>("/api/clients")
        .then((list) => {
          // Keep left sidebar super clean: only active live clients (33 historical reference cases live under Clients -> Historical)
          const activeOnly = list.filter(
            (c) => !(c.full_name || "").startsWith("Reference Case") && !(c.full_name || "").startsWith("Case C00")
          );
          setActiveClients(activeOnly.slice(0, 8));
        })
        .catch(() => {});
    }
  }, [router, requiredRole]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  const openPanel = (req: PanelRequest) => {
    setRightPanel(req);
    setRecentPanels((prev) => {
      const dedup = prev.filter(
        (p) => !(p.panel === req.panel && p.case_id === req.case_id && p.doc_key === req.doc_key && p.table === req.table)
      );
      return [req, ...dedup].slice(0, 8);
    });
  };

  const speakText = async (text: string, personaOverride?: string) => {
    try {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      setSpeaking(true);
      const token = getStoredToken();
      const res = await fetch("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ text, persona: personaOverride || voicePersona }),
      });
      if (!res.ok) {
        setSpeaking(false);
        return;
      }
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audioRef.current = audio;
      audio.onended = () => setSpeaking(false);
      audio.onerror = () => setSpeaking(false);
      await audio.play();
    } catch {
      setSpeaking(false);
    }
  };

  const stopSpeaking = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setSpeaking(false);
  };

  const toggleMic = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      setTurns((prev) => [
        ...prev,
        { sender: "assistant", content: "Voice microphone input requires Chromium/Edge/Chrome browser speech support." },
      ]);
      return;
    }
    const rec = new SpeechRec();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.onresult = (event: any) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      if (transcript.trim()) {
        setInput(transcript);
        sendMessage(transcript);
      }
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    setListening(true);
    rec.start();
  };

  const loadThread = async (conv: SavedConv) => {
    setActiveConvId(conv.id);
    if (conv.case_id) setActiveCaseId(conv.case_id);
    const msgs = await apiFetch<ChatTurn[]>(`/api/conversations/${conv.id}/messages`);
    setTurns(msgs);
  };

  const handleFileUpload = async (file: File) => {
    if (!file || user?.role === "customer") return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (activeCaseId) fd.append("case_id", activeCaseId);
      const res = await apiFetch<{ title: string; filename: string; detected_fields: string[]; panel: PanelRequest }>(
        "/api/agent/upload-chat-file",
        { method: "POST", body: fd }
      );
      setTurns((prev) => [
        ...prev,
        { sender: "user", content: `Attached file: \`${res.filename}\`` },
        {
          sender: "assistant",
          content: `Indexed **${res.title}** (${res.detected_fields.length} fillable fields detected) and opened it in the side panel.`,
          panel: res.panel,
        },
      ]);
      openPanel(res.panel);
    } finally {
      setBusy(false);
    }
  };

  const handleModelSwitch = async (combined: string) => {
    const [prov, mdl] = combined.split("::");
    if (!prov || !mdl) return;
    // Check if subscription is connected — if not, immediately open Settings Sign-In card!
    const allItems = (modelCatalog?.groups || []).flatMap((g: any) => g.items || []);
    const item = allItems.find((i: any) => i.provider === prov);
    if (item && !item.connected && prov !== "auto") {
      openPanel({ panel: "settings", title: `Connect ${item.label}` });
      return;
    }
    setActiveProvider(prov);
    setActiveModel(mdl);
    if (user?.role === "ceo" || user?.role === "staff") {
      await apiFetch("/api/models/select", { method: "POST", body: JSON.stringify({ provider: prov, model: mdl }) });
    }
  };

  const sendMessage = async (customText?: string, overrideMode?: "chat" | "task") => {
    const text = (customText ?? input).trim();
    if (!text || busy) return;
    const activeMode = overrideMode || mode;
    setInput("");
    setShowPlusMenu(false);
    setBusy(true);
    setTurns((prev) => [...prev, { sender: "user", content: text }]);

    try {
      const res = await apiFetch<{
        conversation_id: string;
        reply: string;
        provider_used: string;
        tool_trace: Array<{ step: number; tool: string; status: string; detail: string }>;
        citations: Array<{ name: string; agency: string; url: string }>;
        created_assets: Array<{ id: number; title: string; mime_type: string; file_url: string }>;
        ui_panel: PanelRequest | null;
        pending_action: PendingActionData | null;
      }>("/api/agent/command", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          mode: activeMode,
          case_id: activeCaseId,
          conversation_id: activeConvId,
        }),
      });

      setActiveConvId(res.conversation_id);
      loadConversations();

      if (res.ui_panel) {
        openPanel(res.ui_panel);
        if (res.ui_panel.case_id) setActiveCaseId(res.ui_panel.case_id);
      }
      setPanelRefreshNonce((n) => n + 1);

      setTurns((prev) => [
        ...prev,
        {
          sender: "assistant",
          content: res.reply,
          provider_used: res.provider_used,
          tool_trace: res.tool_trace,
          citations: res.citations,
          created_assets: res.created_assets,
          panel: res.ui_panel,
          pending_action: res.pending_action,
        },
      ]);

      if (voiceMode && res.reply) {
        speakText(res.reply);
      }
    } catch (err: unknown) {
      setTurns((prev) => [
        ...prev,
        { sender: "assistant", content: `Error: ${err instanceof Error ? err.message : "Request failed"}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const handleActionDecision = async (turnIdx: number, actionId: number, op: "confirm" | "undo" | "cancel") => {
    const updated = await apiFetch<PendingActionData>(`/api/actions/${actionId}/${op}`, { method: "POST" });
    setTurns((prev) =>
      prev.map((t, i) => (i === turnIdx ? { ...t, pending_action: updated } : t))
    );
    setPanelRefreshNonce((n) => n + 1);
    if (updated.action_type === "update_branding") {
      fetch("/api/branding").then((r) => r.json()).then(setBranding).catch(() => {});
    }
  };

  const handleLogout = async () => {
    stopSpeaking();
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // ignore
    }
    clearAuthSession();
    router.push("/login");
  };

  if (!user) return null;

  const isCeo = user.role === "ceo";
  const isStaffOrCeo = user.role === "ceo" || user.role === "staff";
  const agencyName = branding?.agency_name || "Jahtaria Travel Services";

  const starterPrompts = isCeo
    ? [
        { label: "Show CEO analytics, approval graph & prediction recall", mode: "chat" as const },
        { label: "Audit C034 and generate visual roadmap png & DS-160 worksheet", mode: "task" as const },
        { label: "Generate follow-up questionnaire for C034", mode: "chat" as const },
        { label: "Open AI subscriptions, ChatGPT Codex, Claude & Voice setup", mode: "chat" as const },
      ]
    : isStaffOrCeo
    ? [
        { label: "Show active client pipeline", mode: "chat" as const },
        { label: "Audit C005 for barcode mismatch & denial risks", mode: "task" as const },
        { label: "Generate follow-up questionnaire for C034", mode: "chat" as const },
        { label: "Open PICA adult passport renewal PDF", mode: "chat" as const },
      ]
    : [
        { label: "Show my case status & Good Standing score", mode: "chat" as const },
        { label: "Generate tailored follow-up questions for my visa profile", mode: "chat" as const },
        { label: "Open my Voice & Text Mock Embassy Interview", mode: "chat" as const },
        { label: "Show my approved documents & visual roadmap", mode: "chat" as const },
      ];

  return (
    <div
      className="h-screen w-screen overflow-hidden bg-[#0d0f13] text-slate-100 flex"
      onDragOver={(e) => {
        if (isStaffOrCeo) {
          e.preventDefault();
          setDragActive(true);
        }
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragActive(false);
        const f = e.dataTransfer.files?.[0];
        if (f && isStaffOrCeo) handleFileUpload(f);
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.png,.jpg,.jpeg"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFileUpload(f);
          e.target.value = "";
        }}
      />

      {/* ── LEFT GRAPHITE SIDEBAR (Clean Conversations + Active Clients Only!) ─ */}
      <aside
        className={`${
          sidebarOpen ? "w-60" : "w-14"
        } h-full bg-[#111318] border-r border-white/10 flex flex-col transition-all duration-200 shrink-0`}
      >
        <div className="h-12 px-3 flex items-center justify-between border-b border-white/5">
          {sidebarOpen ? (
            <div className="flex items-center gap-2 min-w-0">
              <img src={branding?.logo_url || "/jahtaria-logo.png"} alt={agencyName} className="w-6 h-6 rounded-full border border-white/20 object-cover shrink-0" />
              <span className="text-xs font-bold text-slate-100 truncate">{agencyName}</span>
            </div>
          ) : (
            <img
              src={branding?.logo_url || "/jahtaria-logo.png"}
              alt={agencyName}
              className="w-7 h-7 rounded-full border border-white/20 object-cover mx-auto cursor-pointer"
              onClick={() => setSidebarOpen(true)}
            />
          )}
          {sidebarOpen && (
            <button onClick={() => setSidebarOpen(false)} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10">
              <PanelLeft className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="p-2.5">
          <button
            onClick={() => {
              setTurns([]);
              setActiveConvId(null);
              if (isStaffOrCeo) setActiveCaseId(null);
            }}
            className="w-full flex items-center justify-center gap-2 py-2 px-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.11] border border-white/10 text-xs font-medium text-white transition"
          >
            <Plus className="w-4 h-4 shrink-0" />
            {sidebarOpen && <span>New Conversation</span>}
          </button>
        </div>

        <nav className="px-2 space-y-0.5 flex-1 overflow-y-auto">
          {isCeo && (
            <SidebarBtn icon={BarChart3} label="CEO Analytics" open={sidebarOpen} active={rightPanel?.panel === "ceo_analytics"} onClick={() => openPanel({ panel: "ceo_analytics", title: "CEO Executive Analytics & Graphs" })} />
          )}
          {isStaffOrCeo ? (
            <>
              <SidebarBtn icon={Users} label="Clients" open={sidebarOpen} active={rightPanel?.panel === "clients_list"} onClick={() => openPanel({ panel: "clients_list", title: "Client Pipeline" })} />
              <SidebarBtn icon={FileText} label="Official PDFs" open={sidebarOpen} active={rightPanel?.panel === "official_pdfs"} onClick={() => openPanel({ panel: "official_pdfs", title: "Official Government PDF Viewer" })} />
              <SidebarBtn icon={Globe} label="Gov Sources" open={sidebarOpen} active={rightPanel?.panel === "gov_sources"} onClick={() => openPanel({ panel: "gov_sources", title: "Official Scraped Gov Sources" })} />
              <SidebarBtn icon={Database} label="Database" open={sidebarOpen} active={rightPanel?.panel === "database"} onClick={() => openPanel({ panel: "database", table: "clients", title: "Database Explorer" })} />
              <SidebarBtn icon={BookOpen} label="Obsidian Vault" open={sidebarOpen} active={rightPanel?.panel === "obsidian"} onClick={() => openPanel({ panel: "obsidian", path: "Index.md", title: "Obsidian Vault" })} />
              {isCeo && (
                <SidebarBtn icon={UserPlus} label="Team & Staff" open={sidebarOpen} active={rightPanel?.panel === "team"} onClick={() => openPanel({ panel: "team", title: "Team & Staff Accounts" })} />
              )}

              {/* Clean Active Clients Only (33 Historical cases live inside Clients -> Historical) */}
              {sidebarOpen && activeClients.length > 0 && (
                <div className="pt-3 mt-2 border-t border-white/10 px-1 space-y-0.5">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-2 pb-1">
                    Active Clients
                  </div>
                  {activeClients.map((c) => (
                    <button
                      key={c.case_id}
                      onClick={() => {
                        setActiveCaseId(c.case_id);
                        openPanel({ panel: "client", case_id: c.case_id, subview: "overview", title: `${c.case_id} — ${c.full_name}` });
                      }}
                      className={`w-full text-left px-2 py-1.5 rounded-lg text-xs flex items-center justify-between gap-2 transition ${
                        activeCaseId === c.case_id ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                      }`}
                    >
                      <span className="truncate">{c.full_name}</span>
                      <span className="text-[10px] font-mono text-emerald-400 shrink-0">{c.standing_score}%</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <SidebarBtn icon={ShieldCheck} label="My Case Status" open={sidebarOpen} active={rightPanel?.subview === "overview"} onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "overview", title: "My Case Status" })} />
              <SidebarBtn icon={FileText} label="Questionnaire & Form" open={sidebarOpen} active={rightPanel?.subview === "intake"} onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "intake", title: "My Details & Questionnaire" })} />
              <SidebarBtn icon={Sparkles} label="Voice Mock Interview" open={sidebarOpen} active={rightPanel?.subview === "practice"} onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "practice", title: "Voice & Text Mock Interview" })} />
              <SidebarBtn icon={ImageIcon} label="Approved Docs" open={sidebarOpen} active={rightPanel?.subview === "docs"} onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "docs", title: "My Approved Docs & Roadmap" })} />
              <SidebarBtn icon={Globe} label="Official Links" open={sidebarOpen} active={rightPanel?.panel === "gov_sources"} onClick={() => openPanel({ panel: "gov_sources", title: "Official Embassy & PICA Links" })} />
            </>
          )}

          {/* Saved Conversations History (like Antigravity / ChatGPT) */}
          {sidebarOpen && conversations.length > 0 && (
            <div className="pt-3 mt-2 border-t border-white/10 px-1 space-y-0.5">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-2 pb-1">
                Conversations
              </div>
              {conversations.slice(0, 12).map((cv) => (
                <div
                  key={cv.id}
                  className={`group flex items-center justify-between gap-1 px-2 py-1.5 rounded-lg text-xs cursor-pointer transition ${
                    activeConvId === cv.id ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                  }`}
                  onClick={() => loadThread(cv)}
                >
                  <span className="truncate">{cv.title}</span>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      await apiFetch(`/api/conversations/${cv.id}`, { method: "DELETE" });
                      if (activeConvId === cv.id) {
                        setActiveConvId(null);
                        setTurns([]);
                      }
                      loadConversations();
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 text-slate-500 hover:text-red-400"
                    title="Delete thread"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </nav>

        <div className="p-2 border-t border-white/10 space-y-1">
          {isStaffOrCeo && (
            <SidebarBtn icon={Settings} label="AI, Voice & Setup" open={sidebarOpen} active={rightPanel?.panel === "settings"} onClick={() => openPanel({ panel: "settings", title: "AI Subscriptions, Voice & Setup" })} />
          )}
          <div className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-white/[0.03]">
            {sidebarOpen && (
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-200 truncate">{user.full_name}</div>
                <div className="text-[10px] uppercase text-amber-300 font-semibold">{user.role}</div>
              </div>
            )}
            <button onClick={handleLogout} className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 mx-auto" title="Sign Out">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── CENTER CHATBOT-FIRST CANVAS ───────────────────────────────────── */}
      <div className={`flex-1 flex flex-col min-w-0 graphite-ambient relative ${dragActive ? "ring-2 ring-blue-400 ring-inset" : ""}`}>
        {/* Top Bar with Voice Mode Controls & Side Panel Toggle */}
        <header className="h-12 px-4 flex items-center justify-between border-b border-white/5 shrink-0 gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-400 min-w-0">
            {!sidebarOpen && (
              <button onClick={() => setSidebarOpen(true)} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-300">
                <PanelLeft className="w-4 h-4" />
              </button>
            )}
            <span className="font-semibold text-slate-200 truncate">Visa Intelligence Agent</span>
            {activeCaseId && (
              <span className="px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-400/20 font-mono text-[11px] shrink-0">
                {activeCaseId}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Voice Persona + Auto-Speak Toggle (Available to CEO, Staff & Customers!) */}
            <select
              value={voicePersona}
              onChange={(e) => setVoicePersona(e.target.value)}
              className="hidden sm:block bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[11px] text-slate-300 outline-none"
              title="Voice Persona"
            >
              <option value="advisor_ja" className="bg-[#171a21]">Advisor Voice</option>
              <option value="officer_us" className="bg-[#171a21]">U.S. Officer Voice</option>
              <option value="advisor_male" className="bg-[#171a21]">Specialist (Male)</option>
            </select>
            <button
              onClick={() => {
                if (speaking) stopSpeaking();
                setVoiceMode(!voiceMode);
              }}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 transition ${
                voiceMode
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-400/30"
                  : "bg-white/5 text-slate-400 hover:text-white border border-white/10"
              }`}
              title="Toggle Voice Mode (AI speaks replies aloud)"
            >
              {voiceMode ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
              <span className="hidden md:inline">{speaking ? "Speaking…" : voiceMode ? "Voice On" : "Voice"}</span>
            </button>

            <button
              onClick={() =>
                rightPanel
                  ? setRightPanel(null)
                  : openPanel(
                      isCeo
                        ? { panel: "ceo_analytics", title: "CEO Executive Analytics & Graphs" }
                        : isStaffOrCeo
                        ? { panel: "clients_list", title: "Client Pipeline" }
                        : { panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "overview", title: "My Case Status" }
                    )
              }
              className="g-btn-ghost px-2.5 py-1.5 text-xs inline-flex items-center gap-1.5"
            >
              <PanelRight className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{rightPanel ? "Hide Panel" : "Side Panel"}</span>
            </button>
          </div>
        </header>

        {/* Main Chat Area */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
          {turns.length === 0 ? (
            <div className="h-full max-w-2xl mx-auto flex flex-col items-center justify-center gap-7">
              <div className="text-center space-y-2">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-slate-100">
                  Where should we start?
                </h1>
                <p className="text-xs text-slate-400">
                  Type, speak with the mic, or drop a PDF — ask for graphs, client audits, live questionnaires, or official forms.
                </p>
              </div>

              <div className="w-full space-y-3">
                <PromptPill
                  input={input}
                  setInput={setInput}
                  busy={busy}
                  listening={listening}
                  onToggleMic={toggleMic}
                  modelCatalog={modelCatalog}
                  activeProvider={activeProvider}
                  activeModel={activeModel}
                  onSelectModel={handleModelSwitch}
                  showPlusMenu={showPlusMenu}
                  setShowPlusMenu={setShowPlusMenu}
                  isStaffOrCeo={isStaffOrCeo}
                  onAttachClick={() => fileInputRef.current?.click()}
                  onSend={() => sendMessage()}
                  onOpenPanel={openPanel}
                />

                <div className="flex items-center justify-center gap-2">
                  <button
                    onClick={() => setMode("chat")}
                    className={`px-4 py-1.5 rounded-full text-xs font-semibold transition ${
                      mode === "chat" ? "bg-white/15 text-white border border-white/15" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Chat
                  </button>
                  <button
                    onClick={() => setMode("task")}
                    className={`px-4 py-1.5 rounded-full text-xs font-semibold transition ${
                      mode === "task" ? "bg-blue-500/25 text-blue-200 border border-blue-400/30" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Task (Autonomous)
                  </button>
                </div>
              </div>

              <div className="w-full max-w-md space-y-1.5 pt-2">
                {starterPrompts.map((sp) => (
                  <button
                    key={sp.label}
                    onClick={() => sendMessage(sp.label, sp.mode)}
                    className="w-full text-left px-3.5 py-2.5 rounded-xl text-xs text-slate-300 hover:text-white hover:bg-white/[0.06] flex items-center gap-2.5 transition"
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span>{sp.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-2xl mx-auto space-y-5 pb-4">
              {turns.map((t, idx) => (
                <div key={idx} className={`flex flex-col ${t.sender === "user" ? "items-end" : "items-start"}`}>
                  <div
                    className={`max-w-[92%] rounded-2xl px-4 py-3 ${
                      t.sender === "user"
                        ? "bg-[#222735] text-slate-100 border border-white/10 text-sm"
                        : "bg-transparent text-slate-200"
                    }`}
                  >
                    {t.tool_trace && t.tool_trace.length > 0 && (
                      <div className="mb-3 p-2.5 rounded-xl bg-black/40 border border-white/10 font-mono text-[11px] text-emerald-300 space-y-1">
                        {t.tool_trace.map((st) => (
                          <div key={st.step}>
                            [{st.step}] {st.tool} → {st.detail}
                          </div>
                        ))}
                      </div>
                    )}

                    {t.sender === "assistant" ? <RichMarkdown content={t.content} /> : <div>{t.content}</div>}

                    {/* CEO Preview / Confirm & Undo Action Card */}
                    {t.pending_action && (
                      <div className="mt-3 g-card p-3.5 space-y-2.5 border-amber-400/30">
                        <div className="flex items-center justify-between gap-2 text-xs">
                          <span className="font-semibold text-amber-300">Proposed Change ({t.pending_action.status.toUpperCase()})</span>
                          <span className="text-[11px] text-slate-400">{t.pending_action.target_ref}</span>
                        </div>
                        <div className="text-xs text-slate-200">{t.pending_action.summary}</div>
                        <div className="flex gap-2">
                          {t.pending_action.status === "pending" && (
                            <>
                              <button
                                onClick={() => handleActionDecision(idx, t.pending_action!.id, "confirm")}
                                className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold inline-flex items-center gap-1"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5" /> Confirm &amp; Apply
                              </button>
                              <button
                                onClick={() => handleActionDecision(idx, t.pending_action!.id, "cancel")}
                                className="g-btn-ghost px-3 py-1.5 text-xs"
                              >
                                Cancel
                              </button>
                            </>
                          )}
                          {t.pending_action.status === "applied" && (
                            <button
                              onClick={() => handleActionDecision(idx, t.pending_action!.id, "undo")}
                              className="g-btn-ghost px-3 py-1.5 text-xs text-amber-300 inline-flex items-center gap-1"
                            >
                              <RotateCcw className="w-3.5 h-3.5" /> Undo Change
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Action Row: Open Panel + Speak Aloud */}
                    {t.sender === "assistant" && (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {t.panel && (
                          <button
                            onClick={() => openPanel(t.panel!)}
                            className="px-3 py-1.5 rounded-xl bg-blue-500/15 hover:bg-blue-500/25 border border-blue-400/30 text-xs font-medium text-blue-200 inline-flex items-center gap-1.5 transition"
                          >
                            <PanelRight className="w-3.5 h-3.5" /> Open {t.panel.title || "Side Panel"}
                          </button>
                        )}
                        <button
                          onClick={() => speakText(t.content)}
                          className="px-2.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-[11px] text-slate-400 hover:text-white inline-flex items-center gap-1 transition"
                          title="Read aloud"
                        >
                          <Volume2 className="w-3 h-3" /> Speak
                        </button>
                      </div>
                    )}

                    {t.created_assets && t.created_assets.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {t.created_assets.map((a) => (
                          <div key={a.id} className="g-card p-2.5 flex items-center justify-between gap-2 text-xs">
                            <span className="truncate text-slate-200">{a.title}</span>
                            <button
                              onClick={() =>
                                openPanel({
                                  panel: "client",
                                  case_id: activeCaseId || "C034",
                                  subview: "blueprints",
                                  preview_asset_id: a.id,
                                  title: a.title,
                                })
                              }
                              className="px-2.5 py-1 rounded-lg bg-emerald-600 text-white text-[11px] font-semibold shrink-0"
                            >
                              Preview &amp; Approve
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {t.citations && t.citations.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {t.citations.map((c, ci) => (
                          <a
                            key={ci}
                            href={c.url}
                            target="_blank"
                            rel="noreferrer"
                            className="px-2.5 py-1 rounded-full bg-white/5 hover:bg-white/10 text-[11px] text-slate-300 inline-flex items-center gap-1"
                          >
                            {c.agency} <ExternalLink className="w-2.5 h-2.5" />
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {busy && <div className="text-xs text-slate-400 animate-pulse px-4">Thinking &amp; running tools…</div>}
            </div>
          )}
        </div>

        {/* Sticky Bottom Prompt Bar */}
        {turns.length > 0 && (
          <div className="px-4 sm:px-8 pb-4 pt-2 shrink-0">
            <div className="max-w-2xl mx-auto space-y-2">
              <PromptPill
                input={input}
                setInput={setInput}
                busy={busy}
                listening={listening}
                onToggleMic={toggleMic}
                modelCatalog={modelCatalog}
                activeProvider={activeProvider}
                activeModel={activeModel}
                onSelectModel={handleModelSwitch}
                showPlusMenu={showPlusMenu}
                setShowPlusMenu={setShowPlusMenu}
                isStaffOrCeo={isStaffOrCeo}
                onAttachClick={() => fileInputRef.current?.click()}
                onSend={() => sendMessage()}
                onOpenPanel={openPanel}
              />
              <div className="flex items-center justify-between text-[11px] text-slate-500 px-2">
                <div className="flex gap-2">
                  <button onClick={() => setMode("chat")} className={mode === "chat" ? "text-slate-200 font-semibold" : "hover:text-slate-300"}>
                    Chat
                  </button>
                  <span>•</span>
                  <button onClick={() => setMode("task")} className={mode === "task" ? "text-blue-300 font-semibold" : "hover:text-slate-300"}>
                    Task Mode
                  </button>
                </div>
                <span>Drag &amp; drop PDFs/images into chat • Truthful visa prep only</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── RIGHT COLLAPSIBLE ARTIFACT SIDE PANEL ─────────────────────────── */}
      {rightPanel && (
        <RightSidePanel
          request={rightPanel}
          user={user}
          branding={branding}
          recentLinks={recentPanels}
          refreshNonce={panelRefreshNonce}
          onNavigatePanel={openPanel}
          onSelectCaseForChat={(cid) => setActiveCaseId(cid)}
          onBrandingUpdated={(b) => {
            setBranding(b);
            loadModelCatalog();
          }}
          onClose={() => {
            setRightPanel(null);
            loadModelCatalog();
          }}
        />
      )}
    </div>
  );
}

function SidebarBtn({ icon: Icon, label, open, active, onClick }: { icon: any; label: string; open: boolean; active?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={`w-full flex items-center ${open ? "gap-2.5 px-2.5" : "justify-center"} py-2 rounded-xl text-xs font-medium transition ${
        active ? "bg-white/12 text-white" : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.06]"
      }`}
    >
      <Icon className="w-4 h-4 shrink-0" />
      {open && <span className="truncate">{label}</span>}
    </button>
  );
}

function PromptPill({
  input,
  setInput,
  busy,
  listening,
  onToggleMic,
  modelCatalog,
  activeProvider,
  activeModel,
  onSelectModel,
  showPlusMenu,
  setShowPlusMenu,
  isStaffOrCeo,
  onAttachClick,
  onSend,
  onOpenPanel,
}: {
  input: string;
  setInput: (s: string) => void;
  busy: boolean;
  listening: boolean;
  onToggleMic: () => void;
  modelCatalog: any;
  activeProvider: string;
  activeModel: string;
  onSelectModel: (val: string) => void;
  showPlusMenu: boolean;
  setShowPlusMenu: (b: boolean) => void;
  isStaffOrCeo: boolean;
  onAttachClick: () => void;
  onSend: () => void;
  onOpenPanel: (req: PanelRequest) => void;
}) {
  return (
    <div className="relative">
      {showPlusMenu && isStaffOrCeo && (
        <div className="absolute bottom-14 left-0 z-30 w-60 g-card p-1.5 shadow-2xl space-y-0.5 text-xs">
          <button
            onClick={() => {
              setShowPlusMenu(false);
              onAttachClick();
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/10 text-slate-200 flex items-center gap-2"
          >
            <Paperclip className="w-3.5 h-3.5" /> Attach PDF / DOCX / Image
          </button>
          <button
            onClick={() => {
              setShowPlusMenu(false);
              onOpenPanel({ panel: "clients_list", title: "Client Pipeline" });
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/10 text-slate-200"
          >
            + New Client Case
          </button>
          <button
            onClick={() => {
              setShowPlusMenu(false);
              onOpenPanel({ panel: "settings", title: "AI Subscriptions, Voice & Setup" });
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/10 text-slate-200"
          >
            + Connect ChatGPT / Claude / Voice
          </button>
        </div>
      )}

      <div className="flex items-center gap-1.5 bg-[#1a1d24] border border-white/12 rounded-full px-3 py-2 shadow-xl focus-within:border-blue-400/50 transition overflow-hidden">
        {isStaffOrCeo && (
          <button
            type="button"
            onClick={() => setShowPlusMenu(!showPlusMenu)}
            className="p-1.5 rounded-full text-slate-400 hover:text-white hover:bg-white/10 transition shrink-0"
            title="Attach or Quick Actions"
          >
            <Plus className="w-4 h-4" />
          </button>
        )}

        <input
          className="flex-1 min-w-0 bg-transparent border-0 outline-none text-sm text-slate-100 placeholder:text-slate-500 px-1"
          placeholder={listening ? "Listening… speak now" : "Ask Visa Agent or type a command..."}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSend()}
        />

        {/* Grouped Model Picker (Subscriptions / Local / API Keys) */}
        <div className="hidden sm:flex items-center relative max-w-[148px] shrink-0">
          <select
            value={`${activeProvider}::${activeModel}`}
            onChange={(e) => onSelectModel(e.target.value)}
            className="appearance-none bg-transparent text-xs text-slate-300 hover:text-white pr-5 pl-1.5 py-1 outline-none cursor-pointer truncate max-w-[148px]"
          >
            {(modelCatalog?.groups || []).map((g: any) => (
              <optgroup key={g.group} label={g.group} className="bg-[#111318] text-slate-400">
                {g.items.map((item: any) =>
                  item.models.slice(0, 2).map((m: string) => (
                    <option key={`${item.provider}::${m}`} value={`${item.provider}::${m}`} className="bg-[#171a21] text-slate-100">
                      {item.connected ? "● " : "○ "}
                      {item.label.split(" ")[0]} · {m}
                    </option>
                  ))
                )}
              </optgroup>
            ))}
            {!modelCatalog && <option value="auto::consular-auto">● Consular Auto</option>}
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-slate-500 pointer-events-none -ml-4 shrink-0" />
        </div>

        {/* Live Voice Mic Button */}
        <button
          type="button"
          onClick={onToggleMic}
          className={`p-2 rounded-full transition shrink-0 ${
            listening ? "bg-red-500 text-white animate-pulse" : "text-slate-400 hover:text-white hover:bg-white/10"
          }`}
          title={listening ? "Stop Listening" : "Speak with Microphone"}
        >
          {listening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
        </button>

        <button
          type="button"
          onClick={onSend}
          disabled={busy || !input.trim()}
          className="p-2 rounded-full bg-white/10 hover:bg-blue-600 text-white disabled:opacity-40 transition shrink-0"
          title="Send"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
