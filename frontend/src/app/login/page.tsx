"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Crown, LogIn, UserPlus, KeyRound, ShieldCheck, RefreshCw, ArrowLeft } from "lucide-react";
import { apiFetch, setAuthSession } from "@/lib/api";
import type { BrandingConfig, UserAccount } from "@/lib/types";
import { DoctorBirdWatermark } from "@/components/DoctorBirdWatermark";

export default function LoginPage() {
  const router = useRouter();
  const [branding, setBranding] = useState<BrandingConfig | null>(null);
  const [ceoExists, setCeoExists] = useState<boolean | null>(null);
  const [mode, setMode] = useState<"setup_ceo" | "login" | "signup" | "code" | "forgot">("login");

  const [agencyName, setAgencyName] = useState("Jahtaria Travel Services");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryPin, setRecoveryPin] = useState("");
  const [phone, setPhone] = useState("");
  const [parish, setParish] = useState("St. Andrew");
  const [visaClass, setVisaClass] = useState("B1/B2");
  const [accessCode, setAccessCode] = useState("");

  // Forgot Password flow state
  const [forgotStep, setForgotStep] = useState<"lookup" | "reset">("lookup");
  const [forgotInfo, setForgotInfo] = useState<{
    username: string;
    has_recovery_pin: boolean;
    email_code_sent: boolean;
    message: string;
  } | null>(null);
  const [resetPin, setResetPin] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/branding")
      .then((r) => r.json())
      .then((b: BrandingConfig) => {
        setBranding(b);
        if (b.agency_name) setAgencyName(b.agency_name);
      })
      .catch(() => {});

    fetch("/api/auth/setup-status")
      .then((r) => r.json())
      .then((st: { ceo_exists: boolean }) => {
        setCeoExists(st.ceo_exists);
        if (!st.ceo_exists) {
          setMode("setup_ceo");
        } else {
          setMode("login");
        }
      })
      .catch(() => setCeoExists(true));
  }, []);

  const routeByRole = (user: UserAccount) => {
    if (user.role === "ceo") router.push("/ceo");
    else if (user.role === "staff") router.push("/staff");
    else router.push("/portal");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      if (mode === "setup_ceo") {
        const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/setup-ceo", {
          method: "POST",
          body: JSON.stringify({
            full_name: fullName,
            username,
            email,
            password,
            recovery_pin: recoveryPin,
            agency_name: agencyName,
          }),
        });
        setAuthSession(res.access_token, res.user);
        routeByRole(res.user);
      } else if (mode === "login") {
        const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ username, password }),
        });
        setAuthSession(res.access_token, res.user);
        routeByRole(res.user);
      } else if (mode === "signup") {
        const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/signup", {
          method: "POST",
          body: JSON.stringify({
            full_name: fullName,
            username,
            email,
            password,
            recovery_pin: recoveryPin,
            phone,
            parish,
            visa_class: visaClass,
          }),
        });
        setAuthSession(res.access_token, res.user);
        routeByRole(res.user);
      } else if (mode === "code") {
        const res = await apiFetch<{ access_token: string; user: UserAccount }>("/api/auth/case-code", {
          method: "POST",
          body: JSON.stringify({ access_code: accessCode }),
        });
        setAuthSession(res.access_token, res.user);
        routeByRole(res.user);
      } else if (mode === "forgot") {
        if (forgotStep === "lookup") {
          const info = await apiFetch<{
            username: string;
            has_recovery_pin: boolean;
            email_code_sent: boolean;
            message: string;
          }>("/api/auth/forgot-password/request", {
            method: "POST",
            body: JSON.stringify({ identifier: username }),
          });
          setForgotInfo(info);
          setForgotStep("reset");
        } else {
          const res = await apiFetch<{ reset: boolean; message: string }>("/api/auth/forgot-password/reset", {
            method: "POST",
            body: JSON.stringify({
              identifier: username,
              recovery_pin: resetPin,
              reset_code: resetCode,
              new_password: newPassword,
            }),
          });
          setSuccess(res.message || "Password updated! Sign in with your new password.");
          setPassword("");
          setNewPassword("");
          setResetPin("");
          setResetCode("");
          setForgotStep("lookup");
          setForgotInfo(null);
          setMode("login");
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const displayAgency = branding?.agency_name || "Jahtaria Travel Services";

  return (
    <div className="min-h-screen graphite-ambient flex items-center justify-center p-4 relative overflow-hidden">
      <div className="pointer-events-none select-none absolute inset-0 flex items-center justify-center">
        <DoctorBirdWatermark variant="backdrop" className="w-[540px] max-w-[90%] opacity-[0.1]" />
      </div>
      <div className="w-full max-w-md g-card overflow-hidden shadow-2xl relative z-10 border-[#e5b84b]/20">
        <div className="h-[3px] w-full ja-ribbon" />
        <div className="p-7 space-y-6">
          {/* Brand Header */}
          <div className="flex flex-col items-center text-center gap-3">
            <img
              src={branding?.logo_url || "/jahtaria-logo.png"}
              alt={displayAgency}
              className="w-16 h-16 rounded-full border-2 border-[#e5b84b]/50 shadow-lg object-cover bg-black"
            />
            <div>
              <h1 className="text-xl font-bold text-slate-100 tracking-tight">{displayAgency}</h1>
              <p className="text-xs text-[#e5b84b]/85 mt-0.5 inline-flex items-center gap-1.5">
                <DoctorBirdWatermark variant="emblem" className="w-4 h-3.5" />
                U.S. Visa Intelligence Agent • Kingston, Jamaica
              </p>
            </div>
          </div>

          {/* Mode Switcher */}
          {mode !== "forgot" && (
            <div className="flex flex-wrap gap-1 bg-[#111318] p-1 rounded-xl border border-white/10">
              {ceoExists === false && (
                <button
                  type="button"
                  onClick={() => {
                    setMode("setup_ceo");
                    setError("");
                  }}
                  className={`flex-1 min-w-[110px] py-2 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                    mode === "setup_ceo" ? "bg-amber-500/20 text-amber-300 border border-amber-400/30" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Crown className="w-3.5 h-3.5" /> Setup CEO
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError("");
                }}
                className={`flex-1 min-w-[85px] py-2 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "login" ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <LogIn className="w-3.5 h-3.5" /> Sign In
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("signup");
                  setError("");
                }}
                className={`flex-1 min-w-[100px] py-2 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "signup" ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" /> Client Sign Up
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("code");
                  setError("");
                }}
                className={`flex-1 min-w-[90px] py-2 px-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "code" ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <KeyRound className="w-3.5 h-3.5" /> Case Code
              </button>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-3.5">
            {mode === "setup_ceo" && (
              <>
                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-400/20 text-xs text-amber-200 leading-relaxed">
                  <b>First-Time Agency Owner Setup:</b> Create your <b>CEO</b> account with a username &amp; Recovery PIN (no email required).
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Agency Name</label>
                  <input className="g-input" required value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">CEO Full Name</label>
                  <input className="g-input" required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Owner / Director Name" />
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Username</label>
                    <input className="g-input" required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. ceo_jahtaria" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Recovery PIN</label>
                    <input className="g-input" value={recoveryPin} onChange={(e) => setRecoveryPin(e.target.value)} placeholder="4-8 digits (offline reset)" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Recovery Email (Optional)</label>
                  <input className="g-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Optional for Gmail OTP resets" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">CEO Password (min 6 chars)</label>
                  <input className="g-input" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
                </div>
              </>
            )}

            {mode === "login" && (
              <>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Username</label>
                  <input
                    className="g-input"
                    type="text"
                    required
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Enter your username"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-medium text-slate-300">Password</label>
                    <button
                      type="button"
                      onClick={() => {
                        setMode("forgot");
                        setForgotStep("lookup");
                        setForgotInfo(null);
                        setError("");
                        setSuccess("");
                      }}
                      className="text-[11px] text-[#e5b84b] hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <input
                    className="g-input"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                </div>
              </>
            )}

            {mode === "forgot" && (
              <>
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-white flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 text-[#e5b84b]" /> Reset Password by Username
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setMode("login");
                      setForgotStep("lookup");
                      setForgotInfo(null);
                      setError("");
                    }}
                    className="text-[11px] text-slate-400 hover:text-white inline-flex items-center gap-1"
                  >
                    <ArrowLeft className="w-3 h-3" /> Back
                  </button>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Username</label>
                  <input
                    className="g-input"
                    required
                    disabled={forgotStep === "reset"}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Enter your username"
                  />
                </div>

                {forgotStep === "reset" && forgotInfo && (
                  <>
                    <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-400/25 text-xs text-emerald-200">
                      {forgotInfo.message}
                    </div>
                    {forgotInfo.has_recovery_pin && (
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">Recovery PIN (Offline)</label>
                        <input
                          className="g-input"
                          value={resetPin}
                          onChange={(e) => setResetPin(e.target.value)}
                          placeholder="Enter your Recovery PIN"
                        />
                      </div>
                    )}
                    {forgotInfo.email_code_sent && (
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">6-Digit Gmail Reset Code</label>
                        <input
                          className="g-input font-mono"
                          value={resetCode}
                          onChange={(e) => setResetCode(e.target.value)}
                          placeholder="123456"
                        />
                      </div>
                    )}
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">New Password (min 6 chars)</label>
                      <input
                        className="g-input"
                        type="password"
                        required
                        minLength={6}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Enter new password"
                      />
                    </div>
                  </>
                )}
              </>
            )}

            {mode === "signup" && (
              <>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Full Legal Name</label>
                    <input className="g-input" required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Your Name" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Username</label>
                    <input className="g-input" required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="choose_username" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Password</label>
                    <input className="g-input" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="min 6 chars" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Recovery PIN</label>
                    <input className="g-input" value={recoveryPin} onChange={(e) => setRecoveryPin(e.target.value)} placeholder="4+ digits (for reset)" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Email (Optional)</label>
                    <input className="g-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="For visa alerts" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">WhatsApp / Phone</label>
                    <input className="g-input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 (876) ..." />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Parish</label>
                    <input className="g-input" value={parish} onChange={(e) => setParish(e.target.value)} placeholder="St. Andrew" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Visa Class</label>
                    <select className="g-input" value={visaClass} onChange={(e) => setVisaClass(e.target.value)}>
                      <option value="B1/B2">B1/B2 Visitor</option>
                      <option value="F-1">F-1 Student</option>
                      <option value="H-2B">H-2B Worker</option>
                      <option value="J-1">J-1 Exchange</option>
                    </select>
                  </div>
                </div>
              </>
            )}

            {mode === "code" && (
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Case Access Code</label>
                <input
                  className="g-input font-mono uppercase"
                  required
                  value={accessCode}
                  onChange={(e) => setAccessCode(e.target.value)}
                  placeholder="JAH-C034"
                />
                <p className="text-[11px] text-slate-400 mt-1.5">
                  Enter the personal Case Code provided by your {displayAgency} advisor.
                </p>
              </div>
            )}

            {error && (
              <div className="p-3 rounded-xl bg-red-500/15 border border-red-400/30 text-xs text-red-200">{error}</div>
            )}
            {success && (
              <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-400/30 text-xs text-emerald-200">{success}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition disabled:opacity-60 border border-[#e5b84b]/25 shadow-md"
            >
              {loading
                ? "Please wait…"
                : mode === "setup_ceo"
                ? "Create Agency CEO Account"
                : mode === "login"
                ? "Sign In"
                : mode === "forgot"
                ? forgotStep === "lookup"
                  ? "Find Account & Recovery Options"
                  : "Set New Password"
                : mode === "signup"
                ? "Create Client Portal Account"
                : "Open My Case"}
            </button>
          </form>

          {/* Truthfulness Footer */}
          <div className="pt-3 border-t border-white/10 flex items-center gap-2 text-[11px] text-slate-400">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              Truthful U.S. Embassy Kingston preparation only. All personal records are stored encrypted locally.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
