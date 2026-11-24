"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, ShieldCheck, Briefcase, User as UserIcon, Crown } from "lucide-react";
import { clearAuthSession } from "@/lib/api";
import type { BrandingConfig, UserAccount } from "@/lib/types";

interface AppShellProps {
  user: UserAccount;
  branding: BrandingConfig | null;
  activePortal: "portal" | "staff" | "ceo";
  children: React.ReactNode;
}

export function AppShell({ user, branding, activePortal, children }: AppShellProps) {
  const router = useRouter();
  const agencyName = branding?.agency_name || "Jahtaria Travel Services";
  const tagline = branding?.tagline || "U.S. Visa Preparation & Consular Intelligence";
  const logoSrc = branding?.logo_url || "/jahtaria-logo.png";

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // ignore
    }
    clearAuthSession();
    router.push("/login");
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 bg-ja-green text-white shadow-lg">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <img
              src={logoSrc}
              alt={agencyName}
              className="w-11 h-11 rounded-full border-2 border-ja-goldBright shadow object-cover bg-white shrink-0"
            />
            <div className="truncate">
              <div className="flex items-center gap-2">
                <span className="font-extrabold tracking-tight text-base sm:text-lg text-ja-goldBright truncate">
                  {agencyName}
                </span>
                <span className="hidden md:inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/15 text-emerald-100">
                  <ShieldCheck className="w-3 h-3" /> Kingston Consular Suite
                </span>
              </div>
              <p className="text-[11px] text-emerald-100/80 truncate">{tagline}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            {user.role === "ceo" && (
              <nav className="hidden lg:flex items-center gap-1 bg-black/20 p-1 rounded-xl">
                <Link
                  href="/ceo"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                    activePortal === "ceo" ? "bg-ja-goldBright text-ja-green" : "text-white/85 hover:bg-white/10"
                  }`}
                >
                  <Crown className="w-3.5 h-3.5" /> CEO Suite
                </Link>
                <Link
                  href="/staff"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                    activePortal === "staff" ? "bg-ja-goldBright text-ja-green" : "text-white/85 hover:bg-white/10"
                  }`}
                >
                  <Briefcase className="w-3.5 h-3.5" /> Staff Workspace
                </Link>
                <Link
                  href="/portal"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                    activePortal === "portal" ? "bg-ja-goldBright text-ja-green" : "text-white/85 hover:bg-white/10"
                  }`}
                >
                  <UserIcon className="w-3.5 h-3.5" /> Client View
                </Link>
              </nav>
            )}

            {user.role === "staff" && (
              <nav className="hidden md:flex items-center gap-1 bg-black/20 p-1 rounded-xl">
                <Link
                  href="/staff"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                    activePortal === "staff" ? "bg-ja-goldBright text-ja-green" : "text-white/85 hover:bg-white/10"
                  }`}
                >
                  <Briefcase className="w-3.5 h-3.5" /> Staff Workspace
                </Link>
                <Link
                  href="/portal"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                    activePortal === "portal" ? "bg-ja-goldBright text-ja-green" : "text-white/85 hover:bg-white/10"
                  }`}
                >
                  <UserIcon className="w-3.5 h-3.5" /> Client Preview
                </Link>
              </nav>
            )}

            <div className="hidden sm:flex flex-col text-right leading-tight">
              <span className="text-xs font-bold text-white">{user.full_name}</span>
              <span className="text-[10px] uppercase tracking-wider text-ja-goldBright font-bold">
                {user.role} {user.linked_case_id ? `• ${user.linked_case_id}` : ""}
              </span>
            </div>

            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-ja-red text-white text-xs font-bold transition"
              title="Sign Out"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign Out</span>
            </button>
          </div>
        </div>
        <div className="ja-tricolor-bar" />
      </header>

      <main className="flex-1 max-w-[1440px] w-full mx-auto px-4 sm:px-6 py-6">{children}</main>

      <footer className="border-t border-slate-200/80 bg-white/70 py-3 px-6 text-center text-xs text-slate-500">
        <span className="font-semibold text-ja-green">{agencyName}</span> —{" "}
        {branding?.compliance_notice ||
          "Truthful application verification & interview readiness only. Visa decisions rest solely with U.S. Consular Officers."}
      </footer>
    </div>
  );
}
