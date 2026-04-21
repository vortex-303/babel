"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { api } from "@/app/_lib/admin";

type UploadResult = {
  id: number;
  filename: string;
  size_bytes: number;
  page_count: number;
  word_count: number;
  token_count: number;
};

const ACCEPT = ".epub,.pdf,.docx,.txt,.md";

export function UploadCard() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dragDepth = useRef(0);

  const upload = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      try {
        const body = new FormData();
        body.append("file", file);
        const res = await api("/api/documents", { method: "POST", body });
        if (!res.ok) {
          const detail = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(detail.detail ?? "upload failed");
        }
        const doc: UploadResult = await res.json();
        router.push(`/app/documents/${doc.id}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "upload failed");
      } finally {
        setBusy(false);
      }
    },
    [router],
  );

  return (
    <div
      onDragEnter={(e) => {
        e.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
      }}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !busy) void upload(f);
      }}
      className={`rounded-2xl border border-dashed p-12 text-center transition-colors ${
        dragging
          ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30"
          : "border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-950"
      }`}
    >
      <div className="text-lg font-medium mb-2">
        {busy ? "Uploading & ingesting…" : "Drop a document to translate"}
      </div>
      <p className="text-sm text-zinc-500 mb-6">
        EPUB · PDF · DOCX · TXT · MD — up to several hundred pages
      </p>
      <label
        className={`inline-flex items-center px-5 py-2 rounded-full text-sm font-medium transition-colors ${
          busy
            ? "bg-zinc-300 text-zinc-500 cursor-not-allowed dark:bg-zinc-800 dark:text-zinc-500"
            : "bg-zinc-900 text-white cursor-pointer hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200"
        }`}
      >
        <input
          type="file"
          accept={ACCEPT}
          disabled={busy}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void upload(f);
          }}
        />
        {busy ? "Please wait…" : "Choose file"}
      </label>
      {error && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
      <p className="mt-6 text-xs text-zinc-400">
        We&apos;ll analyze word count, estimate time &amp; cost, and let you
        review the glossary before translating.
      </p>
    </div>
  );
}
