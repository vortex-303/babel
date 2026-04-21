"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/app/_lib/admin";
import {
  LANGUAGES,
  PORTUGUESE_VARIANTS,
  SPANISH_VARIANTS,
} from "@/app/_lib/languages";

export type JobRow = {
  id: number;
  document_id: number;
  status: string;
  source_lang: string;
  target_lang: string;
  chunk_count: number;
  translated_chunks: number;
  model_adapter: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
};

export type DocumentLite = {
  id: number;
  filename: string;
  detected_lang: string | null;
};

export const STATUS_LABEL: Record<string, string> = {
  uploaded: "uploaded",
  analyzing: "analyzing",
  awaiting_glossary_review: "ready",
  queued: "queued",
  pending_approval: "pending approval",
  translating: "translating",
  reviewing: "reviewing",
  assembling: "assembling",
  done: "done",
  failed: "failed",
  rejected: "rejected",
};

export const TERMINAL = new Set(["done", "failed", "rejected"]);

/** Fetch jobs for a document + auto-poll while any are active. */
export function useDocumentJobs(documentId: number): [
  JobRow[] | null,
  () => Promise<void>,
] {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const pollRef = useRef<number | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await api(`/api/jobs?document_id=${documentId}`);
      if (res.ok) setJobs((await res.json()) as JobRow[]);
    } catch {
      /* ignore */
    }
  }, [documentId]);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    const anyActive = jobs?.some((j) => !TERMINAL.has(j.status));
    if (anyActive) {
      if (pollRef.current == null) {
        pollRef.current = window.setInterval(fetchJobs, 3000);
      }
    } else if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current != null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobs, fetchJobs]);

  return [jobs, fetchJobs];
}

/** One-click form to kick off a new translation version of a document. */
export function TriggerForm({
  doc,
  onDone,
  onCancel,
  compact = false,
}: {
  doc: DocumentLite;
  onDone: () => void;
  onCancel?: () => void;
  compact?: boolean;
}) {
  const [source, setSource] = useState(doc.detected_lang ?? "en");
  const [target, setTarget] = useState("es");
  const [esVariant, setEsVariant] = useState("es-419");
  const [ptVariant, setPtVariant] = useState("pt-BR");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const effectiveTarget =
    target === "es" ? esVariant : target === "pt" ? ptVariant : target;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const jobRes = await api("/api/jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          document_id: doc.id,
          source_lang: source,
          target_lang: effectiveTarget,
          model_adapter: "llamacpp",
        }),
      });
      if (!jobRes.ok) throw new Error(await errorText(jobRes));
      const job = await jobRes.json();

      const anRes = await api(`/api/jobs/${job.id}/analyze`, { method: "POST" });
      if (!anRes.ok) throw new Error(await errorText(anRes));

      const trRes = await api(`/api/jobs/${job.id}/translate`, { method: "POST" });
      if (!trRes.ok) throw new Error(await errorText(trRes));

      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  };

  const padding = compact ? "px-4 py-3" : "px-5 py-4";

  return (
    <div
      className={`${padding} bg-zinc-50 dark:bg-zinc-900/40 border-t border-zinc-200 dark:border-zinc-800 space-y-3`}
    >
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <LanguageSelect label="From" value={source} onChange={setSource} />
        <LanguageSelect label="To" value={target} onChange={setTarget} />
        {target === "es" && (
          <VariantSelect
            label="Spanish variant"
            value={esVariant}
            onChange={setEsVariant}
            options={SPANISH_VARIANTS}
          />
        )}
        {target === "pt" && (
          <VariantSelect
            label="Portuguese variant"
            value={ptVariant}
            onChange={setPtVariant}
            options={PORTUGUESE_VARIANTS}
          />
        )}
      </div>
      {doc.detected_lang && doc.detected_lang !== source && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          Detected source language is <strong>{doc.detected_lang}</strong> —{" "}
          <button
            type="button"
            onClick={() => setSource(doc.detected_lang!)}
            className="underline"
          >
            switch
          </button>
          .
        </p>
      )}
      <div className="flex gap-2 items-center">
        <button
          type="button"
          disabled={busy}
          onClick={run}
          className="px-4 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-medium disabled:opacity-50 hover:bg-emerald-500"
        >
          {busy ? "Starting…" : `Translate → ${effectiveTarget}`}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-full border border-zinc-300 dark:border-zinc-700 text-xs"
          >
            Dismiss
          </button>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    </div>
  );
}

/** Renders all versions of a document (QUEUED / translating / done / failed). */
export function VersionList({
  jobs,
  onChange,
}: {
  jobs: JobRow[];
  onChange: () => void;
}) {
  if (jobs.length === 0) {
    return (
      <p className="px-4 py-3 text-xs text-zinc-500 border-t border-zinc-200 dark:border-zinc-800">
        No translations yet.
      </p>
    );
  }
  return (
    <ul className="border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50/40 dark:bg-zinc-900/20 divide-y divide-zinc-200 dark:divide-zinc-800">
      {jobs.map((j) => (
        <VersionRow key={j.id} job={j} onChange={onChange} />
      ))}
    </ul>
  );
}

function VersionRow({ job, onChange }: { job: JobRow; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const active = !TERMINAL.has(job.status);
  const progress =
    job.chunk_count > 0
      ? Math.round((job.translated_chunks / job.chunk_count) * 100)
      : 0;

  const cancel = async () => {
    setBusy(true);
    try {
      await api(`/api/jobs/${job.id}/cancel`, { method: "POST" });
      onChange();
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="px-4 py-2 flex items-center gap-3 flex-wrap">
      <span className="text-xs font-mono">
        {job.source_lang} → {job.target_lang}
      </span>
      <span
        className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded ${
          job.status === "done"
            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
            : job.status === "failed" || job.status === "rejected"
              ? "bg-red-500/15 text-red-700 dark:text-red-300"
              : "bg-blue-500/15 text-blue-700 dark:text-blue-300"
        }`}
      >
        {STATUS_LABEL[job.status] ?? job.status}
      </span>
      {active && (
        <span className="text-xs text-zinc-500">
          {job.translated_chunks}/{job.chunk_count} · {progress}%
        </span>
      )}
      <div className="flex-1" />
      {job.status === "done" && (
        <div className="flex gap-1">
          <DownloadLink jobId={job.id} fmt="md" />
          <DownloadLink jobId={job.id} fmt="docx" />
          <DownloadLink jobId={job.id} fmt="epub" />
        </div>
      )}
      {active && (
        <button
          type="button"
          disabled={busy}
          onClick={cancel}
          className="text-xs px-2 py-0.5 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          Cancel
        </button>
      )}
      {job.error && (
        <p className="w-full text-xs text-red-600 truncate">{job.error}</p>
      )}
    </li>
  );
}

function DownloadLink({ jobId, fmt }: { jobId: number; fmt: string }) {
  return (
    <a
      href={`/api/jobs/${jobId}/download?format=${fmt}`}
      download
      className="text-xs px-2 py-0.5 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800"
    >
      .{fmt}
    </a>
  );
}

function LanguageSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="block text-zinc-500 mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1.5 text-sm"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name} · {l.native}
          </option>
        ))}
      </select>
    </label>
  );
}

function VariantSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { code: string; label: string }[];
}) {
  return (
    <label className="block text-xs">
      <span className="block text-zinc-500 mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-2 py-1.5 text-sm"
      >
        {options.map((v) => (
          <option key={v.code} value={v.code}>
            {v.label}
          </option>
        ))}
      </select>
    </label>
  );
}

async function errorText(res: Response): Promise<string> {
  try {
    const j = await res.json();
    return j.detail ?? res.statusText;
  } catch {
    return res.statusText;
  }
}
