"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Crown,
  BarChart3,
  Database,
  BookOpen,
  Settings,
  Users,
  ShieldAlert,
  TrendingUp,
  CheckCircle2,
  DollarSign,
  FileCheck,
  UserPlus,
} from "lucide-react";
import { apiFetch, getStoredUser } from "@/lib/api";
import type { BrandingConfig, UserAccount } from "@/lib/types";
import { AppShell } from "@/components/AppShell";
import { DatabaseExplorer } from "@/components/DatabaseExplorer";
import { ObsidianVaultView } from "@/components/ObsidianVaultView";
import { EasySetupHub } from "@/components/EasySetupHub";

interface CeoOverview {
  kpis: {
    total_cases: number;
    approved_cases: number;
    refused_cases: number;
    active_pending_cases: number;
    reported_approval_rate_pct: number;
    avg_good_standing_pct: number;
    pending_document_approvals: number;
    approved_deliverables: number;
    estimated_pipeline_usd: number;
    official_sources_count: number;
    official_pdfs_count: number;
    source_manifest_count: number;
    source_diff_alerts: number;
  };
  stage_distribution: Record<string, number>;
  risk_distribution: Record<string, number>;
  top_risk_flags: Array<{ code: string; count: number }>;
  prediction_evaluation: {
    frozen_cases_count: number;
    profile_questions_observed: number;
    profile_thematic_hits: number;
    profile_thematic_recall_pct: number;
    policy_questions_tracked_separately: number;
    compliance_note: string;
  };
  recent_activity: Array<{ id: number; case_id: string; event_type: string; actor: string; summary: string; created_at: string }>;
}

export default function CeoDashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [branding, setBranding] = useState<BrandingConfig | null>(null);
  const [section, setSection] = useState<"executive" | "database" | "obsidian" | "setup" | "users">("executive");
  const [overview, setOverview] = useState<CeoOverview | null>(null);
  const [users, setUsers] = useState<UserAccount[]>([]);

  // Create Staff / Account form
  const [newFullName, setNewFullName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"staff" | "ceo" | "customer">("staff");
  const [userMsg, setUserMsg] = useState("");

  useEffect(() => {
    const u = getStoredUser<UserAccount>();
    if (!u) {
      router.replace("/login");
      return;
    }
    if (u.role !== "ceo") {
      router.replace(u.role === "staff" ? "/staff" : "/portal");
      return;
    }
    setUser(u);
    fetch("/api/branding").then((r) => r.json()).then(setBranding).catch(() => {});
    apiFetch<CeoOverview>("/api/ceo/overview").then(setOverview).catch(() => {});
    apiFetch<UserAccount[]>("/api/auth/users").then(setUsers).catch(() => {});
  }, [router]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setUserMsg("");
    await apiFetch("/api/auth/users", {
      method: "POST",
      body: JSON.stringify({ full_name: newFullName, email: newEmail, password: newPassword, role: newRole }),
    });
    setNewFullName("");
    setNewEmail("");
    setNewPassword("");
    setUserMsg("Account created successfully.");
    const list = await apiFetch<UserAccount[]>("/api/auth/users");
    setUsers(list);
  };

  if (!user) return null;

  return (
    <AppShell user={user} branding={branding} activePortal="ceo">
      <div className="space-y-5">
        {/* Executive Header */}
        <div className="rounded-2xl bg-gradient-to-r from-[#0e2d1a] via-ja-green to-ja-navy text-white p-6 shadow-lg flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-ja-goldBright text-ja-green text-[10px] font-extrabold uppercase tracking-wider">
              <Crown className="w-3 h-3" /> CEO Executive Command Suite
            </span>
            <h1 className="text-2xl font-extrabold mt-1">
              {branding?.agency_name || "Jahtaria Travel Services"} — Executive Intelligence
            </h1>
            <p className="text-xs text-emerald-100/85 mt-0.5">
              Agency-wide visa readiness, prediction recall audit, official gov source verification, white-label resale control &amp; staff governance.
            </p>
          </div>

          <div className="flex flex-wrap gap-1.5 bg-black/25 p-1.5 rounded-2xl">
            {[
              { id: "executive", label: "Executive KPIs", icon: BarChart3 },
              { id: "database", label: "Database & PDFs", icon: Database },
              { id: "obsidian", label: "Obsidian Vault", icon: BookOpen },
              { id: "setup", label: "Easy Setup & Branding", icon: Settings },
              { id: "users", label: "Team Logins", icon: Users },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => setSection(item.id as typeof section)}
                  className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition ${
                    section === item.id ? "bg-ja-goldBright text-ja-green shadow" : "text-white/85 hover:bg-white/10"
                  }`}
                >
                  <Icon className="w-4 h-4" /> {item.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* SECTION 1: EXECUTIVE KPI DASHBOARD */}
        {section === "executive" && overview && (
          <div className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="ja-card p-5 border-t-4 border-ja-green">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>TOTAL CASES IN PORTFOLIO</span>
                  <Users className="w-4 h-4 text-ja-green" />
                </div>
                <div className="text-3xl font-black text-slate-900 mt-1">{overview.kpis.total_cases}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {overview.kpis.approved_cases} approved • {overview.kpis.refused_cases} refused • {overview.kpis.active_pending_cases} active/unknown
                </div>
              </div>

              <div className="ja-card p-5 border-t-4 border-ja-gold">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>AVG GOOD STANDING SCORE</span>
                  <TrendingUp className="w-4 h-4 text-amber-600" />
                </div>
                <div className="text-3xl font-black text-ja-green mt-1">{overview.kpis.avg_good_standing_pct}%</div>
                <div className="text-xs text-slate-500 mt-1">
                  Reported Approval Rate (decided): <b>{overview.kpis.reported_approval_rate_pct}%</b>
                </div>
              </div>

              <div className="ja-card p-5 border-t-4 border-ja-navy">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>EST. PIPELINE VALUE (USD)</span>
                  <DollarSign className="w-4 h-4 text-ja-navy" />
                </div>
                <div className="text-3xl font-black text-ja-navy mt-1">
                  ${overview.kpis.estimated_pipeline_usd.toLocaleString()}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {overview.kpis.pending_document_approvals} draft(s) awaiting staff approval
                </div>
              </div>

              <div className="ja-card p-5 border-t-4 border-emerald-600">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>VERIFIED KNOWLEDGE CORPUS</span>
                  <FileCheck className="w-4 h-4 text-emerald-700" />
                </div>
                <div className="text-3xl font-black text-slate-900 mt-1">
                  {overview.kpis.official_pdfs_count} PDFs
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {overview.kpis.official_sources_count} gov URLs • {overview.kpis.source_manifest_count} manifest files • {overview.kpis.source_diff_alerts} diff alert(s)
                </div>
              </div>
            </div>

            {/* Prediction Accuracy Evaluation + Top Risk Flags */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              <div className="lg:col-span-6 ja-card p-5 space-y-3">
                <h3 className="font-extrabold text-sm text-ja-green uppercase tracking-wider border-b pb-2">
                  Interview Prediction Engine Evaluation (Compliant Audit)
                </h3>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="p-3 rounded-xl bg-ja-greenLight">
                    <div className="text-2xl font-black text-ja-green">
                      {overview.prediction_evaluation.profile_thematic_recall_pct}%
                    </div>
                    <div className="text-[11px] font-bold text-slate-600">Profile Thematic Recall</div>
                  </div>
                  <div className="p-3 rounded-xl bg-blue-50">
                    <div className="text-2xl font-black text-ja-navy">
                      {overview.prediction_evaluation.frozen_cases_count}
                    </div>
                    <div className="text-[11px] font-bold text-slate-600">Pre-Interview Frozen Cases</div>
                  </div>
                  <div className="p-3 rounded-xl bg-amber-50">
                    <div className="text-2xl font-black text-amber-800">
                      {overview.prediction_evaluation.policy_questions_tracked_separately}
                    </div>
                    <div className="text-[11px] font-bold text-slate-600">Policy Qs Separated</div>
                  </div>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-xl border">
                  {overview.prediction_evaluation.compliance_note}
                </p>
              </div>

              <div className="lg:col-span-6 ja-card p-5 space-y-3">
                <h3 className="font-extrabold text-sm text-ja-red uppercase tracking-wider border-b pb-2 flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4" /> Top Denial-Risk &amp; Discrepancy Flags Across Clients
                </h3>
                <div className="space-y-2">
                  {overview.top_risk_flags.map((rf, idx) => (
                    <div key={idx} className="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-slate-50 border text-xs">
                      <span className="font-bold text-slate-800">{rf.code}</span>
                      <span className="px-2.5 py-0.5 rounded-full bg-red-100 text-ja-red font-extrabold shrink-0">
                        {rf.count} case{rf.count === 1 ? "" : "s"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Live Pipeline Activity Log */}
            <div className="ja-card p-5 space-y-3">
              <h3 className="font-extrabold text-sm text-ja-navy uppercase tracking-wider border-b pb-2">
                Live Agency Activity &amp; Pipeline Audit Stream
              </h3>
              <div className="space-y-2 max-h-[340px] overflow-y-auto">
                {overview.recent_activity.map((ev) => (
                  <div key={ev.id} className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-50 border text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="px-2 py-0.5 rounded bg-ja-green text-ja-goldBright font-extrabold shrink-0">
                        {ev.case_id}
                      </span>
                      <span className="font-bold text-slate-700 shrink-0">{ev.actor}</span>
                      <span className="text-slate-600 truncate">{ev.summary}</span>
                    </div>
                    <span className="text-[11px] text-slate-400 shrink-0">
                      {ev.created_at ? new Date(ev.created_at).toLocaleString() : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {section === "database" && <DatabaseExplorer />}
        {section === "obsidian" && <ObsidianVaultView />}
        {section === "setup" && <EasySetupHub isCeo branding={branding} onBrandingUpdated={setBranding} />}

        {/* SECTION 5: CEO TEAM & ROLE LOGIN MANAGEMENT */}
        {section === "users" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <div className="lg:col-span-7 ja-card p-5 space-y-3">
              <h3 className="font-extrabold text-sm text-ja-green border-b pb-2">Registered Role Accounts ({users.length})</h3>
              <div className="space-y-2">
                {users.map((u) => (
                  <div key={u.id} className="flex items-center justify-between p-3 rounded-xl border bg-white text-xs">
                    <div>
                      <div className="font-bold text-slate-900">{u.full_name}</div>
                      <div className="text-slate-500">{u.email}</div>
                    </div>
                    <span className="px-2.5 py-1 rounded-full bg-ja-greenLight text-ja-green font-extrabold uppercase text-[10px]">
                      {u.role} {u.linked_case_id ? `• ${u.linked_case_id}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <form onSubmit={handleCreateUser} className="lg:col-span-5 ja-card p-5 space-y-3">
              <h3 className="font-extrabold text-sm text-ja-navy border-b pb-2 flex items-center gap-1.5">
                <UserPlus className="w-4 h-4" /> Create Staff / CEO / Customer Login
              </h3>
              <input className="ja-input text-xs" required placeholder="Full Name" value={newFullName} onChange={(e) => setNewFullName(e.target.value)} />
              <input className="ja-input text-xs" required type="email" placeholder="Email Address" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
              <input className="ja-input text-xs" required type="password" placeholder="Password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
              <select className="ja-input text-xs" value={newRole} onChange={(e) => setNewRole(e.target.value as "staff" | "ceo" | "customer")}>
                <option value="staff">Staff Case Specialist</option>
                <option value="ceo">CEO Executive Admin</option>
                <option value="customer">Customer Portal User</option>
              </select>
              {userMsg && (
                <div className="text-xs font-bold text-emerald-700 flex items-center gap-1">
                  <CheckCircle2 className="w-4 h-4" /> {userMsg}
                </div>
              )}
              <button type="submit" className="ja-btn-primary w-full py-2 text-xs">
                Create Account
              </button>
            </form>
          </div>
        )}
      </div>
    </AppShell>
  );
}
