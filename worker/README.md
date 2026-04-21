# babel-worker

Pulls translation jobs from a remote babel backend (e.g.
`https://api.babeltower.lat`) and runs them locally against a
`llama-server` on your machine. Your GPU, their queue.

## Quick install (Mac or Linux)

```bash
cd /path/to/babel
./scripts/install-worker.sh
```

That:
- installs the `babel-worker` Python package,
- writes `~/.config/babel-worker/config.env` (prompts for backend URL + worker token),
- creates a launchd plist (Mac) or systemd unit (Linux) so the worker
  restarts on reboot and crashes.

## Manual install

```bash
cd worker
uv pip install -e .                # or: pip install -e .

cat > ~/.config/babel-worker/config.env <<'EOF'
BABEL_WORKER_BACKEND_URL=https://api.babeltower.lat
BABEL_WORKER_TOKEN=<match the backend's BABEL_WORKER_TOKEN>
BABEL_WORKER_LLAMA_HOST=127.0.0.1
BABEL_WORKER_LLAMA_PORT=8080
EOF

babel-worker
```

## What it does

Every 5 seconds:

1. `POST /api/worker/claim-next` with the bearer token.
2. If a job comes back: translate each chunk via local `llama-server`,
   `POST /api/worker/jobs/{id}/chunks/{idx}` after every chunk, send a
   heartbeat with tokens/sec. On error: `POST /api/worker/jobs/{id}/fail`.
3. When all chunks done: `POST /api/worker/jobs/{id}/done`.
4. Loop.

If `llama-server` is down, the worker still polls — it just fails the
first chunk loudly so the admin UI surfaces the outage. Fix
`llama-server`, restart the worker (or leave it — the next claim will
work once llama is back).

## Env reference

| Variable | Default | Meaning |
|---|---|---|
| `BABEL_WORKER_BACKEND_URL` | *required* | `https://api.babeltower.lat` or `http://localhost:8765` for local dev |
| `BABEL_WORKER_TOKEN` | *required* | Shared secret; matches backend's `BABEL_WORKER_TOKEN` |
| `BABEL_WORKER_LLAMA_HOST` | `127.0.0.1` | Where llama-server listens |
| `BABEL_WORKER_LLAMA_PORT` | `8080` | Ditto |
| `BABEL_WORKER_POLL_INTERVAL` | `5.0` | Seconds between `claim-next` polls when idle |
| `BABEL_WORKER_HEARTBEAT_INTERVAL` | `30.0` | Seconds between heartbeats while idle |
| `BABEL_WORKER_ID` | auto from MAC | Stable id for admin-panel visibility |
