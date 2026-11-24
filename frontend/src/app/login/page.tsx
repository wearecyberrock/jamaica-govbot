"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, KeyRound, UserPlus, LogIn, Crown, Briefcase, User as UserIcon } from "lucide-react";
import { apiFetch, setAuthSession } from "@/lib/api";
import type { BrandingConfig, UserAccount } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [branding, setBranding] = useState<BrandingConfig | null>(null);
  const [mode, setMode] = useState<"login" | "signup" | "code">("login");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [parish, setParish] = useState("St. Andrew");
  const [visaClass, setVisaClass] = useState("B1/B2");
  const [accessCode, setAccessCode] = useState("JAH-C034");

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/branding")
      .then((r) => r.json())
      .then(setBranding)
      .catch(() => {});
  }, []);

  const routeByRole = (user: UserAccount) => {
    if (user.role === "ceo") router.push("/ceo");
    else if (user.role === "staff") router.push("/staff");
    else router.push("/portal");
  };

  const doLogin = async (loginEmail: string, loginPassword: string) => {
    setError("");
    setLoading(true);
    try {
      const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      setAuthSession(res.access_token, res.user);
      routeByRole(res.user);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "login") {
      await doLogin(email, password);
      return;
    }
    setError("");
    setLoading(true);
    try {
      if (mode === "signup") {
        const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/signup", {
          method: "POST",
          body: JSON.stringify({ full_name: fullName, email, password, phone, parish, visa_class: visaClass }),
        });
        setAuthSession(res.access_token, res.user);
        routeByRole(res.user);
      } else {
        const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/case-code", {
          method: "POST",
          body: JSON.stringify({ access_code: accessCode }),
        });
        setAuthSession(res.access_token, res.user);
        routeByRole(res.user);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const agencyName = branding?.agency_name || "Jahtaria Travel Services";
  const tagline = branding?.tagline || "U.S. Visa Preparation & Consular Intelligence";

  return (
    <div className="min-h-screen flex flex-col">
      <div className="ja-tricolor-bar" />
      <div className="flex-1 flex items-center justify-center p-4 sm:p-8">
        <div className="max-w-5xl w-full grid grid-cols-1 lg:grid-cols-12 rounded-3xl overflow-hidden shadow-2xl border border-slate-200 bg-white">
          {/* Left Hero — Jamaican Emerald & Royal Gold */}
          <div className="lg:col-span-5 bg-gradient-to-br from-ja-green via-[#133b22] to-ja-navy text-white p-8 flex flex-col justify-between">
            <div className="space-y-5">
              <div className="flex items-center gap-3.5">
                <img
                  src={branding?.logo_url || "/jahtaria-logo.png"}
                  alt={agencyName}
                  className="w-16 h-16 rounded-full border-2 border-ja-goldBright shadow-xl bg-white object-cover"
                />
                <div>
                  <span className="inline-block px-2.5 py-0.5 rounded-full bg-ja-goldBright text-ja-green text-[10px] font-extrabold uppercase tracking-wider">
                    Jamaica → U.S. Visa Suite
                  </span>
                  <h1 className="text-xl font-extrabold text-white mt-1 leading-tight">{agencyName}</h1>
                </div>
              </div>

              <p className="text-sm text-emerald-100/90 leading-relaxed">{tagline}</p>

              <div className="space-y-2.5 text-xs text-emerald-50/90 pt-2">
                <div className="flex items-start gap-2">
                  <ShieldCheck className="w-4 h-4 text-ja-goldBright shrink-0 mt-0.5" />
                  <span>Deterministic Kingston Embassy Good Standing Engine (DS-160 AA Barcode, PICA 6-Month Passport &amp; 92% RGD Rules).</span>
                </div>
                <div className="flex items-start gap-2">
                  <ShieldCheck className="w-4 h-4 text-ja-goldBright shrink-0 mt-0.5" />
                  <span>Built-in Official PICA &amp; U.S. Dept. of State PDF Viewer, Obsidian Vault &amp; Hermes Autonomous Agent.</span>
                </div>
                <div className="flex items-start gap-2">
                  <ShieldCheck className="w-4 h-4 text-ja-goldBright shrink-0 mt-0.5" />
                  <span>Three Dedicated Role Portals: Customer Portal, Staff Case Workspace &amp; CEO Executive Suite.</span>
                </div>
              </div>
            </div>

            {/* Quick 1-Click Local Desktop Role Switcher */}
            <div className="mt-8 pt-5 border-t border-white/15 space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-wider text-ja-goldBright">
                Quick Local Desktop Sign-In (Seeded Accounts)
              </div>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => doLogin("ceo@jahtariatravel.com", "JahtariaCEO2026!")}
                  className="p-2 rounded-xl bg-white/10 hover:bg-ja-goldBright hover:text-ja-green text-xs font-bold flex flex-col items-center gap-1 transition"
                >
                  <Crown className="w-4 h-4" /> CEO
                </button>
                <button
                  type="button"
                  onClick={() => doLogin("staff@jahtariatravel.com", "JahtariaStaff2026!")}
                  className="p-2 rounded-xl bg-white/10 hover:bg-ja-goldBright hover:text-ja-green text-xs font-bold flex flex-col items-center gap-1 transition"
                >
                  <Briefcase className="w-4 h-4" /> Staff
                </button>
                <button
                  type="button"
                  onClick={() => doLogin("client@jahtariatravel.com", "JahtariaClient2026!")}
                  className="p-2 rounded-xl bg-white/10 hover:bg-ja-goldBright hover:text-ja-green text-xs font-bold flex flex-col items-center gap-1 transition"
                >
                  <UserIcon className="w-4 h-4" /> Customer
                </button>
              </div>
            </div>
          </div>

          {/* Right Form Panel */}
          <div className="lg:col-span-7 p-8 flex flex-col justify-center">
            <div className="flex gap-1.5 bg-slate-100 p-1 rounded-xl mb-6">
              <button
                type="button"
                onClick={() => setMode("login")}
                className={`flex-1 py-2 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition ${
                  mode === "login" ? "bg-ja-green text-ja-goldBright shadow" : "text-slate-600"
                }`}
              >
                <LogIn className="w-3.5 h-3.5" /> Sign In
              </button>
              <button
                type="button"
                onClick={() => setMode("signup")}
                className={`flex-1 py-2 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition ${
                  mode === "signup" ? "bg-ja-green text-ja-goldBright shadow" : "text-slate-600"
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" /> New Client Signup
              </button>
              <button
                type="button"
                onClick={() => setMode("code")}
                className={`flex-1 py-2 rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 transition ${
                  mode === "code" ? "bg-ja-green text-ja-goldBright shadow" : "text-slate-600"
                }`}
              >
                <KeyRound className="w-3.5 h-3.5" /> Case Access Code
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === "login" && (
                <>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Email Address</label>
                    <input className="ja-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ceo@jahtariatravel.com" />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Password</label>
                    <input className="ja-input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••••••" />
                  </div>
                </>
              )}

              {mode === "signup" && (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Full Legal Name</label>
                      <input className="ja-input" required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="e.g. Andre Williams" />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">WhatsApp / Phone</label>
                      <input className="ja-input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 (876) ..." />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">Parish</label>
                      <input className="ja-input" value={parish} onChange={(e) => setParish(e.target.value)} />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1">U.S. Visa Type</label>
                      <select className="ja-input" value={visaClass} onChange={(e) => setVisaClass(e.target.value)}>
                        <option value="B1/B2">B1/B2 Visitor / Business</option>
                        <option value="F1">F-1 Student</option>
                        <option value="H-2B">H-2B Temporary Worker</option>
                        <option value="J1">J-1 Exchange Visitor</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Email Address</label>
                    <input className="ja-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Create Password</label>
                    <input className="ja-input" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} />
                  </div>
                </>
              )}

              {mode === "code" && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Client Case Access Code</label>
                  <input
                    className="ja-input font-mono uppercase tracking-wider text-base"
                    required
                    value={accessCode}
                    onChange={(e) => setAccessCode(e.target.value)}
                    placeholder="JAH-C034"
                  />
                  <p className="text-xs text-slate-500 mt-1.5">
                    Enter the unique access code provided by your Jahtaria visa advisor (demo code: <code>JAH-C034</code> or <code>JAH-C001</code>).
                  </p>
                </div>
              )}

              {error && <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs font-bold text-ja-red">{error}</div>}

              <button type="submit" disabled={loading} className="ja-btn-primary w-full py-3 text-sm">
                {loading ? "Signing In..." : mode === "login" ? "Sign In to Dashboard" : mode === "signup" ? "Create My Visa Portal Account" : "Open My Case Portal"}
              </button>
            </form>

            <p className="text-[11px] text-slate-400 mt-6 leading-relaxed">
              {branding?.compliance_notice ||
                "Truthful application verification & interview readiness only. We never guarantee visa approval or coach concealment."}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
