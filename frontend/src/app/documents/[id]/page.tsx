import Link from "next/link";
import { notFound } from "next/navigation";

import { AnalyzePanel } from "./_analyze-panel";

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

async function fetchDocument(id: string): Promise<Document | null> {
  const origin =
    process.env.NEXT_PUBLIC_BABEL_BACKEND ?? "http://127.0.0.1:8765";
  const res = await fetch(`${origin}/documents/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) return null;
  return (await res.json()) as Document;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default async function DocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const doc = await fetchDocument(id);
  if (!doc) notFound();

  return (
    <div className="flex flex-col flex-1 bg-zinc-50 dark:bg-black">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <Link
              href="/"
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

      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-10">
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Words" value={doc.word_count.toLocaleString()} />
          <Stat label="Tokens" value={doc.token_count.toLocaleString()} />
          <Stat label="Chapters" value={doc.page_count.toLocaleString()} />
          <Stat label="Size" value={formatBytes(doc.size_bytes)} />
        </section>

        <AnalyzePanel
          documentId={doc.id}
          detectedLang={doc.detected_lang}
          detectedLangConfidence={doc.detected_lang_confidence}
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
