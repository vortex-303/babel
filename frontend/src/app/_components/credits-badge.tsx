"use client";

import Link from "next/link";

import { useAuth } from "@/app/_lib/auth";

export function CreditsBadge() {
  const { session, profile, loading } = useAuth();
  if (loading || !session) return null;
  if (!profile) return null;
  const low = profile.credits_balance < 1000;
  return (
    <Link
      href="/app/billing"
      className={`text-xs px-2 py-1 rounded-full border ${
        low
          ? "border-amber-400 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300"
          : "border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
      }`}
      title={`${profile.credits_balance.toLocaleString()} words left`}
    >
      {profile.credits_balance.toLocaleString()} words
    </Link>
  );
}
