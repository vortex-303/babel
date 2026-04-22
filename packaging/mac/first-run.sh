#!/bin/bash
# First-run setup — invoked by launcher.sh when no config.env exists.
# Uses AppleScript dialogs so there's no Terminal flash.
set -euo pipefail

CFG_DIR="$HOME/.config/babel-worker"
CFG="$CFG_DIR/config.env"

mkdir -p "$CFG_DIR"

# ---- backend URL --------------------------------------------------------
BACKEND=$(osascript <<'APPLESCRIPT'
set defaultURL to "https://api.babeltower.lat"
try
    set answer to text returned of (display dialog ¬
        "Backend URL for babel" & return & return & ¬
        "Leave the default unless you're running your own babel backend." ¬
        default answer defaultURL ¬
        buttons {"Cancel", "Continue"} ¬
        default button "Continue" ¬
        with icon note ¬
        with title "babel · first-run setup")
    return answer
on error number -128
    return ""
end try
APPLESCRIPT
)

[ -n "$BACKEND" ] || exit 1

# ---- email --------------------------------------------------------------
EMAIL=$(osascript <<'APPLESCRIPT'
try
    set answer to text returned of (display dialog ¬
        "Email" & return & return & ¬
        "Sign in with your babeltower.lat account — the one that bought the self-host license." ¬
        default answer "" ¬
        buttons {"Cancel", "Continue"} ¬
        default button "Continue" ¬
        with icon note ¬
        with title "babel · first-run setup")
    return answer
on error number -128
    return ""
end try
APPLESCRIPT
)

[ -n "$EMAIL" ] || exit 1

# ---- password -----------------------------------------------------------
PASSWORD=$(osascript <<'APPLESCRIPT'
try
    set answer to text returned of (display dialog ¬
        "Password" & return & return & ¬
        "Stored locally at ~/.config/babel-worker/config.env (chmod 600)." ¬
        default answer "" ¬
        buttons {"Cancel", "Continue"} ¬
        default button "Continue" ¬
        with hidden answer ¬
        with icon note ¬
        with title "babel · first-run setup")
    return answer
on error number -128
    return ""
end try
APPLESCRIPT
)

[ -n "$PASSWORD" ] || exit 1

# ---- write config -------------------------------------------------------
umask 077
cat > "$CFG" <<EOF
# babel-worker config — written by first-run.sh. Edit by hand if needed.
BABEL_WORKER_BACKEND_URL=$BACKEND
BABEL_WORKER_EMAIL=$EMAIL
BABEL_WORKER_PASSWORD=$PASSWORD
BABEL_WORKER_LLAMA_HOST=127.0.0.1
BABEL_WORKER_LLAMA_PORT=8080
BABEL_WORKER_POLL_INTERVAL=5.0
BABEL_WORKER_HEARTBEAT_INTERVAL=30.0
BABEL_WORKER_AUTO_CLAIM=true
EOF

osascript <<APPLESCRIPT >/dev/null
display dialog "babel is configured." & return & return & "Look for the tower icon in your menu bar (top-right). Click it to start llama-server and watch jobs arrive." buttons {"OK"} default button "OK" with icon note with title "babel · ready"
APPLESCRIPT
