# Deploy babel on Ubuntu (serve babeltower.lat from your GPU box)

Three commands between cloning the repo and your model being reachable at
`https://babeltower.lat`.

Prereqs (what you need already working):
- Ubuntu 22.04 or 24.04 with `sudo`
- NVIDIA driver 570+ (check with `nvidia-smi`)
- The `babeltower.lat` DNS zone in the same Cloudflare account
- SSH key authorized on the `vortex-303` GitHub account

---

## The three commands

```bash
# 1. Clone
git clone git@github.com:vortex-303/babel.git
cd babel

# 2. Install every dependency (Node, pnpm, uv, llama.cpp CUDA build,
#    cloudflared, Python venv). Idempotent — safe to re-run.
./scripts/bootstrap-ubuntu.sh

# 3. Set your admin code, then set up the public tunnel
$EDITOR .env                           # set BABEL_ADMIN_CODE=pancho41
./scripts/tunnel-setup.sh              # one-time; prompts for browser login

# 4. Start serving
./scripts/serve.sh                     # foreground; Ctrl+C stops everything
```

After step 4 the Vercel landing at `https://babeltower.lat/app` proxies
through your tunnel to the backend on your GPU box.

---

## What each script does

### `bootstrap-ubuntu.sh`

- Verifies NVIDIA driver version (warns if below 570, won't install — too
  risky to touch without confirmation).
- `apt install`s base packages (`git`, `curl`, `unzip`, `jq`, `build-essential`,
  `libcudart12`, `libcublas12`).
- Installs Node 20 via NodeSource if missing.
- Installs pnpm globally via npm.
- Installs uv (Python package manager).
- Downloads the **latest llama.cpp CUDA-13.1 prebuilt** from GitHub
  releases and extracts to `~/bin/llama.cpp/`. Adds `build/bin` to PATH in
  `~/.bashrc`.
- Installs cloudflared from Cloudflare's apt repo.
- Calls `./setup.sh` to create `backend/.venv` and install Python + Node deps.
- Copies `.env.example` → `.env` if no `.env` exists yet.

Env overrides:
```bash
LLAMACPP_RELEASE_TAG=b8864 CUDA_VARIANT=12.4 ./scripts/bootstrap-ubuntu.sh
```

### `tunnel-setup.sh`

- Logs in to Cloudflare (opens a browser; one-time).
- Creates a tunnel named `babel` if it doesn't exist.
- Writes `~/.cloudflared/config.yml` mapping `api.babeltower.lat` →
  `http://127.0.0.1:8765`.
- Runs `cloudflared tunnel route dns` to point the hostname at the tunnel.
- Validates the config before exiting.

To run cloudflared as a systemd service (starts on boot):
```bash
./scripts/tunnel-setup.sh --service
```

To use a different hostname or port:
```bash
./scripts/tunnel-setup.sh --hostname api.example.com --port 8765
```

### `serve.sh`

- Sources `.env` so `BABEL_ADMIN_CODE` is in scope.
- Starts cloudflared in the background (if not already running as a service).
- Runs `./dev.sh` which brings up llama-server, backend, and frontend.
- Ctrl+C stops everything cleanly.

On first run, llama-server downloads the TranslateGemma 4B Q4_K_M GGUF
(~2.6 GB) into `~/.cache/huggingface/hub/`. Takes 1–5 minutes depending on
connection. Subsequent starts are instant.

---

## After the first `serve.sh`

- `https://babeltower.lat` — landing page (served by Vercel)
- `https://babeltower.lat/app` — upload UI (proxies through the tunnel)
- `https://babeltower.lat/admin` — admin panel (requires pass-code from `.env`)
- `https://api.babeltower.lat/health` — backend health, for monitoring

---

## Keeping it running

For a box that should serve 24/7, install both as services:

```bash
./scripts/tunnel-setup.sh --service     # cloudflared as systemd
# Optional: wrap dev.sh in tmux or make it a service too
tmux new-session -d -s babel './scripts/serve.sh'
```

To attach later: `tmux attach -t babel`. To stop: `tmux kill-session -t babel`.

Systemd unit for babel itself is TODO — for now tmux is the simple answer.

---

## Troubleshooting

**`llama-server: command not found` right after bootstrap**
Start a fresh shell (the installer added to `~/.bashrc`, but your current
session doesn't have it): `exec bash` or open a new terminal.

**`nvidia-smi` says "Failed to initialize NVML"**
The driver got unloaded. Reboot, then re-check before running bootstrap.

**`cloudflared tunnel login` browser URL times out**
Open the URL on a browser that's signed in to the right Cloudflare account.
If the server is headless, copy the URL from the terminal and paste into
your laptop's browser — the auth flow still works.

**DNS isn't propagating** (`curl https://api.babeltower.lat` gives NXDOMAIN)
Wait 2–5 minutes. Cloudflare usually propagates in seconds, but cold caches
take longer. `dig api.babeltower.lat @1.1.1.1` to check from the outside.

**Backend starts but `/app` shows ECONNRESET from Vercel**
Your Vercel env var `NEXT_PUBLIC_BABEL_BACKEND` must point at the tunnel
hostname (`https://api.babeltower.lat`), not `http://127.0.0.1:8765`.
Update via `vercel env rm NEXT_PUBLIC_BABEL_BACKEND production && echo
https://api.babeltower.lat | vercel env add NEXT_PUBLIC_BABEL_BACKEND
production`, then redeploy.

**Translations are gibberish (echoed English + random Python)**
`llama-server` is running with the wrong chat template. Verify
`ps aux | grep llama-server` shows NO `--chat-template` flag — if it does,
the template strips TranslateGemma's training instructions. `dev.sh`
already has this fix; confirm no one edited it.
