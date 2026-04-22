"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/app/_lib/admin";

import { DocumentVersions } from "./_versions-view";

type Document = {
  id: number;
  filename: string;
  size_bytes: number;
  page_count: number;
  word_count: number;
  token_count: number;
  detected_lang: string | null;
  detected_lang_confidence: number | null;
  uploaded_at: string;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentDetailClient({ id }: { id: number }) {
  const [doc, setDoc] = useState<Document | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing">(
    "loading",
  );

  const load = useCallback(async () => {
    try {
      const res = await api(`/api/documents/${id}`);
      if (res.status === 404) {
        setStatus("missing");
        return;
      }
      if (!res.ok) throw new Error(res.statusText);
      setDoc((await res.json()) as Document);
      setStatus("ready");
    } catch {
      setStatus("missing");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (status === "loading") {
    return (
      <div className="min-h-screen grid place-items-center bg-zinc-50 dark:bg-black">
        <p className="text-sm text-zinc-500">Loading…</p>
      </div>
    );
  }
  if (status === "missing" || !doc) {
    return (
      <div className="min-h-screen grid place-items-center bg-zinc-50 dark:bg-black p-6">
        <div className="text-center max-w-sm space-y-3">
          <h1 className="text-xl font-semibold">Document not found</h1>
          <p className="text-sm text-zinc-500">
            It was either deleted, or uploaded from a different browser session
            (files are private to the browser that uploaded them).
          </p>
          <Link
            href="/app"
            className="inline-block text-xs text-zinc-700 dark:text-zinc-200 border border-zinc-300 dark:border-zinc-700 rounded-full px-4 py-1.5"
          >
            ← back to your files
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 bg-zinc-50 dark:bg-black">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <Link
              href="/app"
              className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
            >
              ← back
            </Link>
            <h1 className="text-xl font-semibold tracking-tight mt-1">
              {doc.filename}
            </h1>
          </div>
          <span className="text-xs text-zinc-500">
            uploaded {new Date(doc.uploaded_at).toLocaleString()}
          </span>
        </div>
      </header>

      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-10 space-y-6">
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Words" value={doc.word_count.toLocaleString()} />
          <Stat label="Tokens" value={doc.token_count.toLocaleString()} />
          <Stat label="Chapters" value={doc.page_count.toLocaleString()} />
          <Stat label="Size" value={formatBytes(doc.size_bytes)} />
        </section>

        <DocumentVersions
          doc={{
            id: doc.id,
            filename: doc.filename,
            detected_lang: doc.detected_lang,
          }}
        />
      </main>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4">
      <div className="text-xs uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}
