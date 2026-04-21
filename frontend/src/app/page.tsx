import Link from "next/link";

import { UserMenu } from "./_components/user-menu";

export const metadata = {
  title: "babel — translate books locally, privately",
  description:
    "Long-document AI translation for LATAM. Upload a PDF, EPUB, or DOCX; get a polished translation in minutes. Rioplatense Spanish and other regional variants included.",
};

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white text-zinc-900 dark:bg-black dark:text-zinc-100">
      {/* ===== Header ===== */}
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-black/80 backdrop-blur sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <Link href="/" className="text-lg font-bold tracking-tight">
            <span className="text-emerald-600">babel</span>
            <span className="text-zinc-400">.</span>
            <span className="text-zinc-500 text-sm font-normal">tower</span>
          </Link>
          <nav className="hidden md:flex items-center gap-6 text-sm">
            <a
              href="#how"
              className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              How it works
            </a>
            <a
              href="#features"
              className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              Features
            </a>
            <a
              href="#privacy"
              className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              Privacy
            </a>
            <a
              href="#faq"
              className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              FAQ
            </a>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/app"
              className="hidden sm:inline-block text-zinc-900 hover:text-emerald-600 font-medium text-sm dark:text-zinc-100"
            >
              Open app
            </Link>
            <UserMenu />
          </div>
        </div>
      </header>

      {/* ===== Hero ===== */}
      <section className="max-w-6xl mx-auto px-6 py-20 md:py-28">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 text-xs font-mono px-3 py-1 rounded-full mb-6">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
            LATAM · self-hosted LLM · glossary-locked
          </div>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-[1.05]">
            Translate a whole book{" "}
            <span className="text-emerald-600">without the 50-page cap</span>.
          </h1>
          <p className="mt-6 text-lg text-zinc-600 dark:text-zinc-400 leading-relaxed">
            Drop a PDF, EPUB, or DOCX. babel runs an open-source translation
            model on a real GPU, locks your proper nouns so names stay
            consistent across chapters, and emits a clean{" "}
            <code className="text-sm">.docx</code> or{" "}
            <code className="text-sm">.epub</code>. Spanish (Argentina),
            Spanish (Mexico), Portuguese (Brazil) and 37 other languages
            with proper regional flavor.
          </p>
          <div className="mt-8 flex gap-3 flex-wrap">
            <Link
              href="/app"
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm px-6 py-3 rounded-full transition-colors"
            >
              Start translating →
            </Link>
            <a
              href="#how"
              className="bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-semibold text-sm px-6 py-3 rounded-full"
            >
              See how it works
            </a>
          </div>
          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-xs text-zinc-500">
            {[
              "No page caps",
              "Glossary review",
              "es-AR · es-MX · es-ES",
              "Runs on your GPU",
            ].map((claim) => (
              <span key={claim} className="flex items-center gap-1.5">
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="w-3.5 h-3.5 text-emerald-600"
                >
                  <path
                    fillRule="evenodd"
                    d="M16.704 5.293a1 1 0 0 1 0 1.414l-7.5 7.5a1 1 0 0 1-1.414 0l-3.5-3.5a1 1 0 0 1 1.414-1.414L8.5 12.086l6.79-6.793a1 1 0 0 1 1.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
                {claim}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ===== How it works ===== */}
      <section
        id="how"
        className="bg-zinc-50 dark:bg-zinc-950 border-y border-zinc-200 dark:border-zinc-800 py-20"
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
              Three steps, one coffee.
            </h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              Most books finish before your third refill.
            </p>
          </div>
          <ol className="grid md:grid-cols-3 gap-4">
            {[
              {
                n: "1",
                t: "Upload",
                b: "PDF, EPUB, DOCX, TXT, or Markdown. We parse the layout, count tokens, and detect the source language.",
              },
              {
                n: "2",
                t: "Review the glossary",
                b: "babel pulls recurring proper nouns and lets you fix how each one should be translated — Alice → Alicia, not Alisha.",
              },
              {
                n: "3",
                t: "Translate + download",
                b: "Chunks run sequentially with the previous passage as context. Pick your output format when it's done.",
              },
            ].map((step) => (
              <li
                key={step.n}
                className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-6"
              >
                <div className="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold mb-4">
                  {step.n}
                </div>
                <h3 className="font-bold mb-1">{step.t}</h3>
                <p className="text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
                  {step.b}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ===== Features ===== */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-20">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            What the others don&apos;t do.
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            {
              t: "Regional Spanish that actually sounds regional",
              b: "Pick rioplatense, Mexican, Peninsular, or LATAM-neutral. babel injects the right register — voseo, vocabulary, idioms — into every chunk's prompt.",
            },
            {
              t: "Glossary lock",
              b: "Review proper nouns before the long run. Your character names stay spelled the same way from page 1 to page 500.",
            },
            {
              t: "No page or word caps",
              b: "DeepL caps you at a handful of pages per month. BookTranslator stops at 50 MB. babel runs whatever fits on disk.",
            },
            {
              t: "Real file formats, not plain text",
              b: "Drop a DOCX with headings, get a DOCX back. EPUBs preserve chapters. Markdown in, Markdown out.",
            },
            {
              t: "Local or cloud, your call",
              b: "Run on our GPU while it's free, or plug in your own llama.cpp / OpenRouter key. Your text never touches a training set.",
            },
            {
              t: "Priced for LATAM",
              b: "Free tier for small docs while the beta is open. Paid tiers coming soon in USD, ARS, and MXN.",
            },
          ].map((f) => (
            <div
              key={f.t}
              className="border border-zinc-200 dark:border-zinc-800 rounded-xl p-5 bg-white dark:bg-zinc-950"
            >
              <h3 className="font-bold text-sm mb-2">{f.t}</h3>
              <p className="text-zinc-600 dark:text-zinc-400 text-xs leading-relaxed">
                {f.b}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== Privacy comparison ===== */}
      <section
        id="privacy"
        className="bg-zinc-50 dark:bg-zinc-950 border-y border-zinc-200 dark:border-zinc-800 py-20"
      >
        <div className="max-w-4xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
              Your manuscript, your terms.
            </h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              Unreleased books don&apos;t belong on someone else&apos;s training set.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="border border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30 rounded-xl p-5">
              <h3 className="font-bold text-sm text-emerald-900 dark:text-emerald-300 mb-3">
                ✓ What babel does
              </h3>
              <ul className="space-y-2 text-xs text-emerald-900 dark:text-emerald-300 leading-relaxed">
                <li>· Runs the translation model on dedicated infrastructure (currently our own GPU).</li>
                <li>· Deletes your source and output files after the retention window.</li>
                <li>· Lets you self-host the entire stack — code is open on GitHub.</li>
              </ul>
            </div>
            <div className="border border-zinc-200 dark:border-zinc-800 rounded-xl p-5 bg-white dark:bg-zinc-900">
              <h3 className="font-bold text-sm mb-3">✕ What babel doesn&apos;t</h3>
              <ul className="space-y-2 text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
                <li>· Send your text to any third-party LLM API unless you explicitly opt in.</li>
                <li>· Keep your documents indefinitely.</li>
                <li>· Train a model on your uploads.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ===== FAQ ===== */}
      <section id="faq" className="max-w-3xl mx-auto px-6 py-20">
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-center mb-10">
          Frequently asked
        </h2>
        <div className="space-y-3">
          {[
            {
              q: "What model does babel use?",
              a: "Google's TranslateGemma (4B and 12B variants), benchmarked on 55 language pairs. It runs locally via llama.cpp on Metal, CUDA, or CPU.",
            },
            {
              q: "How long does a book take?",
              a: "A 300-page (~80k word) novel on a modern NVIDIA card finishes in 20–40 minutes. On an M-series Mac, about double that.",
            },
            {
              q: "Can I really use it for free?",
              a: "During the beta, yes, subject to queue limits and file-size caps. Admin-mode users (authors with a pass-code) get unlimited throughput.",
            },
            {
              q: "What if I want OpenRouter or OpenAI instead?",
              a: "Cloud adapters are stubbed — you can swap in your own API key. That route bypasses our local GPU and your text goes through the third-party provider.",
            },
            {
              q: "Open source?",
              a: "Currently private during beta. Selected invited users can clone and self-host.",
            },
          ].map((item, i) => (
            <details
              key={i}
              className="group border border-zinc-200 dark:border-zinc-800 rounded-xl bg-white dark:bg-zinc-950 overflow-hidden"
            >
              <summary className="cursor-pointer px-5 py-4 flex items-center justify-between list-none">
                <span className="text-sm font-semibold">{item.q}</span>
                <span className="text-zinc-400 group-open:rotate-180 transition-transform">
                  ⌄
                </span>
              </summary>
              <div className="px-5 pb-4 text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {item.a}
              </div>
            </details>
          ))}
        </div>
      </section>

      {/* ===== Bottom CTA ===== */}
      <section className="bg-zinc-950 text-zinc-100 py-20">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            Ready to translate?
          </h2>
          <p className="mt-3 text-zinc-400">
            The first chapter takes about a minute. No account required to try.
          </p>
          <Link
            href="/app"
            className="inline-block mt-8 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm px-6 py-3 rounded-full"
          >
            Open babel →
          </Link>
        </div>
      </section>

      {/* ===== Footer ===== */}
      <footer className="border-t border-zinc-200 dark:border-zinc-800 py-10">
        <div className="max-w-6xl mx-auto px-6 flex flex-wrap items-center justify-between gap-4">
          <div className="text-sm">
            <span className="font-bold">
              <span className="text-emerald-600">babel</span>tower
            </span>{" "}
            <span className="text-zinc-500">— long-document translation for LATAM</span>
          </div>
          <div className="flex items-center gap-5 text-xs text-zinc-500">
            <span>Hecho en Argentina 🇦🇷</span>
            <a
              href="mailto:hello@babeltower.lat"
              className="hover:text-zinc-900 dark:hover:text-zinc-200"
            >
              Contact
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
