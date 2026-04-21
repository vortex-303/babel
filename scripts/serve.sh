#!/usr/bin/env bash
# babel — production serve: starts babel + cloudflared tunnel together.
#
# Runs in the foreground. Ctrl+C stops both. If cloudflared is already
# running as a systemd service (after `tunnel-setup.sh --service`), this
# script skips starting cloudflared and just runs babel.
#
# Usage:
#   ./scripts/serve.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CF_CONFIG="$HOME/.cloudflared/config.yml"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }

# Load .env if present so BABEL_ADMIN_CODE etc. are in scope.
if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi

if [ -z "${BABEL_ADMIN_CODE:-}" ]; then
  warn "BABEL_ADMIN_CODE is not set — admin endpoints will be disabled."
  warn "  Set it in .env before running, otherwise /admin will 403."
fi

pids=()
cleanup() {
  echo
  say "shutting down…"
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

# ----- cloudflared --------------------------------------------------------
if systemctl --quiet is-active cloudflared 2>/dev/null; then
  say "cloudflared already running as systemd service — skipping"
elif have cloudflared && [ -f "$CF_CONFIG" ]; then
  say "starting cloudflared tunnel…"
  mkdir -p "$ROOT/jobs"
  cloudflared tunnel --config "$CF_CONFIG" run \
    >"$ROOT/jobs/cloudflared.log" 2>&1 &
  pids+=($!)
  say "  cloudflared logs → $ROOT/jobs/cloudflared.log"
else
  warn "cloudflared not configured — babel will only be reachable on localhost."
  warn "  Run scripts/tunnel-setup.sh first to get a public URL."
fi

# ----- babel (llama + backend + frontend) --------------------------------
say "starting babel…"
"$ROOT/dev.sh" &
pids+=($!)

wait
