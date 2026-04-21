#!/usr/bin/env bash
# babel — Tailscale Funnel setup (alternative to cloudflared).
#
# Installs Tailscale, authenticates, and exposes the babel backend port via
# Funnel so it's reachable on a public HTTPS URL (your-host.tailXYZ.ts.net).
# No Cloudflare account required — only a free Tailscale account.
#
# After this runs, point your Vercel `NEXT_PUBLIC_BABEL_BACKEND` env var at
# the URL it prints.
#
# Usage:
#   ./scripts/tunnel-tailscale.sh
#   PORT=8765 ./scripts/tunnel-tailscale.sh
set -euo pipefail

PORT="${PORT:-8765}"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ----- 1. Install tailscale ----------------------------------------------
if ! have tailscale; then
  say "installing tailscale…"
  curl -fsSL https://tailscale.com/install.sh | sh
else
  say "tailscale already installed ($(tailscale version | head -1))"
fi

have jq || { say "installing jq (needed to parse tailscale status)…"; sudo apt-get install -y -qq jq; }

# ----- 2. Authenticate ---------------------------------------------------
if ! sudo tailscale status >/dev/null 2>&1; then
  say "authenticating tailscale (opens a browser or prints a URL)…"
  warn "If you're on a headless box, copy the URL from below and open it on"
  warn "any browser that's logged into your tailnet."
  sudo tailscale up
else
  say "tailscale already authenticated"
fi

# ----- 3. Resolve our tailnet hostname -----------------------------------
DNS_NAME="$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName' | sed 's/\.$//')"
if [ -z "$DNS_NAME" ] || [ "$DNS_NAME" = null ]; then
  die "couldn't determine tailnet DNS name. Make sure MagicDNS is enabled
  in the Tailscale admin console (https://login.tailscale.com/admin/dns)."
fi

say "tailnet hostname: $DNS_NAME"

# ----- 4. Enable Funnel --------------------------------------------------
say "enabling Funnel on port $PORT (foreground HTTPS → http://127.0.0.1:$PORT)…"
if sudo tailscale funnel --bg "$PORT" 2>&1 | tee /tmp/ts-funnel.out; then
  say "funnel enabled"
else
  if grep -qi "not.*enabled\|permission\|acl\|attr:funnel" /tmp/ts-funnel.out; then
    cat <<EOF >&2

Funnel isn't authorized for this machine yet. One-time admin setup:

  1. Open https://login.tailscale.com/admin/acls
  2. In the policy file ensure you have:

       "nodeAttrs": [
         { "target": ["autogroup:admin"], "attr": ["funnel"] }
       ],

     (or scope it to the tag/user that owns this machine).
  3. Save, come back here, re-run this script.

Docs: https://tailscale.com/kb/1223/funnel
EOF
    exit 1
  fi
  die "funnel command failed — see output above"
fi

# ----- 5. Summary + next steps -------------------------------------------
URL="https://${DNS_NAME}"

cat <<EOF

\033[1;32m✓ Tailscale Funnel is live\033[0m

  Public URL:   $URL
  Forwards to:  http://127.0.0.1:$PORT
  Cert:         Tailscale-issued, auto-renewed

------------------------------------------------------------
Wire this into Vercel so babeltower.lat talks to your box:

  vercel env rm NEXT_PUBLIC_BABEL_BACKEND production --yes 2>/dev/null
  echo "$URL" | vercel env add NEXT_PUBLIC_BABEL_BACKEND production
  vercel --prod

------------------------------------------------------------
Verify the tunnel once babel is running (./scripts/serve.sh):

  curl $URL/health

------------------------------------------------------------
To stop exposing the port later:

  sudo tailscale funnel --bg $PORT off

EOF
