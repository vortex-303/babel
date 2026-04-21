#!/usr/bin/env bash
# babel — first-time setup on a fresh machine.
# Re-runs are safe (idempotent).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

have() { command -v "$1" >/dev/null 2>&1; }

say() { printf '• %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

say "checking prerequisites…"

MISSING=()
have brew     || MISSING+=("brew (https://brew.sh)")
have uv       || MISSING+=("uv (curl -LsSf https://astral.sh/uv/install.sh | sh)")
have node     || MISSING+=("node (brew install node)")
have pnpm     || MISSING+=("pnpm (npm install -g pnpm  or  brew install pnpm)")
have llama-server || MISSING+=("llama.cpp (brew install llama.cpp)")

if [ "${#MISSING[@]}" -gt 0 ]; then
  warn "missing tools:"
  for m in "${MISSING[@]}"; do printf '    - %s\n' "$m" >&2; done
  die "install the above, then re-run ./setup.sh"
fi

# ----- backend -----
say "setting up backend (Python via uv)…"
pushd "$ROOT/backend" >/dev/null
if [ ! -d .venv ]; then
  uv venv
fi
uv pip install -q -e ".[dev]"
popd >/dev/null
say "backend ready (venv at backend/.venv)"

# ----- frontend -----
say "installing frontend deps (pnpm)…"
pushd "$ROOT/frontend" >/dev/null
pnpm install --frozen-lockfile 2>/dev/null || pnpm install
popd >/dev/null
say "frontend ready"

# ----- data dirs -----
mkdir -p "$ROOT/jobs" "$ROOT/backend/jobs" "$ROOT/backend/uploads" "$ROOT/backend/outputs"

cat <<EOF

babel is ready.

1. Start everything with:
   ./dev.sh

   This boots llama-server (downloading the TranslateGemma 4B Q4_K_M
   GGUF on first run, ~2.6 GB), the FastAPI backend on :8765, and the
   Next.js frontend on :3838.

2. Open http://127.0.0.1:3838

3. Tests:
   cd backend && .venv/bin/python -m pytest tests/ -q
EOF
