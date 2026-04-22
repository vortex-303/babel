# packaging/mac

Build a self-contained, unsigned `babel.app` that any macOS user can drag
into Applications and run.

## Build

```bash
./packaging/mac/build.sh
```

Output lands at `packaging/mac/build/babel-<version>-macos-<arch>.zip` (about
150 MB). The bundle contains:

- **Resources/python/** — full relocatable CPython from
  [astral-sh/python-build-standalone](https://github.com/astral-sh/python-build-standalone)
- **Resources/python/.../site-packages/babel_worker/** — the worker package
  we already ship, pip-installed into the bundled interpreter
- **Resources/llama/bin/** — `llama-server` + dylibs straight from
  [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) releases
- **Resources/first-run.sh** — AppleScript dialog that prompts for backend
  URL + worker token on first launch
- **MacOS/babel** — a bash launcher that sets `PATH`, runs first-run if
  needed, and execs `python3 -m babel_worker --tray`
- **Info.plist** with `LSUIElement=true` so it's a menu-bar-only app (no
  Dock icon, no window)

No Python or Homebrew required on the target machine — everything is
bundled.

## Bump versions

Edit the top of `build.sh`:

```bash
PBS_TAG="20260414"      # astral-sh/python-build-standalone release tag
PBS_PY="3.10.20"        # CPython version inside that release
LLAMA_TAG="b8882"       # ggml-org/llama.cpp release tag
```

If an asset 404s during download, the script aborts — so stale URLs are
caught immediately, not silently buried in a broken app.

## Release

For now, manual:

```bash
VERSION=0.1.0 ./packaging/mac/build.sh
gh release create v0.1.0 \
  packaging/mac/build/babel-0.1.0-macos-arm64.zip \
  --title "babel 0.1.0 — macOS (Apple Silicon)" \
  --notes "First `.app` release."
```

The landing page's download button points at
`https://github.com/vortex-303/babel/releases/latest/download/babel-macos-arm64.zip`,
which always resolves to the newest release. Rename the zip to that exact
file name when you upload the release asset.

## Verify a user's download (reproducible builds)

Any user can rebuild the app from the tagged commit and compare:

```bash
git checkout v0.1.0
VERSION=0.1.0 ./packaging/mac/build.sh
shasum -a 256 packaging/mac/build/babel-0.1.0-macos-arm64.zip
```

If their hash matches the hash in the GitHub release notes, the binary is
exactly what the source describes. No signing needed — the source itself
is the trust anchor.

## Why unsigned

- No $99/year Apple Developer enrollment
- Open-source; anyone can audit + rebuild
- macOS still protects first-launch with Gatekeeper (right-click → Open),
  which we'd need regardless if we wanted to be careful about phishing
- We may revisit signing later if it's a real conversion blocker; for now
  the ≈ 5 seconds of Gatekeeper friction is an acceptable tax
