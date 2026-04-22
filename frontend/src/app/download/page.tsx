import Link from "next/link";

export const metadata = {
  title: "Download babel for Mac",
  description:
    "Run book-scale translations on your own Mac. Unsigned, open-source .app — drag to Applications and go.",
};

// Points at the latest GitHub release asset. We rename the release zip on
// every push, so keeping this in one place makes the upgrade cheap.
const MAC_LATEST_URL =
  "https://github.com/vortex-303/babel/releases/latest/download/babel-macos-arm64.zip";

export default function DownloadPage() {
  return (
    <div className="min-h-screen bg-white text-zinc-900 dark:bg-black dark:text-zinc-100">
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-black/80 backdrop-blur sticky top-0 z-20">
        <div className="max-w-4xl mx-auto px-6 py-3 flex items-center justify-between">
          <Link href="/" className="text-lg font-bold tracking-tight">
            <span className="text-emerald-600">babel</span>
          </Link>
          <Link
            href="/app"
            className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            Or use babel in your browser →
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-20">
        <div className="text-center mb-10">
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
            Download babel for Mac
          </h1>
          <p className="mt-4 text-lg text-zinc-600 dark:text-zinc-400">
            Run book-scale translations on your own Mac. No ChatGPT, no DeepL,
            no quotas. Your GPU, your files.
          </p>
        </div>

        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 p-8 text-center">
          <a
            href={MAC_LATEST_URL}
            className="inline-flex items-center gap-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-base px-8 py-4 rounded-full transition-colors"
          >
            <AppleIcon className="w-5 h-5" />
            Download babel · macOS (Apple Silicon)
          </a>
          <p className="mt-4 text-xs text-zinc-500">
            ~150 MB · requires macOS 11 or later · open-source, unsigned build
          </p>
        </div>

        <section className="mt-12 grid gap-4 md:grid-cols-3">
          <Step n="1" title="Unzip + drag to Applications">
            The download is a <code>.zip</code>. Unzip it and drag{" "}
            <code>babel.app</code> into your <code>/Applications</code> folder.
          </Step>
          <Step n="2" title="Right-click → Open">
            First launch only: right-click (or Control-click) <code>babel.app</code>{" "}
            in Finder and choose <strong>Open</strong>. macOS asks once; click{" "}
            <strong>Open</strong>. It's remembered forever.
          </Step>
          <Step n="3" title="Paste your access token">
            babel asks for your worker token (admin gives you this). Pasted,
            saved, babel's tower icon appears in the menu bar, and it starts
            polling for jobs.
          </Step>
        </section>

        <section className="mt-16 max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold tracking-tight mb-4">
            Why not signed / notarized?
          </h2>
          <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed">
            Apple Developer Program enrollment is $99/year, and signing/notarizing
            binds the binary to a specific identity that's trivially fakeable
            anyway. We're open-source: the entire build process lives in{" "}
            <code>packaging/mac/build.sh</code> on{" "}
            <a
              href="https://github.com/vortex-303/babel"
              className="underline hover:text-emerald-600"
            >
              our GitHub
            </a>
            , and the hash of the zip we publish is reproducible from the commit
            that built it. Don't trust us — verify.
          </p>

          <p className="mt-4 text-zinc-600 dark:text-zinc-400 leading-relaxed">
            The one-time right-click → Open step is Gatekeeper doing its job:
            making sure you <em>want</em> to run a binary you downloaded. Once
            you say yes once, macOS remembers. Subsequent launches are normal.
          </p>
        </section>

        <section className="mt-16 max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold tracking-tight mb-4">
            Linux / Windows?
          </h2>
          <p className="text-zinc-600 dark:text-zinc-400">
            Not yet packaged, but the same worker runs on both. See{" "}
            <Link href="https://github.com/vortex-303/babel" className="underline hover:text-emerald-600">
              the repo
            </Link>{" "}
            for the script-based install (<code>scripts/install-worker.sh</code>
            ). Native installers are on the roadmap.
          </p>
        </section>
      </main>

      <footer className="border-t border-zinc-200 dark:border-zinc-800 py-8 text-center text-xs text-zinc-500">
        <Link href="/" className="underline hover:text-zinc-700 dark:hover:text-zinc-300">
          back to babeltower.lat
        </Link>
      </footer>
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-xl p-5 bg-white dark:bg-zinc-950">
      <div className="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-sm mb-3">
        {n}
      </div>
      <h3 className="font-semibold mb-2">{title}</h3>
      <p className="text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
        {children}
      </p>
    </div>
  );
}

function AppleIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
    </svg>
  );
}
