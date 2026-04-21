#!/usr/bin/env bash
# babel-worker — install on macOS or Linux.
# Idempotent. Prompts for the missing bits. Uses a dedicated venv so it
# never fights with your system Python or uv's externally-managed one.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER_DIR="$ROOT/worker"
CFG_DIR="$HOME/.config/babel-worker"
CFG_FILE="$CFG_DIR/config.env"
VENV_DIR="$HOME/.local/share/babel-worker/venv"
BIN_DIR="$HOME/.local/bin"
LOG_DIR="$HOME/.local/state/babel-worker"
WORKER_BIN="$VENV_DIR/bin/babel-worker"

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      die "unsupported OS: $(uname -s)" ;;
esac

have python3 || die "python3 not installed"

mkdir -p "$CFG_DIR" "$LOG_DIR" "$BIN_DIR" "$(dirname "$VENV_DIR")"
chmod 700 "$CFG_DIR"

# ----- 1. Dedicated venv --------------------------------------------------
if [ ! -x "$VENV_DIR/bin/python" ]; then
  if have uv; then
    say "creating venv via uv → $VENV_DIR"
    uv venv "$VENV_DIR"
  else
    say "creating venv via python3 -m venv → $VENV_DIR"
    python3 -m venv "$VENV_DIR"
  fi
else
  say "venv already present: $VENV_DIR"
fi

# ----- 2. Install worker package into the venv ---------------------------
EXTRAS=""
if [ "$OS" = mac ]; then
  read -rp "Install menu-bar tray icon? [Y/n] " ans
  case "$ans" in
    [nN]*) EXTRAS="" ;;
    *)     EXTRAS="[tray]" ;;
  esac
fi
PKG_SPEC="$WORKER_DIR${EXTRAS}"

say "installing babel-worker${EXTRAS:+ (with tray)} into the venv…"
if have uv; then
  uv pip install --python "$VENV_DIR/bin/python" -e "$PKG_SPEC"
else
  "$VENV_DIR/bin/pip" install --quiet --upgrade pip
  "$VENV_DIR/bin/pip" install --quiet -e "$PKG_SPEC"
fi

[ -x "$WORKER_BIN" ] || die "babel-worker not found at $WORKER_BIN after install"

# ----- 3. Symlink to ~/.local/bin/babel-worker ---------------------------
ln -sf "$WORKER_BIN" "$BIN_DIR/babel-worker"
say "babel-worker available at: $BIN_DIR/babel-worker (→ $WORKER_BIN)"

# ----- 4. Config file ----------------------------------------------------
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

# ----- 5. System service --------------------------------------------------
if [ "$OS" = mac ]; then
  PLIST="$HOME/Library/LaunchAgents/com.vortex303.babel-worker.plist"
  say "installing launchd agent: $PLIST"
  TRAY_FLAG=""
  [ -n "$EXTRAS" ] && TRAY_FLAG="    <string>--tray</string>"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.vortex303.babel-worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>$WORKER_BIN</string>
$TRAY_FLAG
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

  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
  say "launchd agent loaded."
  echo "    Logs:    tail -F $LOG_DIR/stderr.log"
  echo "    Stop:    launchctl unload $PLIST"

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
ExecStart=$WORKER_BIN
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/stdout.log
StandardError=append:$LOG_DIR/stderr.log

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now babel-worker.service
  say "systemd service started."
  echo "    Logs:    journalctl --user -u babel-worker -f"
  echo "    Stop:    systemctl --user stop babel-worker"
  warn "On some distros: sudo loginctl enable-linger $USER"
  warn "  (otherwise the service stops when you log out)"
fi

cat <<EOF

\033[1;32m✓ babel-worker installed and running\033[0m

  Venv:    $VENV_DIR
  Binary:  $WORKER_BIN
  Config:  $CFG_FILE
  Logs:    $LOG_DIR/{stdout,stderr}.log

Verify in the admin panel within 30 seconds:
  https://babeltower.lat/admin   → "Workers" list should include this machine.

EOF
