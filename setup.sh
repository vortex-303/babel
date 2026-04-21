#!/usr/bin/env bash
# babel — first-time setup on a fresh machine. Supports macOS + Linux.
# Re-runs are safe (idempotent).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '• %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# Detect OS and pick the right hint for each missing tool.
case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      OS=unknown ;;
esac

hint_for() {
  local tool="$1"
  case "$OS:$tool" in
    mac:brew)          echo "install Homebrew from https://brew.sh" ;;
    mac:uv)            echo "curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
    mac:node)          echo "brew install node" ;;
    mac:pnpm)          echo "brew install pnpm  (or  npm i -g pnpm)" ;;
    mac:llama-server)  echo "brew install llama.cpp" ;;
    linux:uv)          echo "curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
    linux:node)        echo "apt install -y nodejs  |  dnf install -y nodejs  |  pacman -S nodejs  |  or use nvm" ;;
    linux:pnpm)        echo "npm i -g pnpm  (or see https://pnpm.io/installation)" ;;
    linux:llama-server)
      cat <<'HINT'
build from source or grab a release binary:
       # Option A — prebuilt CPU/CUDA release
       #   https://github.com/ggml-org/llama.cpp/releases  (download + unpack; put binaries on PATH)
       # Option B — build from source with CUDA (NVIDIA)
       #   git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
       #   cmake -B build -DGGML_CUDA=ON && cmake --build build -j
       #   export PATH="$(pwd)/build/bin:$PATH"
       # Option C — CPU-only build
       #   cmake -B build && cmake --build build -j
HINT
      ;;
    *)                 echo "please install '$tool'" ;;
  esac
}

say "detected OS: $OS"
say "checking prerequisites…"

REQUIRED=(uv node pnpm llama-server)
[ "$OS" = mac ] && REQUIRED=(brew "${REQUIRED[@]}")

MISSING=()
for tool in "${REQUIRED[@]}"; do
  have "$tool" || MISSING+=("$tool")
done

if [ "${#MISSING[@]}" -gt 0 ]; then
  warn "missing tools:"
  for t in "${MISSING[@]}"; do
    printf '    - %s\n      → %s\n' "$t" "$(hint_for "$t")" >&2
  done
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

babel is ready on $OS.

1. Start everything with:
   ./dev.sh

   This boots llama-server (downloading the TranslateGemma 4B Q4_K_M
   GGUF on first run, ~2.6 GB), the FastAPI backend on :8765, and the
   Next.js frontend on :3838.

2. Open http://127.0.0.1:3838

3. Tests:
   cd backend && .venv/bin/python -m pytest tests/ -q

EOF

if [ "$OS" = linux ]; then
  cat <<'EOF'
Linux GPU tips:
  - NVIDIA: build llama.cpp with -DGGML_CUDA=ON and keep --n-gpu-layers 999
           in dev.sh. On A10/A40-class cards, 12B Q4_K_M is a better quality/speed pick.
  - AMD: build with -DGGML_HIP=ON (ROCm). Same --n-gpu-layers flag applies.
  - CPU-only: edit dev.sh and set --n-gpu-layers 0. Expect ~5-10× slower tok/s.
EOF
fi
