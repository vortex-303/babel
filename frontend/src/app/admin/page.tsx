"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, getAdminCode } from "../_lib/admin";
import { UserMenu } from "../_components/user-menu";

type Health = {
  backend: boolean;
  llama_server: { ok: boolean; host: string; port: number; error: string | null };
  queue: {
    mode: "auto" | "manual";
    queued: number;
    pending_approval: number;
    active: {
      id: number;
      filename: string | null;
      translated_chunks: number;
      chunk_count: number;
      started_at: string | null;
    } | null;
  };
};

type QueueEntry = {
  id: number;
  document_filename: string | null;
  document_word_count: number | null;
  status: string;
  source_lang: string;
  target_lang: string;
  model_adapter: string;
  priority: number;
  submitted_by_admin: boolean;
  queued_at: string | null;
  started_at: string | null;
  translated_chunks: number;
  chunk_count: number;
};

export default function AdminPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [queue, setQueue] = useState<QueueEntry[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [h, q] = await Promise.all([
        api("/api/admin/health"),
        api("/api/admin/queue"),
      ]);
      if (h.status === 403 || q.status === 403) {
        setAuthed(false);
        return;
      }
      setAuthed(true);
      if (h.ok) setHealth(await h.json());
      if (q.ok) setQueue(await q.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "refresh failed");
    }
  }, []);

  useEffect(() => {
    if (!getAdminCode()) {
      setAuthed(false);
      return;
    }
    void refresh();
    const iv = window.setInterval(refresh, 5000);
    return () => window.clearInterval(iv);
  }, [refresh]);

  const setMode = async (mode: "auto" | "manual") => {
    setBusy(true);
    try {
      await api("/api/admin/mode", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const act = async (id: number, action: "accept" | "reject") => {
    setBusy(true);
    try {
      await api(`/api/admin/queue/${id}/${action}`, { method: "POST" });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const bump = async (id: number, delta: number) => {
    const entry = queue?.find((e) => e.id === id);
    if (!entry) return;
    setBusy(true);
    try {
      await api(`/api/admin/queue/${id}/priority`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ priority: entry.priority + delta }),
      });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const purge = async () => {
    if (!confirm("Delete all documents older than the retention window?"))
      return;
    setBusy(true);
    try {
      const r = await api("/api/admin/purge", { method: "POST" });
      const body = await r.json();
      alert(`Removed ${body.documents_removed} documents`);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  if (authed === false) {
    return (
      <Gate>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Admin access required.{" "}
          <span className="text-zinc-500">
            Use the <strong>Guest</strong> button up top to enter your
            pass-code, then come back.
          </span>
        </p>
      </Gate>
    );
  }

  if (authed === null) {
    return <Gate><p className="text-sm text-zinc-500">Checking…</p></Gate>;
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <Link
              href="/app"
              className="text-xs text-zinc-500 hover:text-zinc-800"
            >
              ← back to app
            </Link>
            <h1 className="text-xl font-semibold tracking-tight mt-1">Admin</h1>
          </div>
          <UserMenu />
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {/* Health */}
        {health && (
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat
              label="Backend"
              value={health.backend ? "ok" : "down"}
              ok={health.backend}
            />
            <Stat
              label={`llama-server ${health.llama_server.host}:${health.llama_server.port}`}
              value={health.llama_server.ok ? "ok" : "down"}
              ok={health.llama_server.ok}
            />
            <Stat label="Queue depth" value={health.queue.queued.toString()} />
            <Stat
              label="Pending approval"
              value={health.queue.pending_approval.toString()}
            />
          </section>
        )}

        {/* Mode + actions */}
        {health && (
          <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-medium mb-1">Queue mode</h2>
                <p className="text-xs text-zinc-500">
                  In <strong>auto</strong>, new jobs go straight to the queue.
                  In <strong>manual</strong>, non-admin jobs wait for your
                  approval.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy || health.queue.mode === "auto"}
                  onClick={() => void setMode("auto")}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border ${
                    health.queue.mode === "auto"
                      ? "bg-emerald-600 text-white border-emerald-600"
                      : "border-zinc-300 dark:border-zinc-700"
                  }`}
                >
                  Auto
                </button>
                <button
                  type="button"
                  disabled={busy || health.queue.mode === "manual"}
                  onClick={() => void setMode("manual")}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border ${
                    health.queue.mode === "manual"
                      ? "bg-amber-600 text-white border-amber-600"
                      : "border-zinc-300 dark:border-zinc-700"
                  }`}
                >
                  Manual
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 pt-2 border-t border-zinc-200 dark:border-zinc-800">
              <button
                type="button"
                disabled={busy}
                onClick={() => void purge()}
                className="px-3 py-1.5 rounded-full text-xs font-medium border border-red-400 text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
              >
                Purge expired
              </button>
              <button
                type="button"
                onClick={() => void refresh()}
                className="px-3 py-1.5 rounded-full text-xs font-medium border border-zinc-300 dark:border-zinc-700"
              >
                Refresh
              </button>
            </div>
          </section>
        )}

        {/* Active job */}
        {health?.queue.active && (
          <section className="rounded-xl border border-emerald-400/40 bg-emerald-50/60 dark:bg-emerald-950/30 p-5">
            <h2 className="text-base font-medium mb-1">Currently translating</h2>
            <p className="text-sm">
              #{health.queue.active.id}{" "}
              <span className="text-zinc-600 dark:text-zinc-400">
                — {health.queue.active.filename}
              </span>
            </p>
            <p className="text-xs text-zinc-500 mt-1">
              {health.queue.active.translated_chunks} /{" "}
              {health.queue.active.chunk_count} chunks
              {health.queue.active.started_at && (
                <> · started {new Date(health.queue.active.started_at).toLocaleTimeString()}</>
              )}
            </p>
          </section>
        )}

        {/* Queue list */}
        <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
          <div className="px-5 py-3 border-b border-zinc-200 dark:border-zinc-800">
            <h2 className="text-base font-medium">Queue</h2>
          </div>
          {queue && queue.length > 0 ? (
            <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {queue.map((entry) => (
                <li key={entry.id} className="px-5 py-3 flex flex-wrap items-center gap-3">
                  <span
                    className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded ${
                      entry.status === "pending_approval"
                        ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                        : entry.status === "translating"
                          ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                          : "bg-zinc-500/15 text-zinc-600 dark:text-zinc-300"
                    }`}
                  >
                    {entry.status}
                  </span>
                  <span className="text-sm flex-1 truncate">
                    #{entry.id} {entry.document_filename}
                  </span>
                  <span className="text-xs text-zinc-500">
                    {entry.source_lang} → {entry.target_lang} ·{" "}
                    {entry.document_word_count?.toLocaleString() ?? "?"} words
                  </span>
                  <div className="flex gap-1">
                    {entry.status === "pending_approval" && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void act(entry.id, "accept")}
                          className="px-2 py-1 text-xs rounded bg-emerald-600 text-white"
                        >
                          Accept
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void act(entry.id, "reject")}
                          className="px-2 py-1 text-xs rounded border border-zinc-300 dark:border-zinc-700"
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {entry.status === "queued" && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void bump(entry.id, 1)}
                          className="px-2 py-1 text-xs rounded border border-zinc-300 dark:border-zinc-700"
                          title="Bump priority"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void bump(entry.id, -1)}
                          className="px-2 py-1 text-xs rounded border border-zinc-300 dark:border-zinc-700"
                          title="Lower priority"
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void act(entry.id, "reject")}
                          className="px-2 py-1 text-xs rounded border border-zinc-300 dark:border-zinc-700"
                        >
                          Cancel
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-8 text-sm text-zinc-500 text-center">
              Queue is empty.
            </p>
          )}
        </section>
      </main>
    </div>
  );
}

function Gate({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid place-items-center bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100 p-6">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-2xl font-semibold">Admin</h1>
        {children}
        <div>
          <Link
            href="/"
            className="text-xs text-zinc-500 hover:text-zinc-800"
          >
            ← home
          </Link>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border px-4 py-3 ${
        ok === undefined
          ? "border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950"
          : ok
            ? "border-emerald-300 bg-emerald-50/70 dark:bg-emerald-950/30"
            : "border-red-300 bg-red-50/70 dark:bg-red-950/30"
      }`}
    >
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="text-lg font-semibold mt-0.5">{value}</div>
    </div>
  );
}
