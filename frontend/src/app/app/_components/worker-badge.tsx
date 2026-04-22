"use client";

import { useEffect, useState } from "react";

export function WorkerBadge() {
  const [online, setOnline] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch("/api/status", { cache: "no-store" });
        if (!r.ok) return;
        const j = (await r.json()) as { workers_online: number };
        if (alive) setOnline(j.workers_online);
      } catch {
        /* ignore */
      }
    };
    void poll();
    const id = window.setInterval(poll, 10_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  if (online === null) {
    return <span className="text-xs text-zinc-400">…</span>;
  }
  if (online > 0) {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
        title={`${online} worker${online === 1 ? "" : "s"} connected`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        translation online
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
      title="No Mac/Linux worker is currently connected. Jobs will queue until one comes online."
    >
      <span className="w-1.5 h-1.5 rounded-full bg-zinc-400" />
      no worker online
    </span>
  );
}
