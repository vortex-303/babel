#!/usr/bin/env bash
# babel-worker — install on macOS or Linux.
# Idempotent. Prompts for the missing bits.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER_DIR="$ROOT/worker"
CFG_DIR="$HOME/.config/babel-worker"
CFG_FILE="$CFG_DIR/config.env"
LOG_DIR="$HOME/.local/state/babel-worker"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      die "unsupported OS: $(uname -s)" ;;
esac

# ----- 1. Python + pipx/uv ------------------------------------------------
have python3 || die "python3 not installed"

if have uv; then
  PY_INSTALLER="uv pip install --system"
elif have pipx; then
  PY_INSTALLER="pipx install --force"
else
  say "neither uv nor pipx found — installing via user pip"
  PY_INSTALLER="python3 -m pip install --user"
fi

say "installing babel-worker package…"
pushd "$WORKER_DIR" >/dev/null
case "$PY_INSTALLER" in
  uv*)    uv pip install --system -e . ;;
  pipx*)  pipx install --force -e . ;;
  *)      python3 -m pip install --user -e . ;;
esac
popd >/dev/null

have babel-worker || die "babel-worker on PATH check failed — add $(python3 -m site --user-base)/bin to PATH and re-run"

say "babel-worker installed: $(which babel-worker)"

# ----- 2. Config file -----------------------------------------------------
mkdir -p "$CFG_DIR" "$LOG_DIR"
chmod 700 "$CFG_DIR"

if [ ! -f "$CFG_FILE" ]; then
  say "first-time config — answer two questions"
  read -rp "Backend URL [https://api.babeltower.lat]: " BACKEND_URL
  BACKEND_URL="${BACKEND_URL:-https://api.babeltower.lat}"

  printf "Worker token (BABEL_WORKER_TOKEN from backend .env / fly secrets): "
  read -rs WORKER_TOKEN
  echo

  [ -n "$WORKER_TOKEN" ] || die "worker token required"

  umask 077
  cat > "$CFG_FILE" <<EOF
# babel-worker config — managed by scripts/install-worker.sh
BABEL_WORKER_BACKEND_URL=$BACKEND_URL
BABEL_WORKER_TOKEN=$WORKER_TOKEN
BABEL_WORKER_LLAMA_HOST=127.0.0.1
BABEL_WORKER_LLAMA_PORT=8080
BABEL_WORKER_POLL_INTERVAL=5.0
BABEL_WORKER_HEARTBEAT_INTERVAL=30.0
EOF
  say "wrote $CFG_FILE"
else
  say "config exists: $CFG_FILE (not overwriting — edit by hand if needed)"
fi

# ----- 3. System service --------------------------------------------------
if [ "$OS" = mac ]; then
  PLIST="$HOME/Library/LaunchAgents/com.vortex303.babel-worker.plist"
  say "installing launchd agent: $PLIST"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.vortex303.babel-worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(which babel-worker)</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$PATH</string>
  </dict>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>StandardOutPath</key>   <string>$LOG_DIR/stdout.log</string>
  <key>StandardErrorPath</key> <string>$LOG_DIR/stderr.log</string>
</dict>
</plist>
EOF

  # Reload if already loaded, then load.
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
  say "launchd agent loaded. Tail logs with:"
  echo "    tail -F $LOG_DIR/stderr.log"

else
  UNIT="$HOME/.config/systemd/user/babel-worker.service"
  mkdir -p "$(dirname "$UNIT")"
  say "installing systemd user unit: $UNIT"
  cat > "$UNIT" <<EOF
[Unit]
Description=babel translation pull-worker
After=network.target

[Service]
Type=simple
EnvironmentFile=$CFG_FILE
ExecStart=$(which babel-worker)
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/stdout.log
StandardError=append:$LOG_DIR/stderr.log

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now babel-worker.service
  say "systemd service started. Tail logs with:"
  echo "    journalctl --user -u babel-worker -f"
  warn "On some distros you also need: sudo loginctl enable-linger $USER"
  warn "so the service keeps running after you log out."
fi

cat <<EOF

\033[1;32m✓ babel-worker installed and running\033[0m

  Config:  $CFG_FILE
  Logs:    $LOG_DIR/{stdout,stderr}.log
  Uninstall: $(basename "$0" .sh)-uninstall.sh (TODO)

To verify the worker is reaching the backend, check the admin panel:
  https://babeltower.lat/admin  → Workers list should show this machine
  within 30 seconds.

EOF
