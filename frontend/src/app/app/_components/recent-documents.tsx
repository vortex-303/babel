"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/app/_lib/admin";

import {
  TERMINAL,
  TriggerForm,
  useDocumentJobs,
  VersionList,
} from "./versions";

type DocumentRow = {
  id: number;
  filename: string;
  word_count: number;
  page_count: number;
  detected_lang: string | null;
  uploaded_at: string;
};

export function RecentDocuments() {
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api("/api/documents");
      if (!res.ok) throw new Error(res.statusText);
      setDocs((await res.json()) as DocumentRow[]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const iv = window.setInterval(refresh, 8000);
    return () => window.clearInterval(iv);
  }, [refresh]);

  if (error) {
    return (
      <section className="mt-10">
        <p className="text-sm text-red-600">Couldn't load files: {error}</p>
      </section>
    );
  }
  if (docs.length === 0) return null;

  return (
    <section className="mt-10">
      <h2 className="text-sm font-medium text-zinc-500 mb-3">Your files</h2>
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
        {docs.map((d) => (
          <FileRow key={d.id} doc={d} onDeleted={refresh} />
        ))}
      </ul>
    </section>
  );
}

function FileRow({
  doc,
  onDeleted,
}: {
  doc: DocumentRow;
  onDeleted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [jobs, refetch] = useDocumentJobs(doc.id);

  const doneVersions =
    jobs?.filter((j) => j.status === "done").map((j) => j.target_lang) ?? [];
  const activeCount =
    jobs?.filter((j) => !TERMINAL.has(j.status)).length ?? 0;

  const deleteFile = async () => {
    if (
      !confirm(
        `Delete "${doc.filename}" and all its translations? This can't be undone.`,
      )
    )
      return;
    setBusy(true);
    try {
      await api(`/api/documents/${doc.id}`, { method: "DELETE" });
      onDeleted();
    } finally {
      setBusy(false);
    }
  };

  return (
    <li>
      <div className="px-4 py-3 flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
          aria-label={open ? "Collapse" : "Expand"}
        >
          {open ? "▾" : "▸"}
        </button>
        <Link
          href={`/app/documents/${doc.id}`}
          className="text-sm flex-1 truncate hover:text-zinc-900 dark:hover:text-zinc-100"
        >
          {doc.filename}
        </Link>
        <span className="text-xs text-zinc-500 whitespace-nowrap">
          {doc.word_count.toLocaleString()} words
        </span>
        {doneVersions.length > 0 && (
          <span className="text-xs text-emerald-700 dark:text-emerald-300">
            {doneVersions.length} version{doneVersions.length > 1 ? "s" : ""}
          </span>
        )}
        {activeCount > 0 && (
          <span className="text-xs text-blue-700 dark:text-blue-300">
            {activeCount} active
          </span>
        )}
        <button
          type="button"
          onClick={() => setTriggerOpen((v) => !v)}
          className="text-xs px-3 py-1 rounded-full bg-emerald-600 text-white font-medium hover:bg-emerald-500"
        >
          {triggerOpen ? "Close" : "Translate to…"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={deleteFile}
          title="Delete file and all versions"
          className="text-xs px-2 py-1 rounded-full border border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800/50 dark:text-red-300 dark:hover:bg-red-950/30"
        >
          Delete
        </button>
      </div>

      {triggerOpen && (
        <TriggerForm
          doc={doc}
          onDone={() => {
            setTriggerOpen(false);
            setOpen(true);
            void refetch();
          }}
          onCancel={() => setTriggerOpen(false)}
          compact
        />
      )}

      {open && jobs !== null && <VersionList jobs={jobs} onChange={refetch} />}
    </li>
  );
}
