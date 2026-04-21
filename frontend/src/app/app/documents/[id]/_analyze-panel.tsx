"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  LANGUAGES,
  PORTUGUESE_VARIANTS,
  SPANISH_VARIANTS,
} from "@/app/_lib/languages";
import { api } from "@/app/_lib/admin";

type ChunkPreview = { idx: number; tokens: number; preview: string };

type AnalyzeResult = {
  id: number;
  status: string;
  model_adapter: string;
  model_name: string;
  source_lang: string;
  target_lang: string;
  chunk_count: number;
  translated_chunks: number;
  estimated_seconds: number | null;
  estimated_cost_usd: number | null;
  error: string | null;
  analysis: {
    total_tokens: number;
    tokens_per_second: number;
    adapter_label: string;
    chunk_preview: ChunkPreview[];
  };
};

type JobStatus = {
  id: number;
  status: string;
  chunk_count: number;
  translated_chunks: number;
  error: string | null;
};

type JobChunk = {
  idx: number;
  tokens: number;
  source_preview: string;
  translated: string | null;
};

type GlossaryEntry = {
  id: number | null;
  source_term: string;
  target_term: string | null;
  notes: string | null;
  locked: boolean;
  occurrences: number;
};

const ADAPTERS: { value: string; label: string }[] = [
  { value: "llamacpp", label: "llama.cpp (local)" },
  { value: "ollama", label: "Ollama (local)" },
  { value: "gemini", label: "Gemini 2.5 Pro" },
  { value: "claude", label: "Claude Sonnet 4.6" },
];

const TERMINAL = new Set(["done", "failed"]);

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export function AnalyzePanel({
  documentId,
  detectedLang,
  detectedLangConfidence,
}: {
  documentId: number;
  detectedLang?: string | null;
  detectedLangConfidence?: number | null;
}) {
  const [adapter, setAdapter] = useState<string>("llamacpp");
  const [source, setSource] = useState(detectedLang ?? "en");
  const [target, setTarget] = useState("es");
  const [esVariant, setEsVariant] = useState("es-419");
  const [ptVariant, setPtVariant] = useState("pt-BR");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);

  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [chunks, setChunks] = useState<JobChunk[] | null>(null);
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);
  const [cancelBusy, setCancelBusy] = useState(false);
  const pollRef = useRef<number | null>(null);

  const [glossary, setGlossary] = useState<GlossaryEntry[] | null>(null);
  const [glossaryBusy, setGlossaryBusy] = useState(false);
  const [glossaryError, setGlossaryError] = useState<string | null>(null);

  // Resolve the actual target_lang sent to the backend — if user picks es/pt,
  // use the selected variant so the backend + system prompt see e.g. "es-AR".
  const effectiveTarget = useMemo(() => {
    if (target === "es") return esVariant;
    if (target === "pt") return ptVariant;
    return target;
  }, [target, esVariant, ptVariant]);

  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    setJobStatus(null);
    setChunks(null);
    try {
      const jobRes = await api("/api/jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          document_id: documentId,
          source_lang: source,
          target_lang: effectiveTarget,
          model_adapter: adapter,
        }),
      });
      if (!jobRes.ok) throw new Error(await errorText(jobRes));
      const job = await jobRes.json();

      const analyzeRes = await api(`/api/jobs/${job.id}/analyze`, {
        method: "POST",
      });
      if (!analyzeRes.ok) throw new Error(await errorText(analyzeRes));
      const data: AnalyzeResult = await analyzeRes.json();
      setResult(data);
      setJobStatus({
        id: data.id,
        status: data.status,
        chunk_count: data.chunk_count,
        translated_chunks: data.translated_chunks,
        error: data.error,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "analyze failed");
    } finally {
      setBusy(false);
    }
  };

  const lastTranslatedCount = useRef(-1);

  const pollOnce = useCallback(async (jobId: number) => {
    try {
      const res = await api(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error(await errorText(res));
      const data: JobStatus = await res.json();
      setJobStatus(data);

      const terminal = TERMINAL.has(data.status);
      const progressed = data.translated_chunks !== lastTranslatedCount.current;

      // Refetch chunks whenever progress moves forward, or when the job ends.
      // Lets the user watch translations land in real time, not just at the end.
      if (terminal || progressed) {
        lastTranslatedCount.current = data.translated_chunks;
        const chunksRes = await api(`/api/jobs/${jobId}/chunks`);
        if (chunksRes.ok) {
          const cdata: JobChunk[] = await chunksRes.json();
          setChunks(cdata);
        }
      }

      if (terminal && pollRef.current != null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (e) {
      setTranslateError(e instanceof Error ? e.message : "poll failed");
    }
  }, []);

  const startTranslation = async () => {
    if (!result) return;
    setTranslating(true);
    setTranslateError(null);
    setChunks(null);
    try {
      const res = await api(`/api/jobs/${result.id}/translate`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await errorText(res));
      const data: JobStatus = await res.json();
      setJobStatus(data);
      if (pollRef.current != null) clearInterval(pollRef.current);
      pollRef.current = window.setInterval(() => {
        void pollOnce(result.id);
      }, 2000);
    } catch (e) {
      setTranslateError(e instanceof Error ? e.message : "translate failed");
      setTranslating(false);
    }
  };

  const extractGlossary = async () => {
    if (!result) return;
    setGlossaryBusy(true);
    setGlossaryError(null);
    try {
      const res = await api(`/api/jobs/${result.id}/extract-glossary`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await errorText(res));
      setGlossary((await res.json()) as GlossaryEntry[]);
    } catch (e) {
      setGlossaryError(e instanceof Error ? e.message : "extract failed");
    } finally {
      setGlossaryBusy(false);
    }
  };

  const saveGlossary = async () => {
    if (!result || !glossary) return;
    setGlossaryBusy(true);
    setGlossaryError(null);
    try {
      const res = await api(`/api/jobs/${result.id}/glossary`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ entries: glossary }),
      });
      if (!res.ok) throw new Error(await errorText(res));
      setGlossary((await res.json()) as GlossaryEntry[]);
    } catch (e) {
      setGlossaryError(e instanceof Error ? e.message : "save failed");
    } finally {
      setGlossaryBusy(false);
    }
  };

  const updateGlossaryTarget = (idx: number, target: string) => {
    setGlossary((prev) => {
      if (!prev) return prev;
      const next = [...prev];
      next[idx] = { ...next[idx], target_term: target || null };
      return next;
    });
  };

  const cancelTranslation = async () => {
    if (!result) return;
    setCancelBusy(true);
    setTranslateError(null);
    try {
      const res = await api(`/api/jobs/${result.id}/cancel`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await errorText(res));
      const data: JobStatus = await res.json();
      setJobStatus(data);
      setTranslating(false);
      if (pollRef.current != null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (e) {
      setTranslateError(e instanceof Error ? e.message : "cancel failed");
    } finally {
      setCancelBusy(false);
    }
  };

  useEffect(() => {
    return () => {
      if (pollRef.current != null) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    // Optimistic "translating" flag only represents the click → poll-starts
    // window; the real state lives in jobStatus.status. Clear it as soon as
    // the server confirms the job has moved past the awaiting/starting
    // phase so we don't show "Translating…" over a queued job.
    if (
      jobStatus &&
      jobStatus.status !== "awaiting_glossary_review"
    ) {
      setTranslating(false);
    }
  }, [jobStatus]);

  const percent =
    jobStatus && jobStatus.chunk_count > 0
      ? Math.round((jobStatus.translated_chunks / jobStatus.chunk_count) * 100)
      : 0;

  const isDone = jobStatus?.status === "done";
  const isFailed = jobStatus?.status === "failed";
  const isQueued =
    jobStatus?.status === "queued" || jobStatus?.status === "pending_approval";
  const isTranslating = jobStatus?.status === "translating";
  // Button is locked during any active state; also briefly during the
  // optimistic local `translating` flag right after the click.
  const buttonLocked = translating || isQueued || isTranslating;
  // Cancel works for queued, pending-approval, and translating jobs — all
  // pre-terminal states.
  const canCancel = isQueued || isTranslating;

  return (
    <section className="mt-8 rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-6">
      <h2 className="text-base font-medium mb-4">Analyze translation job</h2>
      {detectedLang && detectedLang !== source && (
        <div className="mb-4 rounded-md border border-amber-400/40 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">
          We detected the document language as{" "}
          <strong>{detectedLang}</strong>
          {detectedLangConfidence != null && (
            <> (confidence {Math.round(detectedLangConfidence * 100)}%)</>
          )}
          , but you have <strong>From</strong> set to{" "}
          <strong>{source}</strong>. Translation will run the wrong direction
          unless you switch{" "}
          <button
            type="button"
            onClick={() => setSource(detectedLang)}
            className="underline font-medium"
          >
            From → {detectedLang}
          </button>
          .
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <Field label="From">
          <LanguageSelect value={source} onChange={setSource} />
        </Field>
        <Field label="To">
          <LanguageSelect value={target} onChange={setTarget} />
        </Field>
        {target === "es" && (
          <Field label="Spanish variant" className="lg:col-span-2">
            <select
              value={esVariant}
              onChange={(e) => setEsVariant(e.target.value)}
              className={selectCls}
            >
              {SPANISH_VARIANTS.map((v) => (
                <option key={v.code} value={v.code}>
                  {v.label}
                </option>
              ))}
            </select>
          </Field>
        )}
        {target === "pt" && (
          <Field label="Portuguese variant" className="lg:col-span-2">
            <select
              value={ptVariant}
              onChange={(e) => setPtVariant(e.target.value)}
              className={selectCls}
            >
              {PORTUGUESE_VARIANTS.map((v) => (
                <option key={v.code} value={v.code}>
                  {v.label}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field
          label="Adapter"
          className={
            target === "es" || target === "pt" ? "lg:col-span-4" : "lg:col-span-2"
          }
        >
          <select
            value={adapter}
            onChange={(e) => setAdapter(e.target.value)}
            className={selectCls}
          >
            {ADAPTERS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={run}
        className="px-5 py-2 rounded-full bg-zinc-900 text-white text-sm font-medium disabled:opacity-50 dark:bg-white dark:text-black"
      >
        {busy ? "Analyzing…" : "Analyze"}
      </button>
      {error && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      {result && (
        <div className="mt-6 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MiniStat label="Chunks" value={result.chunk_count.toLocaleString()} />
            <MiniStat
              label="Tokens"
              value={result.analysis.total_tokens.toLocaleString()}
            />
            <MiniStat
              label="ETA"
              value={formatDuration(result.estimated_seconds)}
            />
            <MiniStat
              label="Est. cost"
              value={
                result.estimated_cost_usd == null ||
                result.estimated_cost_usd === 0
                  ? "$0.00"
                  : `$${result.estimated_cost_usd.toFixed(2)}`
              }
            />
          </div>
          <p className="text-xs text-zinc-500">
            {result.analysis.adapter_label} · ~
            {Math.round(result.analysis.tokens_per_second)} tok/s · job #
            {result.id} · {result.source_lang} → {result.target_lang} · status{" "}
            <span className="font-medium">
              {jobStatus?.status ?? result.status}
            </span>
          </p>

          <div className="pt-4 border-t border-zinc-200 dark:border-zinc-800 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium">
                Glossary{" "}
                <span className="text-xs text-zinc-500 font-normal">
                  (review before translation for consistent names)
                </span>
              </h3>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={glossaryBusy}
                  onClick={extractGlossary}
                  className="px-3 py-1.5 rounded-full border border-zinc-300 dark:border-zinc-700 text-xs font-medium disabled:opacity-50 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                >
                  {glossaryBusy
                    ? "Working…"
                    : glossary
                      ? "Re-extract"
                      : "Extract terms"}
                </button>
                {glossary && glossary.length > 0 && (
                  <button
                    type="button"
                    disabled={glossaryBusy}
                    onClick={saveGlossary}
                    className="px-3 py-1.5 rounded-full bg-zinc-900 text-white text-xs font-medium disabled:opacity-50 dark:bg-white dark:text-black"
                  >
                    Save
                  </button>
                )}
              </div>
            </div>
            {glossaryError && (
              <p className="text-sm text-red-600 dark:text-red-400">
                {glossaryError}
              </p>
            )}
            {glossary && glossary.length > 0 && (
              <div className="max-h-80 overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-800">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-50 dark:bg-zinc-900 text-xs uppercase tracking-wide text-zinc-500">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium w-10">#</th>
                      <th className="text-left px-3 py-2 font-medium">Source</th>
                      <th className="text-left px-3 py-2 font-medium">
                        Target ({target})
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {glossary.map((g, i) => (
                      <tr
                        key={g.source_term + i}
                        className="border-t border-zinc-200 dark:border-zinc-800"
                      >
                        <td className="px-3 py-1.5 text-xs text-zinc-500">
                          {g.occurrences}×
                        </td>
                        <td className="px-3 py-1.5">{g.source_term}</td>
                        <td className="px-3 py-1.5">
                          <input
                            value={g.target_term ?? ""}
                            onChange={(e) =>
                              updateGlossaryTarget(i, e.target.value)
                            }
                            placeholder="(leave blank to let model decide)"
                            className="w-full bg-transparent border-b border-transparent focus:border-zinc-400 dark:focus:border-zinc-600 focus:outline-none py-0.5 text-sm"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {glossary && glossary.length === 0 && (
              <p className="text-xs text-zinc-500">
                No recurring capitalized terms found. Short docs or highly
                narrative text often lack glossary candidates.
              </p>
            )}
          </div>

          <div className="pt-4 border-t border-zinc-200 dark:border-zinc-800 flex flex-wrap gap-2 items-center">
            <button
              type="button"
              disabled={buttonLocked || cancelBusy}
              onClick={startTranslation}
              className="px-5 py-2 rounded-full bg-emerald-600 text-white text-sm font-medium disabled:opacity-50 hover:bg-emerald-500"
            >
              {isDone
                ? "Translate again"
                : isTranslating
                  ? "Translating…"
                  : jobStatus?.status === "pending_approval"
                    ? "Waiting for admin approval…"
                    : jobStatus?.status === "queued"
                      ? "Queued — waiting for worker…"
                      : "Start translation"}
            </button>
            {canCancel && (
              <button
                type="button"
                disabled={cancelBusy}
                onClick={cancelTranslation}
                className="px-5 py-2 rounded-full border border-zinc-300 dark:border-zinc-700 text-sm font-medium disabled:opacity-50 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                {cancelBusy ? "Canceling…" : "Cancel"}
              </button>
            )}
            {isDone && (
              <div className="flex flex-wrap gap-2">
                <DownloadButton jobId={result.id} format="md" />
                <DownloadButton jobId={result.id} format="docx" />
                <DownloadButton jobId={result.id} format="epub" />
              </div>
            )}
            {translateError && (
              <p className="w-full mt-2 text-sm text-red-600 dark:text-red-400">
                {translateError}
              </p>
            )}
          </div>

          {jobStatus && jobStatus.status !== "awaiting_glossary_review" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-zinc-500">
                <span>
                  {isQueued
                    ? `Waiting for a worker · ${jobStatus.chunk_count} chunks ready`
                    : `${jobStatus.translated_chunks} / ${jobStatus.chunk_count} chunks`}
                </span>
                <span>{isQueued ? "queued" : `${percent}%`}</span>
              </div>
              <div className="h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    jobStatus.status === "failed"
                      ? "bg-red-500"
                      : jobStatus.status === "done"
                        ? "bg-emerald-500"
                        : "bg-emerald-400"
                  }`}
                  style={{ width: `${percent}%` }}
                />
              </div>
              {jobStatus.error && (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {jobStatus.error}
                </p>
              )}
            </div>
          )}

          {result.analysis.chunk_preview.length > 0 && !chunks && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wide">
                First chunks
              </h3>
              {result.analysis.chunk_preview.map((c) => (
                <div
                  key={c.idx}
                  className="rounded-md border border-zinc-200 dark:border-zinc-800 p-3"
                >
                  <div className="text-xs text-zinc-500 mb-1">
                    chunk {c.idx} · {c.tokens} tokens
                  </div>
                  <div className="text-sm text-zinc-700 dark:text-zinc-300 line-clamp-4">
                    {c.preview}
                  </div>
                </div>
              ))}
            </div>
          )}

          {chunks && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wide">
                Translated output ({chunks.length} chunks)
              </h3>
              {chunks.map((c) => (
                <div
                  key={c.idx}
                  className="rounded-md border border-zinc-200 dark:border-zinc-800 p-3 space-y-2"
                >
                  <div className="text-xs text-zinc-500">
                    chunk {c.idx} · {c.tokens} tokens
                  </div>
                  <div className="text-xs text-zinc-400 italic line-clamp-2">
                    {c.source_preview}
                  </div>
                  <div className="text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">
                    {c.translated ?? (
                      <span className="text-zinc-400">(not translated)</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
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

const selectCls =
  "w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm";

function LanguageSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={selectCls}
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.name} · {l.native}
        </option>
      ))}
    </select>
  );
}

function DownloadButton({
  jobId,
  format,
}: {
  jobId: number;
  format: "md" | "docx" | "epub";
}) {
  return (
    <a
      href={`/api/jobs/${jobId}/download?format=${format}`}
      download
      className="px-4 py-2 rounded-full border border-zinc-300 dark:border-zinc-700 text-xs font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900"
    >
      Download .{format}
    </a>
  );
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className ?? ""}`}>
      <span className="block text-xs text-zinc-500 mb-1">{label}</span>
      {children}
    </label>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="text-sm font-semibold mt-0.5">{value}</div>
    </div>
  );
}
