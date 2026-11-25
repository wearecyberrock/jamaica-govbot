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
} from "lucide-react";
import { apiFetch, clearAuthSession, getStoredUser } from "@/lib/api";
import type { BrandingConfig, ClientSummary, UserAccount } from "@/lib/types";
import { RightSidePanel, type PanelRequest } from "./RightSidePanel";

interface ChatTurn {
  sender: "user" | "assistant";
  content: string;
  provider_used?: string;
  tool_trace?: Array<{ step: number; tool: string; status: string; detail: string }>;
  citations?: Array<{ name: string; agency: string; url: string }>;
  created_assets?: Array<{ id: number; title: string; mime_type: string; file_url: string }>;
  panel?: PanelRequest | null;
}

export function AgentWorkspace({ requiredRole }: { requiredRole?: "ceo" | "staff" | "customer" }) {
  const router = useRouter();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [branding, setBranding] = useState<BrandingConfig | null>(null);

  // Left sidebar & Right side panel state
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightPanel, setRightPanel] = useState<PanelRequest | null>(null);
  const [recentPanels, setRecentPanels] = useState<PanelRequest[]>([]);

  // Active client cases in sidebar (Staff/CEO)
  const [sidebarCases, setSidebarCases] = useState<ClientSummary[]>([]);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);

  // Chatbot state
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"chat" | "task">("chat");
  const [selectedModel, setSelectedModel] = useState("Hermes Auto");
  const [busy, setBusy] = useState(false);

  // Compact `+` quick action popup menu
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

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
    }

    fetch("/api/branding").then((r) => r.json()).then(setBranding).catch(() => {});

    if (u.role === "ceo" || u.role === "staff") {
      apiFetch<ClientSummary[]>("/api/clients")
        .then((list) => setSidebarCases(list.slice(0, 10)))
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
        reply: string;
        provider_used: string;
        tool_trace: Array<{ step: number; tool: string; status: string; detail: string }>;
        citations: Array<{ name: string; agency: string; url: string }>;
        created_assets: Array<{ id: number; title: string; mime_type: string; file_url: string }>;
        ui_panel: PanelRequest | null;
      }>("/api/agent/command", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          mode: activeMode,
          case_id: activeCaseId,
        }),
      });

      if (res.ui_panel) {
        openPanel(res.ui_panel);
        if (res.ui_panel.case_id) setActiveCaseId(res.ui_panel.case_id);
      }

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
        },
      ]);
    } catch (err: unknown) {
      setTurns((prev) => [
        ...prev,
        { sender: "assistant", content: `Error: ${err instanceof Error ? err.message : "Request failed"}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = async () => {
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
        { label: "Open PICA adult passport renewal PDF", mode: "chat" as const },
        { label: "Create a new staff account", mode: "chat" as const },
      ]
    : isStaffOrCeo
    ? [
        { label: "Show active client pipeline", mode: "chat" as const },
        { label: "Audit C005 for barcode mismatch & denial risks", mode: "task" as const },
        { label: "Generate visual roadmap png for C034", mode: "task" as const },
        { label: "Open PICA passport application PDF & official gov links", mode: "chat" as const },
      ]
    : [
        { label: "Show my case status & Good Standing score", mode: "chat" as const },
        { label: "Explain the April 1, 2025 DS-160 barcode rule & MRV fees", mode: "chat" as const },
        { label: "Open my practice mock interview questions", mode: "chat" as const },
        { label: "Show my approved documents & visual roadmap", mode: "chat" as const },
      ];

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#0d0f13] text-slate-100 flex">
      {/* ── LEFT GRAPHITE SIDEBAR (Collapsible like Antigravity / Gemini) ─── */}
      <aside
        className={`${
          sidebarOpen ? "w-60" : "w-14"
        } h-full bg-[#111318] border-r border-white/10 flex flex-col transition-all duration-200 shrink-0`}
      >
        {/* Top Logo + Toggle */}
        <div className="h-12 px-3 flex items-center justify-between border-b border-white/5">
          {sidebarOpen ? (
            <div className="flex items-center gap-2 min-w-0">
              <img
                src={branding?.logo_url || "/jahtaria-logo.png"}
                alt={agencyName}
                className="w-6 h-6 rounded-full border border-white/20 object-cover shrink-0"
              />
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
            <button
              onClick={() => setSidebarOpen(false)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10"
              title="Collapse Sidebar"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* + New Conversation */}
        <div className="p-2.5">
          <button
            onClick={() => {
              setTurns([]);
              if (isStaffOrCeo) setActiveCaseId(null);
            }}
            className="w-full flex items-center justify-center gap-2 py-2 px-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.11] border border-white/10 text-xs font-medium text-white transition"
            title="New Conversation"
          >
            <Plus className="w-4 h-4 shrink-0" />
            {sidebarOpen && <span>New Conversation</span>}
          </button>
        </div>

        {/* Compact Icon Menu */}
        <nav className="px-2 space-y-0.5 flex-1 overflow-y-auto">
          {isCeo && (
            <SidebarBtn
              icon={BarChart3}
              label="CEO Analytics"
              open={sidebarOpen}
              active={rightPanel?.panel === "ceo_analytics"}
              onClick={() => openPanel({ panel: "ceo_analytics", title: "CEO Executive Analytics & Graphs" })}
            />
          )}
          {isStaffOrCeo ? (
            <>
              <SidebarBtn
                icon={Users}
                label="Clients"
                open={sidebarOpen}
                active={rightPanel?.panel === "clients_list"}
                onClick={() => openPanel({ panel: "clients_list", title: "Client Pipeline" })}
              />
              <SidebarBtn
                icon={FileText}
                label="Official PDFs"
                open={sidebarOpen}
                active={rightPanel?.panel === "official_pdfs"}
                onClick={() => openPanel({ panel: "official_pdfs", title: "Official Government PDF Viewer" })}
              />
              <SidebarBtn
                icon={Globe}
                label="Gov Sources"
                open={sidebarOpen}
                active={rightPanel?.panel === "gov_sources"}
                onClick={() => openPanel({ panel: "gov_sources", title: "Official Scraped Gov Sources" })}
              />
              <SidebarBtn
                icon={Database}
                label="Database"
                open={sidebarOpen}
                active={rightPanel?.panel === "database"}
                onClick={() => openPanel({ panel: "database", table: "clients", title: "Database Explorer" })}
              />
              <SidebarBtn
                icon={BookOpen}
                label="Obsidian Vault"
                open={sidebarOpen}
                active={rightPanel?.panel === "obsidian"}
                onClick={() => openPanel({ panel: "obsidian", path: "Index.md", title: "Obsidian Vault" })}
              />
              {isCeo && (
                <SidebarBtn
                  icon={UserPlus}
                  label="Team & Staff"
                  open={sidebarOpen}
                  active={rightPanel?.panel === "team"}
                  onClick={() => openPanel({ panel: "team", title: "Team & Staff Accounts" })}
                />
              )}

              {/* Quick Recent Cases List inside Sidebar (like Antigravity's Projects list) */}
              {sidebarOpen && sidebarCases.length > 0 && (
                <div className="pt-4 mt-3 border-t border-white/10 px-1 space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-2 pb-1">
                    Cases
                  </div>
                  {sidebarCases.slice(0, 7).map((c) => (
                    <button
                      key={c.case_id}
                      onClick={() => {
                        setActiveCaseId(c.case_id);
                        openPanel({ panel: "client", case_id: c.case_id, subview: "overview", title: `${c.case_id} — ${c.full_name || c.pseudonym}` });
                      }}
                      className={`w-full text-left px-2 py-1.5 rounded-lg text-xs flex items-center justify-between gap-2 transition ${
                        activeCaseId === c.case_id ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                      }`}
                    >
                      <span className="truncate">{c.full_name || c.case_id}</span>
                      <span className="text-[10px] font-mono text-emerald-400 shrink-0">{c.standing_score}%</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <SidebarBtn
                icon={ShieldCheck}
                label="My Case Status"
                open={sidebarOpen}
                active={rightPanel?.subview === "overview"}
                onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "overview", title: "My Case Status" })}
              />
              <SidebarBtn
                icon={FileText}
                label="My Details & Form"
                open={sidebarOpen}
                active={rightPanel?.subview === "intake"}
                onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "intake", title: "My Details & Form" })}
              />
              <SidebarBtn
                icon={Sparkles}
                label="Mock Interview"
                open={sidebarOpen}
                active={rightPanel?.subview === "practice"}
                onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "practice", title: "Practice Mock Interview" })}
              />
              <SidebarBtn
                icon={ImageIcon}
                label="Approved Docs"
                open={sidebarOpen}
                active={rightPanel?.subview === "docs"}
                onClick={() => openPanel({ panel: "customer_case", case_id: user.linked_case_id || "C034", subview: "docs", title: "My Approved Docs & Roadmap" })}
              />
              <SidebarBtn
                icon={Globe}
                label="Official Links"
                open={sidebarOpen}
                active={rightPanel?.panel === "gov_sources"}
                onClick={() => openPanel({ panel: "gov_sources", title: "Official Embassy & PICA Links" })}
              />
            </>
          )}
        </nav>

        {/* Bottom Settings + User Account */}
        <div className="p-2 border-t border-white/10 space-y-1">
          {isStaffOrCeo && (
            <SidebarBtn
              icon={Settings}
              label="Settings & Setup"
              open={sidebarOpen}
              active={rightPanel?.panel === "settings"}
              onClick={() => openPanel({ panel: "settings", title: "Easy Setup, AI & MCP" })}
            />
          )}
          <div className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-white/[0.03]">
            {sidebarOpen && (
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-200 truncate">{user.full_name}</div>
                <div className="text-[10px] uppercase text-amber-300 font-semibold">{user.role}</div>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 mx-auto"
              title="Sign Out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── CENTER CHATBOT-FIRST CANVAS ───────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 graphite-ambient">
        {/* Minimal Top Header */}
        <header className="h-12 px-4 flex items-center justify-between border-b border-white/5 shrink-0">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {!sidebarOpen && (
              <button onClick={() => setSidebarOpen(true)} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-300">
                <PanelLeft className="w-4 h-4" />
              </button>
            )}
            <span className="font-semibold text-slate-200">Visa Intelligence Agent</span>
            {activeCaseId && (
              <span className="px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-400/20 font-mono text-[11px]">
                Active: {activeCaseId}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
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
              title="Toggle Right Inspector Panel"
            >
              <PanelRight className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{rightPanel ? "Hide Panel" : "Side Panel"}</span>
            </button>
          </div>
        </header>

        {/* Main Chat Area */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
          {turns.length === 0 ? (
            /* Clean Empty State — "Where should we start?" just like image.png */
            <div className="h-full max-w-2xl mx-auto flex flex-col items-center justify-center gap-7">
              <div className="text-center space-y-2">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-slate-100">
                  Where should we start?
                </h1>
                <p className="text-xs text-slate-400">
                  Ask anything — type to inspect clients, view graphs, audit denial risks, open PICA PDFs, or generate visual roadmaps.
                </p>
              </div>

              {/* Centered Pill Prompt Input */}
              <div className="w-full space-y-3">
                <PromptPill
                  input={input}
                  setInput={setInput}
                  busy={busy}
                  selectedModel={selectedModel}
                  setSelectedModel={setSelectedModel}
                  showPlusMenu={showPlusMenu}
                  setShowPlusMenu={setShowPlusMenu}
                  isStaffOrCeo={isStaffOrCeo}
                  onSend={() => sendMessage()}
                  onOpenPanel={openPanel}
                />

                {/* Chat | Task Pill Switcher */}
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
                    Task (Hermes Agent)
                  </button>
                </div>
              </div>

              {/* Minimal Starter Suggestions */}
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
            /* Active Chat Conversation */
            <div className="max-w-2xl mx-auto space-y-5 pb-4">
              {turns.map((t, idx) => (
                <div key={idx} className={`flex flex-col ${t.sender === "user" ? "items-end" : "items-start"}`}>
                  <div
                    className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      t.sender === "user"
                        ? "bg-[#222735] text-slate-100 border border-white/10"
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

                    <div className="whitespace-pre-wrap">{t.content}</div>

                    {/* Clickable Artifact / Side-Panel Chip */}
                    {t.panel && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          onClick={() => openPanel(t.panel!)}
                          className="px-3 py-1.5 rounded-xl bg-blue-500/15 hover:bg-blue-500/25 border border-blue-400/30 text-xs font-medium text-blue-200 inline-flex items-center gap-1.5 transition"
                        >
                          <PanelRight className="w-3.5 h-3.5" /> Open {t.panel.title || "Side Panel"}
                        </button>
                      </div>
                    )}

                    {/* Inline Generated Visual / PDF Chips */}
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

                    {/* Official Citations */}
                    {t.citations && t.citations.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
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

        {/* Sticky Bottom Prompt Bar (when in active conversation) */}
        {turns.length > 0 && (
          <div className="px-4 sm:px-8 pb-4 pt-2 shrink-0">
            <div className="max-w-2xl mx-auto space-y-2">
              <PromptPill
                input={input}
                setInput={setInput}
                busy={busy}
                selectedModel={selectedModel}
                setSelectedModel={setSelectedModel}
                showPlusMenu={showPlusMenu}
                setShowPlusMenu={setShowPlusMenu}
                isStaffOrCeo={isStaffOrCeo}
                onSend={() => sendMessage()}
                onOpenPanel={openPanel}
              />
              <div className="flex items-center justify-between text-[11px] text-slate-500 px-2">
                <div className="flex gap-2">
                  <button
                    onClick={() => setMode("chat")}
                    className={mode === "chat" ? "text-slate-200 font-semibold" : "hover:text-slate-300"}
                  >
                    Chat
                  </button>
                  <span>•</span>
                  <button
                    onClick={() => setMode("task")}
                    className={mode === "task" ? "text-blue-300 font-semibold" : "hover:text-slate-300"}
                  >
                    Task Mode
                  </button>
                </div>
                <span>Truthful U.S. visa preparation only</span>
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
          onNavigatePanel={openPanel}
          onSelectCaseForChat={(cid) => setActiveCaseId(cid)}
          onBrandingUpdated={setBranding}
          onClose={() => setRightPanel(null)}
        />
      )}
    </div>
  );
}

function SidebarBtn({
  icon: Icon,
  label,
  open,
  active,
  onClick,
}: {
  icon: any;
  label: string;
  open: boolean;
  active?: boolean;
  onClick: () => void;
}) {
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
  selectedModel,
  setSelectedModel,
  showPlusMenu,
  setShowPlusMenu,
  isStaffOrCeo,
  onSend,
  onOpenPanel,
}: {
  input: string;
  setInput: (s: string) => void;
  busy: boolean;
  selectedModel: string;
  setSelectedModel: (s: string) => void;
  showPlusMenu: boolean;
  setShowPlusMenu: (b: boolean) => void;
  isStaffOrCeo: boolean;
  onSend: () => void;
  onOpenPanel: (req: PanelRequest) => void;
}) {
  return (
    <div className="relative">
      {showPlusMenu && isStaffOrCeo && (
        <div className="absolute bottom-14 left-0 z-30 w-56 g-card p-1.5 shadow-2xl space-y-0.5 text-xs">
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
              onOpenPanel({ panel: "official_pdfs", title: "Official PDFs & Blueprints" });
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/10 text-slate-200"
          >
            + Upload PDF / DOCX Blueprint
          </button>
          <button
            onClick={() => {
              setShowPlusMenu(false);
              onOpenPanel({ panel: "database", table: "clients", title: "Database Explorer" });
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/10 text-slate-200"
          >
            + Browse Database Tables
          </button>
        </div>
      )}

      <div className="flex items-center gap-2 bg-[#1a1d24] border border-white/12 rounded-full px-3 py-2 shadow-xl focus-within:border-blue-400/50 transition">
        {isStaffOrCeo && (
          <button
            type="button"
            onClick={() => setShowPlusMenu(!showPlusMenu)}
            className="p-1.5 rounded-full text-slate-400 hover:text-white hover:bg-white/10 transition"
            title="Quick Actions"
          >
            <Plus className="w-4 h-4" />
          </button>
        )}

        <input
          className="flex-1 bg-transparent border-0 outline-none text-sm text-slate-100 placeholder:text-slate-500 px-1"
          placeholder="Ask Visa Agent or type a command..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSend()}
        />

        <div className="hidden sm:flex items-center relative">
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="appearance-none bg-transparent text-xs text-slate-400 hover:text-slate-200 pr-5 pl-2 py-1 outline-none cursor-pointer"
          >
            <option value="Hermes Auto" className="bg-[#171a21]">Hermes Auto</option>
            <option value="Antigravity" className="bg-[#171a21]">Antigravity</option>
            <option value="Ollama Local" className="bg-[#171a21]">Ollama Local</option>
            <option value="Claude" className="bg-[#171a21]">Claude</option>
            <option value="ChatGPT" className="bg-[#171a21]">ChatGPT</option>
            <option value="Grok" className="bg-[#171a21]">Grok</option>
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-slate-500 pointer-events-none -ml-4" />
        </div>

        <button
          type="button"
          onClick={onSend}
          disabled={busy || !input.trim()}
          className="p-2 rounded-full bg-white/10 hover:bg-blue-600 text-white disabled:opacity-40 transition"
          title="Send"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
