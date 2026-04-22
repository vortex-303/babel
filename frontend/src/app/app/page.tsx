import Link from "next/link";

import { UserMenu } from "../_components/user-menu";
import { HealthBadge } from "./_components/health-badge";
import { RecentDocuments } from "./_components/recent-documents";
import { UploadCard } from "./_components/upload-card";
import { WorkerBadge } from "./_components/worker-badge";

export default function Home() {
  return (
    <div className="flex flex-col flex-1 bg-zinc-50 dark:bg-black">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between gap-4">
          <div>
            <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-800">
              ← babeltower
            </Link>
            <h1 className="text-xl font-semibold tracking-tight mt-1">babel</h1>
            <p className="text-xs text-zinc-500">
              Long-document translation, local-first
            </p>
          </div>
          <div className="flex items-center gap-3">
            <WorkerBadge />
            <HealthBadge />
            <UserMenu />
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-12">
        <UploadCard />
        <RecentDocuments />
      </main>

      <footer className="border-t border-zinc-200 dark:border-zinc-800 py-4 text-center text-xs text-zinc-500">
        babel · Vortex303
      </footer>
    </div>
  );
}
