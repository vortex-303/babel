#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/jobs"
mkdir -p "$LOG_DIR"

pids=()
cleanup() {
  echo
  echo "shutting down babel…"
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

port_busy() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

# 1. llama-server (skip if :8080 already taken)
if port_busy 8080; then
  echo "• llama-server already running on :8080 — reusing"
else
  if ! command -v llama-server >/dev/null 2>&1; then
    echo "error: llama-server not found. Install with: brew install llama.cpp" >&2
    exit 1
  fi
  echo "• starting llama-server on :8080 (logs → $LOG_DIR/llama-server.log)"
  llama-server \
    -hf mradermacher/translategemma-4b-it-GGUF:Q4_K_M \
    --host 127.0.0.1 --port 8080 \
    --ctx-size 8192 \
    --n-gpu-layers 999 \
    --chat-template gemma \
    >"$LOG_DIR/llama-server.log" 2>&1 &
  pids+=($!)
fi

# 2. backend
if port_busy 8765; then
  echo "• backend already running on :8765 — reusing"
else
  if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
    echo "error: backend venv missing. Run: cd backend && uv venv && uv pip install -e ." >&2
    exit 1
  fi
  echo "• starting backend on :8765 (logs → $LOG_DIR/backend.log)"
  (
    cd "$ROOT/backend"
    exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
  ) >"$LOG_DIR/backend.log" 2>&1 &
  pids+=($!)
fi

# 3. frontend
if port_busy 3838; then
  echo "• frontend already running on :3838 — reusing"
else
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "error: pnpm not found. Install with: npm i -g pnpm" >&2
    exit 1
  fi
  echo "• starting frontend on :3838 (logs → $LOG_DIR/frontend.log)"
  (
    cd "$ROOT/frontend"
    exec pnpm dev
  ) >"$LOG_DIR/frontend.log" 2>&1 &
  pids+=($!)
fi

# wait for backend to answer /health, up to ~30s
echo -n "• waiting for backend"
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8765/health >/dev/null; then
    echo " — ready"
    break
  fi
  echo -n "."
  sleep 1
done

# wait for frontend to answer
echo -n "• waiting for frontend"
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:3838 >/dev/null; then
    echo " — ready"
    break
  fi
  echo -n "."
  sleep 1
done

cat <<EOF

babel is up:
  frontend     http://127.0.0.1:3838
  backend      http://127.0.0.1:8765/health
  llama-server http://127.0.0.1:8080/health
  logs         $LOG_DIR/{llama-server,backend,frontend}.log

Ctrl+C to stop everything.
EOF

wait
