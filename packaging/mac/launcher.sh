#!/bin/bash
# babel.app launcher — the MacOS/babel executable macOS runs when the
# user launches babel from Finder / LaunchPad. We set up PATH +
# library paths for the bundled binaries, run the first-run prompt if
# needed, then exec the Python worker in tray mode.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RES="$APP_DIR/Resources"

export PATH="$RES/python/bin:$RES/llama/bin:$PATH"
# Pick up llama.cpp's bundled dylibs without modifying the user's env.
export DYLD_FALLBACK_LIBRARY_PATH="$RES/llama/bin:${DYLD_FALLBACK_LIBRARY_PATH:-}"

# Tell the worker where llama-server lives so it can launch it on demand.
export BABEL_LLAMA_SERVER_BIN="$RES/llama/bin/llama-server"

CFG_DIR="$HOME/.config/babel-worker"
CFG="$CFG_DIR/config.env"

if [ ! -f "$CFG" ]; then
  # Run the first-run dialog. If the user cancels, exit cleanly so the
  # app can be launched again later.
  "$RES/first-run.sh" || exit 0
fi

# Drop into the tray worker. This process lives in the user session as
# a menu-bar agent (LSUIElement=true in Info.plist) until it's quit.
exec "$RES/python/bin/python3" -m babel_worker --tray
