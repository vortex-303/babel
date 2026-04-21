"use client";

import { useEffect, useState } from "react";

type Health = { ok: boolean; adapter?: string; source?: string; target?: string };

export function HealthBadge() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <span className="text-xs px-2 py-1 rounded-full bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300">
        backend offline
      </span>
    );
  }
  if (!health) {
    return <span className="text-xs text-zinc-400">…</span>;
  }
  return (
    <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      {health.adapter} · {health.source}→{health.target}
    </span>
  );
}
