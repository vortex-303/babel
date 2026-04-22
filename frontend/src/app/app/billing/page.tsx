"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/app/_lib/admin";
import { useAuth } from "@/app/_lib/auth";
import { isAuthConfigured } from "@/app/_lib/supabase";

type Pack = {
  words: number;
  price_usd: number;
  label: string;
};

type License = {
  price_usd: number;
  label: string;
  profile_flag: string;
  description: string;
};

type Entry = {
  id: number;
  delta: number;
  reason: string;
  job_id: number | null;
  stripe_session_id: string | null;
  created_at: string;
};

export default function BillingPage() {
  const { session, profile, loading, refreshProfile } = useAuth();
  const [packs, setPacks] = useState<Record<string, Pack>>({});
  const [licenses, setLicenses] = useState<Record<string, License>>({});
  const [history, setHistory] = useState<Entry[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetch("/api/billing/packs")
      .then((r) => r.json())
      .then((j) => {
        setPacks(j.packs as Record<string, Pack>);
        setLicenses((j.licenses ?? {}) as Record<string, License>);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!session) return;
    void refreshProfile();
    void api("/api/billing/history")
      .then((r) => r.json())
      .then((j) => setHistory(j.entries as Entry[]))
      .catch(() => {});
  }, [session, refreshProfile]);

  const buy = async (packId: string) => {
    setError(null);
    setPending(packId);
    try {
      const r = await api("/api/billing/checkout", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pack: packId }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.detail ?? r.statusText);
      }
      const j = (await r.json()) as { url: string };
      window.location.href = j.url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "checkout failed");
      setPending(null);
    }
  };

  if (!isAuthConfigured()) {
    return (
      <Layout>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Accounts aren’t wired up on this deployment yet.
        </p>
      </Layout>
    );
  }
  if (loading) {
    return <Layout>Loading…</Layout>;
  }
  if (!session) {
    return (
      <Layout>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Sign in from the menu in the top right to buy credits.
        </p>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 p-6 mb-8 bg-zinc-50 dark:bg-zinc-950">
        <p className="text-xs uppercase tracking-wide text-zinc-500">
          Current balance
        </p>
        <p className="text-3xl font-bold">
          {profile?.credits_balance.toLocaleString() ?? "—"}{" "}
          <span className="text-base font-medium text-zinc-500">words</span>
        </p>
        <p className="text-xs text-zinc-500 mt-1">
          Lifetime used: {profile?.credits_used.toLocaleString() ?? 0} words
        </p>
      </div>

      {Object.keys(licenses).length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-3">Self-host</h2>
          <div className="grid sm:grid-cols-1 gap-3">
            {Object.entries(licenses).map(([id, lic]) => {
              const owned = Boolean(
                profile && (profile as Record<string, unknown>)[lic.profile_flag],
              );
              return (
                <div
                  key={id}
                  className={`border rounded-xl p-5 flex items-center justify-between gap-4 ${
                    owned
                      ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-800"
                      : "border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950"
                  }`}
                >
                  <div className="flex-1">
                    <p className="font-semibold">
                      {lic.label}
                      {owned && (
                        <span className="ml-2 text-xs font-normal text-emerald-700 dark:text-emerald-300">
                          ✓ active
                        </span>
                      )}
                    </p>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                      {lic.description}
                    </p>
                  </div>
                  {owned ? (
                    <Link
                      href="/download"
                      className="text-sm font-medium px-4 py-2 rounded-full border border-emerald-600 text-emerald-700 dark:text-emerald-300 whitespace-nowrap"
                    >
                      Download app →
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void buy(id)}
                      disabled={pending !== null}
                      className="text-sm font-medium px-4 py-2 rounded-full bg-zinc-900 text-white dark:bg-white dark:text-black whitespace-nowrap disabled:opacity-50"
                    >
                      {pending === id
                        ? "Opening…"
                        : `Buy · $${lic.price_usd}`}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      <h2 className="text-lg font-semibold mb-3">Buy credits</h2>
      {error && (
        <p className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
      <div className="grid sm:grid-cols-3 gap-3">
        {Object.entries(packs).map(([id, pack]) => (
          <div
            key={id}
            className="border border-zinc-200 dark:border-zinc-800 rounded-xl p-5 bg-white dark:bg-zinc-950 flex flex-col"
          >
            <p className="text-sm uppercase tracking-wide text-zinc-500">{id}</p>
            <p className="text-2xl font-semibold mt-1">
              {pack.words.toLocaleString()} words
            </p>
            <p className="text-sm text-zinc-500 mt-1">
              ${pack.price_usd} one-time
            </p>
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => void buy(id)}
              disabled={pending !== null}
              className="mt-4 py-2 px-3 rounded-full bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
            >
              {pending === id ? "Opening…" : `Buy · $${pack.price_usd}`}
            </button>
          </div>
        ))}
      </div>

      <p className="mt-4 text-xs text-zinc-500">
        Credits never expire. Secure checkout by Stripe.
      </p>

      {history.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mt-10 mb-3">History</h2>
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800 border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden bg-white dark:bg-zinc-950">
            {history.map((e) => (
              <li
                key={e.id}
                className="px-4 py-2 flex items-center justify-between text-sm"
              >
                <div>
                  <p className="font-medium">
                    {e.reason === "stripe_topup"
                      ? "Top-up"
                      : e.reason === "job_consume"
                        ? "Translation"
                        : e.reason}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {new Date(e.created_at).toLocaleString()}
                  </p>
                </div>
                <span
                  className={
                    e.delta >= 0
                      ? "text-emerald-700 dark:text-emerald-300 font-mono"
                      : "text-zinc-600 dark:text-zinc-400 font-mono"
                  }
                >
                  {e.delta >= 0 ? "+" : ""}
                  {e.delta.toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Layout>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/app" className="text-sm text-zinc-500 hover:text-zinc-800">
            ← babel
          </Link>
          <h1 className="text-lg font-semibold">Billing</h1>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-6 py-10">{children}</main>
    </div>
  );
}
