#!/usr/bin/env bash
# babel — cloudflared named-tunnel setup.
#
# One-time: creates (or reuses) a tunnel named "babel", routes
# api.babeltower.lat to localhost:8765, writes ~/.cloudflared/config.yml.
# Safe to re-run — idempotent for every step.
#
# Usage:
#   ./scripts/tunnel-setup.sh
#   ./scripts/tunnel-setup.sh --hostname api.example.com   # custom domain
#   ./scripts/tunnel-setup.sh --service                    # install systemd
set -euo pipefail

TUNNEL_NAME="babel"
HOSTNAME="api.babeltower.lat"
LOCAL_PORT=8765
INSTALL_SERVICE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --hostname) HOSTNAME="$2"; shift 2;;
    --name)     TUNNEL_NAME="$2"; shift 2;;
    --port)     LOCAL_PORT="$2"; shift 2;;
    --service)  INSTALL_SERVICE=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

have cloudflared || die "cloudflared not installed. Run bootstrap-ubuntu.sh first."

CF_DIR="$HOME/.cloudflared"
mkdir -p "$CF_DIR"

# ----- 1. Login if not already ------------------------------------------
if [ ! -f "$CF_DIR/cert.pem" ]; then
  say "cloudflared needs a one-time browser login. A URL will appear below."
  cloudflared tunnel login
  [ -f "$CF_DIR/cert.pem" ] || die "login didn't complete — rerun when you're ready"
else
  say "cloudflared already logged in"
fi

# ----- 2. Create tunnel if missing ---------------------------------------
TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null \
  | jq -r --arg n "$TUNNEL_NAME" '.[] | select(.name==$n) | .id' | head -1 || true)

if [ -z "$TUNNEL_ID" ]; then
  say "creating tunnel '$TUNNEL_NAME'…"
  cloudflared tunnel create "$TUNNEL_NAME"
  TUNNEL_ID=$(cloudflared tunnel list --output json \
    | jq -r --arg n "$TUNNEL_NAME" '.[] | select(.name==$n) | .id' | head -1)
  [ -n "$TUNNEL_ID" ] || die "tunnel create succeeded but we can't find its id"
else
  say "tunnel '$TUNNEL_NAME' already exists ($TUNNEL_ID)"
fi

CRED_FILE="$CF_DIR/${TUNNEL_ID}.json"
[ -f "$CRED_FILE" ] || die "credentials file missing: $CRED_FILE"

# ----- 3. Write config.yml -----------------------------------------------
CONFIG="$CF_DIR/config.yml"
say "writing $CONFIG"
cat > "$CONFIG" <<EOF
tunnel: $TUNNEL_NAME
credentials-file: $CRED_FILE

ingress:
  - hostname: $HOSTNAME
    service: http://127.0.0.1:$LOCAL_PORT
  - service: http_status:404
EOF

# ----- 4. Route DNS ------------------------------------------------------
say "routing DNS: $HOSTNAME → $TUNNEL_NAME"
# `route dns` fails if the record already exists; we treat that as success.
if ! cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" 2>&1 \
  | tee /tmp/cf-route-out.log; then
  if grep -qi "already exists" /tmp/cf-route-out.log; then
    say "DNS already routed (ok)"
  else
    warn "DNS route command failed — check the output above"
  fi
fi

# ----- 5. Validate config -----------------------------------------------
say "validating config…"
cloudflared tunnel --config "$CONFIG" ingress validate

# ----- 6. Systemd service (optional) -------------------------------------
if [ "$INSTALL_SERVICE" -eq 1 ]; then
  if systemctl --quiet is-active cloudflared 2>/dev/null; then
    say "cloudflared service already running"
  else
    say "installing cloudflared as a systemd service…"
    sudo cloudflared --config "$CONFIG" service install
    sudo systemctl enable --now cloudflared
    say "service status:"
    sudo systemctl status cloudflared --no-pager | head -8 || true
  fi
fi

cat <<EOF

\033[1;32m✓ tunnel configured\033[0m

  Tunnel:   $TUNNEL_NAME ($TUNNEL_ID)
  Hostname: https://$HOSTNAME
  Target:   http://127.0.0.1:$LOCAL_PORT

To run the tunnel now (foreground, Ctrl+C to stop):
  cloudflared tunnel --config $CONFIG run

To run it as a systemd service (starts on boot):
  $0 --service

To verify once it's up (from this machine or any other):
  curl https://$HOSTNAME/health

EOF
