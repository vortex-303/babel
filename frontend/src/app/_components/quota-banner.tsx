"use client";

import Link from "next/link";

import { useAuth } from "@/app/_lib/auth";

/**
 * Prominent quota readout for the top of the app page. Shows a fat number
 * of remaining words + a one-line context line ("≈ 3 novels left" etc) so
 * users never wonder whether they can run another translation.
 */
export function QuotaBanner() {
  const { session, profile, loading } = useAuth();
  if (loading || !session || !profile) return null;

  const words = profile.credits_balance;
  const low = words < 10_000;
  const out = words <= 0;

  return (
    <div
      className={`rounded-xl border px-5 py-3 mb-6 flex items-center justify-between gap-4 ${
        out
          ? "border-red-400 bg-red-50 dark:bg-red-950/30 dark:border-red-800"
          : low
            ? "border-amber-400 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800"
            : "border-zinc-200 bg-white dark:bg-zinc-950 dark:border-zinc-800"
      }`}
    >
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">
          Translation quota
        </p>
        <p className="text-2xl font-bold tracking-tight">
          {words.toLocaleString()}{" "}
          <span className="text-base font-medium text-zinc-500">
            words remaining
          </span>
        </p>
        <p className="text-xs text-zinc-500 mt-0.5">{tagline(words)}</p>
      </div>
      <Link
        href="/app/billing"
        className={`text-sm font-medium px-4 py-2 rounded-full whitespace-nowrap ${
          out || low
            ? "bg-emerald-600 text-white hover:bg-emerald-500"
            : "border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-900"
        }`}
      >
        {out ? "Buy credits →" : low ? "Top up →" : "Manage"}
      </Link>
    </div>
  );
}

function tagline(words: number): string {
  if (words <= 0) return "Buy credits to translate again.";
  if (words < 10_000) return "Low — consider topping up before your next doc.";
  const books = Math.round(words / 80_000);
  if (books >= 2) return `≈ ${books} full novels`;
  if (books === 1) return "≈ 1 full novel";
  return "Enough for a chapter or two.";
}
