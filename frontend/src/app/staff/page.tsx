"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Users,
  Database,
  BookOpen,
  Settings,
  Plus,
  Search,
  LayoutGrid,
  List,
  X,
} from "lucide-react";
import { apiFetch, getStoredUser } from "@/lib/api";
import type { BrandingConfig, ClientSummary, UserAccount } from "@/lib/types";
import { AppShell } from "@/components/AppShell";
import { ClientWorkspace } from "@/components/ClientWorkspace";
import { DatabaseExplorer } from "@/components/DatabaseExplorer";
import { ObsidianVaultView } from "@/components/ObsidianVaultView";
import { EasySetupHub } from "@/components/EasySetupHub";

const PIPELINE_COLS = [
  { id: "new_intake", label: "New Intake" },
  { id: "risk_audit", label: "Rule & Risk Audit" },
  { id: "questionnaire", label: "Questionnaire" },
  { id: "review_approval", label: "Review & Approval" },
  { id: "docs_ready", label: "Docs Ready" },
  { id: "completed", label: "Completed" },
];

export default function StaffDashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [branding, setBranding] = useState<BrandingConfig | null>(null);
  const [section, setSection] = useState<"pipeline" | "database" | "obsidian" | "setup">("pipeline");
  const [viewMode, setViewMode] = useState<"table" | "kanban">("table");
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [search, setSearch] = useState("");
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  // New Client Modal
  const [showNewModal, setShowNewModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newParish, setNewParish] = useState("St. Andrew");
  const [newVisa, setNewVisa] = useState("B1/B2");
  const [newPurpose, setNewPurpose] = useState("");
  const [newDest, setNewDest] = useState("");

  const loadClients = async (q = "") => {
    const data = await apiFetch<ClientSummary[]>(`/api/clients${q ? `?search=${encodeURIComponent(q)}` : ""}`);
    setClients(data);
  };

  useEffect(() => {
    const u = getStoredUser<UserAccount>();
    if (!u) {
      router.replace("/login");
      return;
    }
    if (u.role === "customer") {
      router.replace("/portal");
      return;
    }
    setUser(u);
    fetch("/api/branding").then((r) => r.json()).then(setBranding).catch(() => {});
    loadClients().catch(() => {});
  }, [router]);

  useEffect(() => {
    if (user) {
      loadClients(search).catch(() => {});
    }
  }, [search, user]);

  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault();
    const created = await apiFetch<{ case_id: string }>("/api/clients", {
      method: "POST",
      body: JSON.stringify({
        full_name: newName,
        email: newEmail,
        phone: newPhone,
        parish: newParish,
        visa_class: newVisa,
        purpose_of_trip: newPurpose,
        us_destination: newDest,
      }),
    });
    setShowNewModal(false);
    setNewName("");
    setNewEmail("");
    setNewPhone("");
    setNewPurpose("");
    setNewDest("");
    await loadClients(search);
    setSelectedCaseId(created.case_id);
  };

  if (!user) return null;

  return (
    <AppShell user={user} branding={branding} activePortal="staff">
      <div className="space-y-5">
        {/* Top Staff Section Nav */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1.5 bg-white p-1.5 rounded-2xl border border-slate-200 shadow-sm">
            {[
              { id: "pipeline", label: `Client Pipeline (${clients.length})`, icon: Users },
              { id: "database", label: "Database, PDFs & Gov Sources", icon: Database },
              { id: "obsidian", label: "Obsidian Vault", icon: BookOpen },
              { id: "setup", label: "Easy Setup & MCP", icon: Settings },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setSection(item.id as typeof section);
                    if (item.id !== "pipeline") setSelectedCaseId(null);
                  }}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition ${
                    section === item.id ? "bg-ja-green text-ja-goldBright shadow" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  <Icon className="w-4 h-4" /> {item.label}
                </button>
              );
            })}
          </div>

          {section === "pipeline" && !selectedCaseId && (
            <button onClick={() => setShowNewModal(true)} className="ja-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5">
              <Plus className="w-4 h-4" /> New Client Case
            </button>
          )}
        </div>

        {/* SECTION 1: CLIENT PIPELINE OR WORKSPACE */}
        {section === "pipeline" &&
          (selectedCaseId ? (
            <ClientWorkspace
              caseId={selectedCaseId}
              onBack={() => setSelectedCaseId(null)}
              onUpdated={() => loadClients(search)}
            />
          ) : (
            <div className="space-y-4">
              <div className="ja-card p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="relative flex-1 min-w-[240px]">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    className="ja-input pl-9 text-xs"
                    placeholder="Search by Case ID (C034, C001, C005), client name, visa class, or profile tag..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
                  <button
                    onClick={() => setViewMode("table")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1 ${
                      viewMode === "table" ? "bg-white text-ja-green shadow" : "text-slate-600"
                    }`}
                  >
                    <List className="w-3.5 h-3.5" /> Table
                  </button>
                  <button
                    onClick={() => setViewMode("kanban")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1 ${
                      viewMode === "kanban" ? "bg-white text-ja-green shadow" : "text-slate-600"
                    }`}
                  >
                    <LayoutGrid className="w-3.5 h-3.5" /> Kanban
                  </button>
                </div>
              </div>

              {viewMode === "table" ? (
                <div className="ja-card overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead className="bg-ja-green text-white">
                        <tr>
                          <th className="px-4 py-3 font-bold">Case ID</th>
                          <th className="px-4 py-3 font-bold">Client Name</th>
                          <th className="px-4 py-3 font-bold">Visa</th>
                          <th className="px-4 py-3 font-bold">Pipeline Stage</th>
                          <th className="px-4 py-3 font-bold">Good Standing Bar</th>
                          <th className="px-4 py-3 font-bold">Outcome</th>
                          <th className="px-4 py-3 font-bold">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 bg-white">
                        {clients.map((c) => {
                          const barColor =
                            c.standing_score >= 80
                              ? "bg-emerald-600"
                              : c.standing_score >= 60
                              ? "bg-amber-500"
                              : "bg-ja-red";
                          return (
                            <tr
                              key={c.case_id}
                              onClick={() => setSelectedCaseId(c.case_id)}
                              className="hover:bg-ja-greenLight/50 cursor-pointer transition"
                            >
                              <td className="px-4 py-3 font-extrabold text-ja-green">{c.case_id}</td>
                              <td className="px-4 py-3">
                                <div className="font-bold text-slate-900">{c.full_name || c.pseudonym}</div>
                                <div className="text-[11px] text-slate-500">{c.profile_tags.slice(0, 3).join(" • ")}</div>
                              </td>
                              <td className="px-4 py-3 font-bold text-ja-navy">{c.visa_class}</td>
                              <td className="px-4 py-3">
                                <span className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 font-bold text-[11px]">
                                  {c.pipeline_stage.replace(/_/g, " ")}
                                </span>
                              </td>
                              <td className="px-4 py-3 min-w-[160px]">
                                <div className="flex items-center gap-2">
                                  <div className="flex-1 h-2.5 rounded-full bg-slate-200 overflow-hidden">
                                    <div className={`h-full ${barColor}`} style={{ width: `${c.standing_score}%` }} />
                                  </div>
                                  <span className="font-extrabold w-9 text-right">{c.standing_score}%</span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <span
                                  className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase ${
                                    c.outcome === "approved"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : c.outcome === "refused"
                                      ? "bg-red-100 text-red-800"
                                      : "bg-slate-100 text-slate-600"
                                  }`}
                                >
                                  {c.outcome}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                <button className="px-3 py-1 rounded-lg bg-ja-green text-ja-goldBright font-bold text-[11px]">
                                  Open Case
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  {PIPELINE_COLS.map((col) => {
                    const colItems = clients.filter((c) => c.pipeline_stage === col.id);
                    return (
                      <div key={col.id} className="ja-card p-3 space-y-2.5 bg-slate-50/80">
                        <div className="flex items-center justify-between border-b pb-2">
                          <span className="text-xs font-extrabold text-ja-green">{col.label}</span>
                          <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-ja-greenLight text-ja-green">
                            {colItems.length}
                          </span>
                        </div>
                        <div className="space-y-2 max-h-[540px] overflow-y-auto">
                          {colItems.map((c) => (
                            <div
                              key={c.case_id}
                              onClick={() => setSelectedCaseId(c.case_id)}
                              className="p-3 rounded-xl bg-white border border-slate-200 hover:border-ja-green cursor-pointer shadow-sm space-y-1.5"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-[11px] font-extrabold text-ja-green">{c.case_id}</span>
                                <span className="text-[11px] font-bold text-ja-navy">{c.standing_score}%</span>
                              </div>
                              <div className="font-bold text-xs text-slate-900 truncate">{c.full_name || c.pseudonym}</div>
                              <div className="w-full h-1.5 rounded-full bg-slate-200 overflow-hidden">
                                <div
                                  className={`h-full ${c.standing_score >= 80 ? "bg-emerald-600" : c.standing_score >= 60 ? "bg-amber-500" : "bg-ja-red"}`}
                                  style={{ width: `${c.standing_score}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

        {section === "database" && <DatabaseExplorer />}
        {section === "obsidian" && <ObsidianVaultView />}
        {section === "setup" && <EasySetupHub isCeo={user.role === "ceo"} branding={branding} onBrandingUpdated={setBranding} />}
      </div>

      {/* New Client Modal */}
      {showNewModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <form onSubmit={handleCreateClient} className="ja-card max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-extrabold text-base text-ja-green">Create New U.S. Visa Client Case</h3>
              <button type="button" onClick={() => setShowNewModal(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Full Name *</label>
                <input className="ja-input text-xs" required value={newName} onChange={(e) => setNewName(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Visa Class</label>
                <select className="ja-input text-xs" value={newVisa} onChange={(e) => setNewVisa(e.target.value)}>
                  <option value="B1/B2">B1/B2 Visitor</option>
                  <option value="F1">F-1 Student</option>
                  <option value="H-2B">H-2B Worker</option>
                  <option value="J1">J-1 Exchange</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Email</label>
                <input className="ja-input text-xs" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Phone / WhatsApp</label>
                <input className="ja-input text-xs" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Parish</label>
                <input className="ja-input text-xs" value={newParish} onChange={(e) => setNewParish(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">U.S. Destination</label>
                <input className="ja-input text-xs" value={newDest} onChange={(e) => setNewDest(e.target.value)} placeholder="e.g. Miami, FL" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Purpose of Trip</label>
              <input className="ja-input text-xs" value={newPurpose} onChange={(e) => setNewPurpose(e.target.value)} placeholder="Tourism / Family visit / Conference" />
            </div>
            <button type="submit" className="ja-btn-primary w-full py-2.5 text-xs">
              Create Case, Run Initial Audit &amp; Sync Obsidian
            </button>
          </form>
        </div>
      )}
    </AppShell>
  );
}
