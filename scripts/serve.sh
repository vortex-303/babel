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

# ----- tunnel (Tailscale Funnel preferred if present, else cloudflared) --
TUNNEL_STARTED=0

# Tailscale Funnel: runs as its own daemon, nothing to (re)start here — just
# detect it and tell the user the URL so they know it's live.
if have tailscale && sudo -n tailscale funnel status >/dev/null 2>&1; then
  FUNNEL_HOST="$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName' 2>/dev/null | sed 's/\.$//' || true)"
  if [ -n "${FUNNEL_HOST:-}" ] && [ "$FUNNEL_HOST" != null ]; then
    say "Tailscale Funnel active: https://$FUNNEL_HOST"
    TUNNEL_STARTED=1
  fi
fi

if [ "$TUNNEL_STARTED" -eq 0 ]; then
  if systemctl --quiet is-active cloudflared 2>/dev/null; then
    say "cloudflared already running as systemd service"
    TUNNEL_STARTED=1
  elif have cloudflared && [ -f "$CF_CONFIG" ]; then
    say "starting cloudflared tunnel…"
    mkdir -p "$ROOT/jobs"
    cloudflared tunnel --config "$CF_CONFIG" run \
      >"$ROOT/jobs/cloudflared.log" 2>&1 &
    pids+=($!)
    say "  cloudflared logs → $ROOT/jobs/cloudflared.log"
    TUNNEL_STARTED=1
  fi
fi

if [ "$TUNNEL_STARTED" -eq 0 ]; then
  warn "no tunnel configured — babel will only be reachable on localhost."
  warn "  Run ./scripts/tunnel-tailscale.sh or ./scripts/tunnel-setup.sh first."
fi

# ----- babel (llama + backend + frontend) --------------------------------
say "starting babel…"
"$ROOT/dev.sh" &
pids+=($!)

wait
