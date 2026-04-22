# babel for Mac — installing the app

This is the user-facing version of this guide. For the build-side details,
see [`packaging/mac/README.md`](../packaging/mac/README.md).

## Install

1. Download **babel-macos-arm64.zip** from
   [babeltower.lat/download](https://babeltower.lat/download) (or directly
   from GitHub releases).
2. Unzip. Drag `babel.app` into `/Applications`.
3. **First launch only**: right-click (or Control-click) `babel.app` →
   **Open** → confirm in the dialog. macOS remembers your approval
   forever. Subsequent launches are normal double-clicks.
4. babel asks for two things:
   - **Backend URL** — leave the default (`https://api.babeltower.lat`)
     unless you're running your own copy of the babel backend.
   - **Worker token** — paste the token from your admin. (If you're the
     admin, it's your own `BABEL_WORKER_TOKEN`.)
5. A little tower icon appears in your menu bar, top-right. Click it to
   see status + start llama-server + view recent activity.

## What the app does

The app is a **pull-worker** for babel. While it's running:

- It pings `api.babeltower.lat` every ~5 seconds for jobs to pick up.
- When a job is assigned, it downloads the source text, runs the
  translation locally against `llama-server`, and streams chunk results
  back to the babel backend.
- The first time `llama-server` runs, it downloads the TranslateGemma 4B
  GGUF (~2.6 GB) into `~/Library/Caches/llama.cpp/`. Later launches reuse
  the cached model — instant start.
- On a modern Apple Silicon Mac, translation runs at ~35-50 tokens/second
  via Metal GPU.

## Where things live

- `/Applications/babel.app` — the app bundle
- `~/.config/babel-worker/config.env` — your backend URL + token (edit
  directly to change either)
- `~/.local/state/babel-worker/stderr.log` — the worker log (via the tray
  menu: **View logs**)
- `~/Library/Caches/llama.cpp/` — downloaded model weights

## Troubleshooting

**"babel.app can't be opened because Apple cannot check it for malicious
software"**
Control-click → Open instead of double-clicking. This bypasses Gatekeeper
for this one bundle, permanently.

**Menu bar icon doesn't appear**
Quit babel (if running), then `open /Applications/babel.app` from
Terminal. Look for Python traces in
`~/.local/state/babel-worker/stderr.log`.

**`llama-server` never finishes starting**
First launch downloads ~2.6 GB. On slow connections, allow 5–15 minutes.
Click the tower icon → **View logs** to see download progress.

**Jobs queue on babeltower.lat/app but never run**
The worker only drains jobs from the account whose token you pasted. If
you're not the admin, make sure the admin's queue actually has your jobs
— they might be on a different user's silo.

**Reset everything**
```bash
launchctl unload ~/Library/LaunchAgents/com.vortex303.babel-worker.plist 2>/dev/null
rm -rf ~/.config/babel-worker ~/.local/state/babel-worker
rm -rf /Applications/babel.app
```
Re-download from babeltower.lat/download to start fresh.

## Privacy

- Documents you upload at `babeltower.lat/app` are briefly stored
  server-side while the worker processes them. They're deleted after 7
  days (longer for paid tiers; admin can purge any time).
- Documents are **not** sent to any third-party LLM provider. All
  translation happens on your (or your admin's) GPU.
- End-to-end encryption so the backend literally can't read your files
  is on the roadmap (Phase G in `PLAN.md`) and rolls in with the paid
  tier.
- The `.app` bundle is open source. The GitHub repo has the exact script
  that built the zip you downloaded — rebuild it and compare the hash if
  you're paranoid.
