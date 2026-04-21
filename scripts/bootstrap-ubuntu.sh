#!/usr/bin/env bash
# babel — one-shot Ubuntu 24.04 setup.
#
# Idempotent. Safe to re-run. Installs everything babel needs on a fresh
# Ubuntu box with an NVIDIA GPU + working driver. Does NOT install the
# NVIDIA driver itself (assumes `nvidia-smi` already works with >= 570).
#
# Usage:
#   ./scripts/bootstrap-ubuntu.sh
#
# Environment overrides:
#   LLAMACPP_RELEASE_TAG   — llama.cpp release tag (default: latest)
#   CUDA_VARIANT           — 12.4 or 13.1 (default: 13.1, matches driver 580+)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Linux ] || die "this script is Ubuntu-only — see INSTALL.md for macOS"

if [ -r /etc/os-release ]; then
  . /etc/os-release
  [ "${ID:-}" = ubuntu ] || warn "tested on Ubuntu; detected '${ID:-unknown}' — may still work"
fi

# ----- 0. GPU sanity check ------------------------------------------------
if have nvidia-smi; then
  DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits | head -1 | cut -d. -f1)
  say "NVIDIA driver detected: $DRIVER.x"
  if [ "$DRIVER" -lt 570 ]; then
    warn "driver $DRIVER.x is below 570 — Blackwell and newer cards may not work. Consider: sudo ubuntu-drivers install nvidia:590"
  fi
else
  warn "nvidia-smi not found — continuing, but you'll only get CPU inference (slow)"
fi

# ----- 1. System packages -------------------------------------------------
say "installing base packages via apt…"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  git curl wget ca-certificates unzip jq \
  build-essential pkg-config \
  libcudart12 libcublas12 2>/dev/null || true

# ----- 2. Node.js 20 LTS --------------------------------------------------
if ! have node || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 20 ]; then
  say "installing Node.js 20 LTS via NodeSource…"
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs
else
  say "Node $(node -v) already present"
fi

# ----- 3. pnpm ------------------------------------------------------------
if ! have pnpm; then
  say "installing pnpm globally via npm…"
  sudo npm install -g pnpm >/dev/null 2>&1
else
  say "pnpm $(pnpm -v) already present"
fi

# ----- 4. uv (Python toolchain) ------------------------------------------
if ! have uv; then
  say "installing uv (Python toolchain)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  # Source the env hook so `uv` is usable in the rest of this script.
  # The installer writes to ~/.local/bin; ensure PATH covers it here.
  export PATH="$HOME/.local/bin:$PATH"
else
  say "uv $(uv --version | cut -d' ' -f2) already present"
fi

# ----- 5. llama.cpp (prebuilt CUDA binary) -------------------------------
LLAMA_DIR="$HOME/bin/llama.cpp"
if ! have llama-server; then
  CUDA_VARIANT="${CUDA_VARIANT:-13.1}"
  TAG="${LLAMACPP_RELEASE_TAG:-}"
  if [ -z "$TAG" ]; then
    say "resolving latest llama.cpp release tag…"
    TAG=$(curl -fsSL https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | jq -r '.tag_name')
    [ -n "$TAG" ] && [ "$TAG" != null ] || die "couldn't resolve latest llama.cpp release"
  fi

  say "downloading llama.cpp $TAG (CUDA $CUDA_VARIANT)…"
  mkdir -p "$LLAMA_DIR"
  cd "$LLAMA_DIR"
  ZIP="llama-${TAG}-bin-ubuntu-cuda-${CUDA_VARIANT}-x64.zip"
  URL="https://github.com/ggml-org/llama.cpp/releases/download/${TAG}/${ZIP}"
  curl -fsSL -o "$ZIP" "$URL" || die "download failed: $URL"
  unzip -q -o "$ZIP"
  rm -f "$ZIP"

  # Ensure llama-server is on PATH for future shells.
  if ! grep -q "llama.cpp/build/bin" "$HOME/.bashrc" 2>/dev/null; then
    {
      echo ""
      echo "# babel: llama.cpp binaries"
      echo "export PATH=\"\$HOME/bin/llama.cpp/build/bin:\$PATH\""
      echo "export LD_LIBRARY_PATH=\"\$HOME/bin/llama.cpp/build/bin:\$LD_LIBRARY_PATH\""
    } >> "$HOME/.bashrc"
  fi
  export PATH="$HOME/bin/llama.cpp/build/bin:$PATH"
  export LD_LIBRARY_PATH="$HOME/bin/llama.cpp/build/bin:${LD_LIBRARY_PATH:-}"

  if ! have llama-server; then
    die "llama-server still not on PATH after install — check $LLAMA_DIR/build/bin"
  fi
else
  say "llama-server already on PATH"
fi

say "llama-server: $(llama-server --version 2>&1 | head -1)"

# ----- 6. cloudflared ----------------------------------------------------
if ! have cloudflared; then
  say "installing cloudflared…"
  sudo mkdir -p /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared noble main' \
    | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq cloudflared
else
  say "cloudflared already present"
fi

# ----- 7. Python + Node deps via existing setup.sh ----------------------
say "running setup.sh to install Python + Node deps…"
cd "$ROOT"
./setup.sh

# ----- 8. .env from .env.example ----------------------------------------
if [ ! -f "$ROOT/.env" ]; then
  say "creating .env from .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn "edit $ROOT/.env and set BABEL_ADMIN_CODE before running dev.sh"
fi

# ----- 9. Summary -------------------------------------------------------
cat <<EOF

\033[1;32m✓ bootstrap complete\033[0m

Next steps:

  1. Set your admin code in .env:
       \$EDITOR $ROOT/.env            # edit BABEL_ADMIN_CODE

  2. Set up the cloudflared tunnel (one-time, interactive login):
       $ROOT/scripts/tunnel-setup.sh

  3. Start serving:
       $ROOT/scripts/serve.sh         # runs babel + tunnel together

  Or develop locally without the tunnel:
       $ROOT/dev.sh                   # localhost-only, no public URL

EOF
