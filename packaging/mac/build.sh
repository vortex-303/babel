#!/usr/bin/env bash
# Build a self-contained babel.app bundle for macOS.
#
# Outputs packaging/mac/build/babel-<version>-macos-<arch>.zip containing a
# signed-ad-hoc babel.app. No Apple Developer account required — users
# right-click → Open on first launch to clear Gatekeeper, then it's
# trusted forever.
#
# What's inside the .app:
#   Contents/MacOS/babel          launcher (bash)
#   Contents/Resources/python/    full relocatable CPython
#   Contents/Resources/python/.../site-packages  babel_worker[tray]
#   Contents/Resources/llama/     llama.cpp binaries + dylibs
#   Contents/Resources/first-run.sh  AppleScript-based config prompt
#   Contents/Info.plist           LSUIElement=true (menu-bar agent)
#
# The GGUF model (~2.6 GB) is NOT bundled — llama-server auto-downloads
# it on first use via -hf. Keeps the zip ≈ 150 MB.
set -euo pipefail

VERSION="${VERSION:-0.1.0}"
ARCH="${ARCH:-$(uname -m)}"   # arm64 or x86_64
# Normalize: python-build-standalone uses aarch64, llama.cpp uses arm64.
case "$ARCH" in
  arm64|aarch64) PBS_ARCH=aarch64-apple-darwin ; LLAMA_ARCH=macos-arm64 ;;
  x86_64|x64)    PBS_ARCH=x86_64-apple-darwin  ; LLAMA_ARCH=macos-x64   ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 2 ;;
esac

# Versions — bump these to update the bundle. The script fails loudly if
# an asset 404s so stale URLs are caught at build time, not install time.
PBS_TAG="20260414"
PBS_PY="3.10.20"
LLAMA_TAG="b8882"

# --- paths ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
APP="$BUILD_DIR/babel.app"

say()  { printf '\033[1;32m•\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null || die "curl required"
command -v unzip >/dev/null || die "unzip required"
command -v codesign >/dev/null || die "codesign required (Xcode Command Line Tools)"

say "Building babel $VERSION for $ARCH → $APP"

rm -rf "$BUILD_DIR"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# --- Python runtime ------------------------------------------------------
say "fetching python-build-standalone $PBS_PY ($PBS_TAG, $PBS_ARCH)…"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_TAG/cpython-$PBS_PY%2B$PBS_TAG-$PBS_ARCH-install_only.tar.gz"
curl -fsSL "$PBS_URL" | tar -xz -C "$APP/Contents/Resources/"
[ -x "$APP/Contents/Resources/python/bin/python3" ] || die "python-build-standalone extract failed"

# --- install worker + deps into the bundle ------------------------------
say "installing babel_worker[tray] into the bundled Python…"
BUNDLED_PY="$APP/Contents/Resources/python/bin/python3"
"$BUNDLED_PY" -m ensurepip --upgrade >/dev/null
"$BUNDLED_PY" -m pip install --quiet --upgrade pip
"$BUNDLED_PY" -m pip install --quiet "$ROOT/worker[tray]"

# Sanity: make sure the entrypoint was created.
[ -x "$APP/Contents/Resources/python/bin/babel-worker" ] \
  || die "babel-worker entrypoint missing after install"

# --- llama.cpp ------------------------------------------------------------
say "fetching llama.cpp $LLAMA_TAG ($LLAMA_ARCH)…"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LLAMA_URL="https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG/llama-$LLAMA_TAG-bin-$LLAMA_ARCH.tar.gz"
curl -fsSL "$LLAMA_URL" | tar -xz -C "$TMP/"
# Archive layout varies by platform: macOS has everything flat under
# `llama-b<tag>/`, Linux has `build/bin/`. Find llama-server wherever it is.
LLAMA_BIN=$(find "$TMP" -name "llama-server" -type f 2>/dev/null | head -1)
[ -n "$LLAMA_BIN" ] && [ -x "$LLAMA_BIN" ] \
  || die "llama-server not found inside llama.cpp archive"
LLAMA_BIN_SRC="$(dirname "$LLAMA_BIN")"
mkdir -p "$APP/Contents/Resources/llama/bin"
cp -a "$LLAMA_BIN_SRC/"* "$APP/Contents/Resources/llama/bin/"

# --- Info.plist ----------------------------------------------------------
say "writing Info.plist"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>        <string>babel</string>
  <key>CFBundleIdentifier</key>        <string>com.vortex303.babel</string>
  <key>CFBundleName</key>              <string>babel</string>
  <key>CFBundleDisplayName</key>       <string>babel</string>
  <key>CFBundleVersion</key>           <string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>LSMinimumSystemVersion</key>    <string>11.0</string>
  <key>LSUIElement</key>               <true/>
  <key>NSHighResolutionCapable</key>   <true/>
</dict>
</plist>
PLIST

# --- launcher ------------------------------------------------------------
cp "$SCRIPT_DIR/launcher.sh"   "$APP/Contents/MacOS/babel"
cp "$SCRIPT_DIR/first-run.sh"  "$APP/Contents/Resources/first-run.sh"
chmod +x "$APP/Contents/MacOS/babel" "$APP/Contents/Resources/first-run.sh"

# --- ad-hoc sign ---------------------------------------------------------
say "ad-hoc codesign"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || \
  say "  (codesign warning — ad-hoc signature may be incomplete; bundle still works)"

# --- zip -----------------------------------------------------------------
ZIP_NAME="babel-$VERSION-macos-$ARCH.zip"
say "zipping → $BUILD_DIR/$ZIP_NAME"
( cd "$BUILD_DIR" && zip -qr "$ZIP_NAME" babel.app )

SIZE_MB=$(du -sm "$BUILD_DIR/$ZIP_NAME" | cut -f1)
cat <<EOF

\033[1;32m✓ babel $VERSION built\033[0m

  App:  $APP
  Zip:  $BUILD_DIR/$ZIP_NAME  (${SIZE_MB} MB)

To test locally:
  open $APP

To distribute:
  upload $BUILD_DIR/$ZIP_NAME to babeltower.lat/download
  users unzip, drag to /Applications, right-click → Open first launch.

EOF
