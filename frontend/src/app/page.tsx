"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser } from "@/lib/api";
import type { UserAccount } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const user = getStoredUser<UserAccount>();
    if (!user) {
      router.replace("/login");
    } else if (user.role === "ceo") {
      router.replace("/ceo");
    } else if (user.role === "staff") {
      router.replace("/staff");
    } else {
      router.replace("/portal");
    }
  }, [router]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4">
      <img src="/jahtaria-logo.png" alt="Jahtaria" className="w-20 h-20 rounded-full shadow-lg" />
      <p className="text-sm font-semibold text-ja-green">Loading Jahtaria Visa Intelligence…</p>
    </div>
  );
}
