import Link from "next/link";

type DocumentRow = {
  id: number;
  filename: string;
  word_count: number;
  page_count: number;
  uploaded_at: string;
};

async function fetchDocuments(): Promise<DocumentRow[]> {
  const origin =
    process.env.NEXT_PUBLIC_BABEL_BACKEND ?? "http://127.0.0.1:8765";
  try {
    const res = await fetch(`${origin}/documents`, { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()) as DocumentRow[];
  } catch {
    return [];
  }
}

export async function RecentDocuments() {
  const docs = await fetchDocuments();
  if (docs.length === 0) return null;
  return (
    <section className="mt-10">
      <h2 className="text-sm font-medium text-zinc-500 mb-3">Recent uploads</h2>
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
        {docs.slice(0, 8).map((d) => (
          <li key={d.id}>
            <Link
              href={`/app/documents/${d.id}`}
              className="flex items-center justify-between px-4 py-3 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-900"
            >
              <span className="truncate">{d.filename}</span>
              <span className="text-xs text-zinc-500">
                {d.word_count.toLocaleString()} words
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
