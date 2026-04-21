# Running babel workers — Mac and Linux

babel uses a **pull-worker** model: one or more machines poll
`https://api.babeltower.lat` for queued jobs, translate locally against
`llama-server`, and stream results back. Your Mac, your Ubuntu GPU box,
or both at once — the queue is atomic, workers can't step on each other.

This file documents **both** platforms side by side.

- [What the worker needs](#what-the-worker-needs)
- [macOS (Apple Silicon)](#macos-apple-silicon)
- [Linux (Ubuntu 22.04 / 24.04 + NVIDIA)](#linux-ubuntu-2204--2404--nvidia)
- [Running both at once](#running-both-at-once)
- [Verifying](#verifying)
- [Common issues](#common-issues)

---

## What the worker needs

| Requirement | Why |
|---|---|
| `llama-server` on `localhost:8080` (TranslateGemma 4B Q4_K_M or bigger) | Does the actual translation |
| `python3` ≥ 3.10 + `httpx` | Runs the `babel-worker` CLI |
| Network access to `https://api.babeltower.lat` | Polls for jobs, pushes results |
| The worker **bearer token** (matches backend's `BABEL_WORKER_TOKEN`) | Auth |

The worker does not touch disk beyond its log files and does not
download models — that's llama-server's job.

---

## macOS (Apple Silicon)

### 1. Install prereqs

```bash
brew install llama.cpp python@3.13
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Start llama-server (in its own Terminal / tmux pane)

```bash
llama-server -hf mradermacher/translategemma-4b-it-GGUF:Q4_K_M \
  --host 127.0.0.1 --port 8080 \
  --ctx-size 8192 --n-gpu-layers 999 --chat-template gemma
```

First run downloads the GGUF (~2.6 GB) into `~/Library/Caches/llama.cpp/`.
Metal GPU acceleration is on by default.

### 3. Install + start the worker

```bash
cd /path/to/babel
./scripts/install-worker.sh
#   Backend URL:  https://api.babeltower.lat
#   Worker token: <ask admin>
```

The installer:
- `pip install -e worker/` so the `babel-worker` CLI is on `$PATH`
- writes `~/.config/babel-worker/config.env` with your answers
- generates `~/Library/LaunchAgents/com.vortex303.babel-worker.plist` and
  loads it via `launchctl`, so the worker starts at login and restarts
  on crash

### 4. Tail the logs

```bash
tail -F ~/.local/state/babel-worker/stderr.log
```

### 5. Stop / uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.vortex303.babel-worker.plist
rm ~/Library/LaunchAgents/com.vortex303.babel-worker.plist
rm -rf ~/.config/babel-worker
```

---

## Linux (Ubuntu 22.04 / 24.04 + NVIDIA)

### 1. One-shot bootstrap (installs Node/pnpm/uv/cloudflared/llama.cpp CUDA)

```bash
cd /path/to/babel
./scripts/bootstrap-ubuntu.sh
```

Verifies the NVIDIA driver (warns if < 570 — Blackwell wants 570+),
downloads the prebuilt CUDA 13.1 llama.cpp binary to `~/bin/llama.cpp/`,
and puts it on your `PATH`. Safe to re-run.

### 2. Start llama-server (in a separate shell or tmux)

```bash
llama-server -hf mradermacher/translategemma-4b-it-GGUF:Q4_K_M \
  --host 127.0.0.1 --port 8080 \
  --ctx-size 8192 --n-gpu-layers 999 --chat-template gemma
```

Downloads into `~/.cache/huggingface/hub/` first time (~2.6 GB). CUDA
offload turns on automatically when the binary was built with
`-DGGML_CUDA=ON` (the prebuilt we installed was).

### 3. Install + start the worker

```bash
./scripts/install-worker.sh
#   Backend URL:  https://api.babeltower.lat
#   Worker token: <ask admin>
```

The installer generates a systemd **user** service at
`~/.config/systemd/user/babel-worker.service`, enables it, and starts it.

### 4. Keep it alive after logout

```bash
sudo loginctl enable-linger $USER
```

Without this, systemd tears down user services when you log out. If the
box runs headless, you want linger on.

### 5. Tail the logs

```bash
journalctl --user -u babel-worker -f
```

### 6. Stop / uninstall

```bash
systemctl --user disable --now babel-worker.service
rm ~/.config/systemd/user/babel-worker.service
systemctl --user daemon-reload
rm -rf ~/.config/babel-worker
```

---

## Running both at once

Totally fine. Each box:

- installs its own `~/.config/babel-worker/config.env` with the same token
- gets a stable `BABEL_WORKER_ID` based on its MAC address, so the admin
  panel distinguishes them
- polls `/api/worker/claim-next` independently

Behavior:
- **Different jobs** go to whichever worker polls next. If the Ubuntu box
  has a bigger GPU, it'll burn through jobs faster and naturally take
  more of them.
- **Same job** can never be claimed by two workers — `claim-next` uses
  `SELECT … FOR UPDATE SKIP LOCKED` on Postgres.
- **Within a single job**, one worker handles all chunks sequentially
  (keeps cross-chunk context coherent).

To prefer one machine: don't run llama-server on the other. The worker
will still poll, fail on the first translate attempt (marking the job
FAILED), which is obnoxious. Better to just stop the worker on the box
you don't want to use:

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/com.vortex303.babel-worker.plist
# Linux
systemctl --user stop babel-worker
```

Start it again when you want that box in the pool.

---

## Verifying

After installing, give the worker 30 seconds then:

```bash
curl -sS https://api.babeltower.lat/admin/health \
  -H "X-Admin-Code: <your-admin-code>" | jq .workers
```

Should list your machine with `last_seen` within the last minute:

```json
[
  {
    "worker_id": "worker-3c22fba1c234",
    "hostname": "blackwell-box",
    "gpu": null,
    "tokens_per_second": null,
    "current_job_id": null,
    "last_seen": "2026-04-21T17:05:12.000000",
    "fly_region": "iad",
    "fly_machine": "68347eeb6799d8"
  }
]
```

`fly_region` / `fly_machine` are the backend side — which Fly machine
received the heartbeat, not the worker's location.

---

## Common issues

**Admin panel shows `llama_server: ok: false`**
That check runs on the **Fly backend**, looking for a local llama-server.
It's always false on Fly (no GPU). You can ignore it. What you actually
care about is each worker's own llama-server, which the worker checks at
startup and on every chunk — failures show up as the job going FAILED
with "llama-server" in the error.

**`404` on `/api/jobs` right after Fly was idle**
The Fly machine auto-stops when idle (free tier). First request after
wake can 502/404 for ~3–5 seconds. Retry and it's fine.

**Multiple workers, only one seems to run**
Expected for a short queue — the first worker to poll grabs the job,
runs it to completion. The second one sits idle (polling, heartbeating)
until the next job shows up. Upload more documents to see parallelism.

**Translations come back as echoed English + random code**
`llama-server` is missing the right chat template. `dev.sh` and the
raw command above include `--chat-template gemma` which is load-bearing
— TranslateGemma's embedded Jinja template strips out the translation
instruction, and the model falls back to autocomplete mode.
