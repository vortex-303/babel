# babel — product plan

> The durable roadmap. Committed 2026-04-21. Updated as decisions land.

---

## One-line pitch

Long-document translation without the page caps, the privacy risks, or the monthly subscription. Download a free Mac app, translate any book in any format, on your own machine.

---

## The product

### Name
**babel** (matches the repo, matches the domain `babeltower.lat`)

### Distribution

**Primary surface**: `https://babeltower.lat/download`

- **One-click download** → `.zip` containing `babel.app` (unsigned)
- User double-clicks → macOS asks them to drag to Applications → first launch, right-click → Open (Gatekeeper bypass, one-time)
- Equivalent `curl -fsSL https://babeltower.lat/install.sh | bash` for terminal-friendly users

**No Apple Developer account, no signing, no notarization.** The codebase is open-source so anyone suspicious can read it, build it themselves, or audit that the binary matches the source. That framing is the answer to "why isn't it signed?"

**App bundle layout** (~200 MB zipped):

```
babel.app/
├── Contents/
│   ├── Info.plist              # LSUIElement=true → menu-bar agent, no dock icon
│   ├── MacOS/babel             # launcher shell script: execs the bundled Python
│   └── Resources/
│       ├── python/             # embedded CPython 3.13 (~40 MB)
│       ├── site-packages/      # babel_worker[tray] + deps
│       ├── llama-server        # universal binary (ARM64 + x86_64)
│       └── icon.icns           # ziggurat tower
```

Model GGUF (~2.6 GB) is **downloaded on first run** into `~/Library/Application Support/babel/models/`, not bundled into the zip. Keeps the download small and lets users pick 4B / 12B / 27B at runtime.

### Open source

Repo flips from private to public on first `.app` release so users can verify the source matches the binary. Reproducible builds documented in `packaging/mac/README.md`.

---

## The business

### Pricing
**$10 per 100,000 words** (≈ 1 average paperback). One-off packs ($10, $50, $100) plus a `$49/month unlimited` subscription if the data supports it after 3 months.

Free tier: **10,000 words/month per account** (one sample chapter).

Admin (Nicolas): unlimited.

### Payments
Stripe Checkout for credit purchase. No contributor marketplace in v1 — that's phase G below.

### Who we sell to (ordered by first-mover fit)

1. **LATAM self-published authors** — ebooks on Amazon KDP, translating their own novels EN↔ES. Already segment 1 for `babeltower.lat` marketing. Rioplatense Spanish + Mexican Spanish regional variants are our wedge vs. DeepL's generic.
2. **Academic researchers** with corpora that can't go to OpenAI — medical records, archives, confidential interviews. Local-first + open source beats GPT-4 for these by definition.
3. **Independent human translators** using babel as a draft pass before their paid human edit — velocity multiplier at their existing rate.

---

## Privacy story — the wedge

### Local mode (the default)
Documents never leave your Mac. No telemetry beyond an opt-in weekly heartbeat. The `.app` is open source and reproducibly buildable; users can verify that no network calls happen during translation beyond `llama-server` on localhost.

### Cloud mode (if the user opts in to hosted workers in Phase G)
- Document encrypted client-side with an ephemeral key
- Ciphertext goes to Supabase Storage; babel backend cannot decrypt
- Assigned worker receives ciphertext + key via a one-shot signed URL
- Worker decrypts in-memory, translates, re-encrypts output
- Cloud is a post office, not a processor
- Retention 7d free / 30d paid, hard-delete option per document

### What's public about a user
Email + pseudonymous handle (enforced via Stripe Connect only on Phase G+). No real name requirement.

### Legal framing
Privacy policy styled around **"we are a conduit, not a processor"** — strict GDPR lane, sellable to enterprises later without rewrites.

---

## Translation quality — the "superior experience" moat

What already works:
- ✅ Chunked with token-aware splits (1500 tok, no overlap, previous-chunk translated tail as context)
- ✅ Glossary extraction + edit + prompt-injection (Alice → Alicia stays consistent across 500 pages)
- ✅ Regional Spanish variants (AR / MX / ES / US / 419)
- ✅ Language auto-detect warns if user picks the wrong direction
- ✅ Format round-trip: MD, DOCX, EPUB out

What's needed to be genuinely superior:

1. **Second-pass review** — a second LLM call per chunk checks glossary adherence, pronoun consistency, tense. ~1 week.
2. **Sentence-level alignment editor** — side-by-side source/target view in the `.app` and on web. Click to edit a sentence, decision locks to the glossary for all subsequent chunks. This is what makes a pro human translator use the tool. ~2 weeks.
3. **Model tiering** — 4B free, 12B paid, 27B + Gemini 2.5 Pro review for Pro. ~3 days once multi-adapter support lands.
4. **Format fidelity** — preserve headings, italics, footnotes through DOCX/EPUB round-trip. Currently flattened to paragraphs. ~1 week.

---

## Roadmap — phases in order

| Phase | Deliverable | State |
|---|---|---|
| A | Supabase Postgres + Storage | ✅ shipped 2026-04-21 |
| B | Fly.io backend at api.babeltower.lat | ✅ shipped 2026-04-21 |
| C | Pull-worker (CLI) with installer for Mac + Linux | ✅ shipped 2026-04-21 |
| **D** | **`babel.app` — unsigned Mac bundle, download-and-run** | **next** |
| E | Accounts (magic-link auth) + credit ledger in Postgres | |
| F | Stripe integration — purchase + balance display | |
| G | End-to-end encryption + contributor mode + Stripe Connect payouts | |
| H | Second-pass review + sentence-level editor | |
| I | Format-fidelity upgrade (headings, italics, footnotes) | |
| J | Model tiering (4B / 12B / 27B + cloud fallback) | |

Each phase is one commit boundary, not one day. D alone is ~1 week of focused work.

---

## Phase D — concrete tasks

The immediate next step. Every task is independently shippable.

1. `packaging/mac/` directory in the repo with:
   - `build-app.sh` — single script builds `babel.app` on any Mac. Downloads a relocatable CPython from [python-build-standalone](https://github.com/indygreg/python-build-standalone) → embeds it → pip-installs `worker/[tray]` + `pystray` + `Pillow` into the bundle's site-packages → copies `llama-server` from Homebrew into Resources → writes `Info.plist` with `LSUIElement=true` → zips to `babel-0.1.0-macos-arm64.zip`.
   - `Info.plist` template
   - `launcher.sh` (the `MacOS/babel` executable)
   - `first-run.py` — AppleScript dialog prompting for backend URL (default: local-only) and optional admin token. Written to `~/Library/Application Support/babel/config.env`.
   - `README.md` — how to rebuild, how to verify the shipped zip matches source (SHA256 check).

2. `scripts/release.sh` — runs `build-app.sh`, signs with ad-hoc `codesign -s -` (no developer account), zips, uploads to GitHub Releases, bumps version. Triggered by git tag.

3. `frontend/src/app/download/page.tsx` — `https://babeltower.lat/download` landing. Detects macOS in UA; shows **Download for Mac · Apple Silicon** button pointing at the latest GitHub Release asset. Linux / Windows show "coming soon" (or `curl | bash` for Linux).

4. **First-run experience** inside the app:
   - Tray appears as starting (gray dot)
   - AppleScript dialog: *"Where should babel run? [ Local only (this Mac) ] [ Contribute to babel cloud ]"*
   - If local: no config needed, prompts to download the 4B GGUF (2.6 GB)
   - If contribute: prompts for admin token (paste from `babeltower.lat/admin/worker-token` page — Phase E work; for beta the admin shares the token manually)
   - Downloads model with progress dialog
   - Spawns `llama-server` subprocess (LlamaManager already exists)
   - Spawns worker loop
   - Tray flips to green

5. **In-app UI** for the local-only user (no website required):
   - Tray menu: *"Translate a document…"* → opens a native `NSOpenPanel` → picks file → launches the local translate pipeline → progress in the tray → opens the output file when done.
   - For the first release, this is it — no glossary editor, no job history, just "drop a file and wait". The full UI lives on `babeltower.lat/app` which local-only users can still open in their browser against `http://127.0.0.1:8765` (the app boots a local babel backend on that port — same code as `./dev.sh`).

6. **Auto-update** (basic): app checks `babeltower.lat/latest-version.txt` on launch. If newer, shows a tray notification: *"babel 0.2.0 available — click to download."* Opens the download page; we don't do in-place updates in v1.

7. **Documentation**:
   - `docs/MAC-APP.md` — user-facing: "how to install", "how to bypass Gatekeeper", "where is my data".
   - `docs/BUILDING.md` — dev-facing: how to build the .app from source, reproducibly.
   - Video or gif in the landing page showing the zip → drag → open flow.

---

## Decisions already locked

(From the 2026-04-21 planning conversation.)

- Name: `babel`
- Distribution: unsigned `.app` in a `.zip` + `curl | bash` alternative
- Model: download on first run
- Pricing: $10 / 100k words
- Contributor marketplace: deferred — v1 is just "local-first Mac app that actually works"
- Apple Developer Program: **not enrolling**. Ever, unless we change our mind.
- Repo: flips to public on first `.app` release

---

## Decisions still open

- Exactly when does the repo flip to public — on Phase D ship, or later?
- Windows + Linux app distribution — Phase D+ or separate phase?
- Does the `.app` ship without admin controls and point to `babeltower.lat` for the admin panel, or bundle the admin UI too?
- Subscription vs. pure pack pricing — ship both to start, see which wins, or commit to one.

---

## What already exists (reuse for D)

- `worker/babel_worker/` — Python package with tray, adapter, loop, config, state. Already handles `--tray` mode.
- `scripts/install-worker.sh` — the CLI install flow. `build-app.sh` will reuse a lot of its logic but bundle everything into an app instead.
- `LlamaManager` class — already supervises `llama-server` as a subprocess.
- Tower icon rendering — already in `tray.py::_tower_icon()`, lift into `.icns` for the bundle.
