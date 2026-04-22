#!/bin/bash
# babel one-liner installer for macOS.
#   curl -fsSL https://babeltower.lat/install.sh | bash
#
# Downloads the latest babel.app release, installs to /Applications (or
# ~/Applications if no write access), clears Gatekeeper's quarantine
# attribute (since you already trusted us by running this), and opens it.
# First launch will prompt for backend URL + worker token.
set -euo pipefail

RELEASE_URL="https://github.com/vortex-303/babel/releases/latest/download/babel-macos-arm64.zip"
SYS_APPS="/Applications"
USER_APPS="$HOME/Applications"

say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || die "this installer is macOS-only. Linux / Windows soon."

if [ "$(uname -m)" != arm64 ]; then
  warn "detected $(uname -m); Apple Silicon only right now. Intel x86_64 build coming soon."
  die "aborting — install on an M-series Mac, or see github.com/vortex-303/babel for the manual path"
fi

# Pick install dir — prefer /Applications if writable, else ~/Applications.
if [ -w "$SYS_APPS" ]; then
  DEST="$SYS_APPS"
else
  mkdir -p "$USER_APPS"
  DEST="$USER_APPS"
  say "no write access to $SYS_APPS — installing to $DEST instead"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say "downloading latest babel.app…"
curl -fL --progress-bar -o "$TMP/babel.zip" "$RELEASE_URL"

say "extracting…"
unzip -q "$TMP/babel.zip" -d "$TMP"
[ -d "$TMP/babel.app" ] || die "unexpected zip layout — expected babel.app at the root"

say "installing to $DEST/babel.app"
rm -rf "$DEST/babel.app"
mv "$TMP/babel.app" "$DEST/"

# Clear quarantine so Gatekeeper doesn't prompt. Anyone running a
# `curl | bash` installer has already chosen to trust the source.
xattr -dr com.apple.quarantine "$DEST/babel.app" 2>/dev/null || true

say "opening babel.app — menu bar tower icon appears in a few seconds"
open "$DEST/babel.app"

cat <<EOF

\033[1;32m✓ babel installed\033[0m

  App:    $DEST/babel.app
  Icon:   top-right menu bar (the ziggurat tower)
  Config: ~/.config/babel-worker/config.env

To uninstall:
  rm -rf "$DEST/babel.app" ~/.config/babel-worker ~/.local/state/babel-worker

Docs: https://github.com/vortex-303/babel/blob/main/docs/MAC-APP.md
EOF
