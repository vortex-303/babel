"use client";

import Link from "next/link";

import { useAuth } from "@/app/_lib/auth";

/**
 * Top-nav quota pill for signed-in users. Fat number + embedded "Buy"
 * CTA so the state + next action live in one compact control. Colors
 * track urgency: emerald (plenty) → amber (low) → red (empty).
 */
export function CreditsBadge() {
  const { session, profile, loading } = useAuth();
  if (loading || !session || !profile) return null;

  const words = profile.credits_balance;
  const out = words <= 0;
  const low = !out && words < 10_000;

  const tone = out
    ? "border-red-400 bg-red-100 text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-300"
    : low
      ? "border-amber-400 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300"
      : "border-emerald-400 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border pl-3 pr-1 py-1 text-xs ${tone}`}
    >
      {profile.self_host_license && (
        <span title="Self-host license active" className="text-[11px]">
          🔓
        </span>
      )}
      <span className="font-semibold">
        {compact(words)} <span className="font-normal opacity-70">words</span>
      </span>
      <Link
        href="/app/billing"
        className="rounded-full bg-white/60 dark:bg-black/40 hover:bg-white dark:hover:bg-black px-2.5 py-0.5 text-[11px] font-medium"
      >
        {out ? "Buy" : low ? "Top up" : "Buy more"}
      </Link>
    </div>
  );
}

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}
