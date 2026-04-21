"""Menu-bar tray icon for babel-worker.

Uses pystray (AppKit on macOS, AppIndicator on Linux). Menu exposes:
  - Current worker state + current-job progress
  - Start / Restart llama-server subprocess
  - Pause / Resume the worker loop
  - Recent activity (last 10 events)
  - Open admin panel / View logs / Quit
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import httpx

try:  # noqa: SIM105
    import pystray
    from PIL import Image, ImageDraw
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "tray UI requires the 'tray' extras — install with:\n"
        "  pip install -e '.[tray]'\n"
        f"(missing: {e})"
    ) from e

from babel_worker.config import Config
from babel_worker.loop import run as run_loop
from babel_worker.state import Controller, WorkerState

log = logging.getLogger("babel_worker.tray")

ADMIN_URL_DEFAULT = "https://babeltower.lat/admin"
LOG_PATH_DEFAULT = Path.home() / ".local/state/babel-worker/stderr.log"
LLAMA_LOG_DEFAULT = Path.home() / ".local/state/babel-worker/llama-server.log"

# llama-server command we auto-launch. Mirrors scripts/serve.sh + dev.sh.
LLAMA_ARGS = [
    "-hf", "mradermacher/translategemma-4b-it-GGUF:Q4_K_M",
    "--host", "127.0.0.1",
    "--port", "8080",
    "--ctx-size", "8192",
    "--n-gpu-layers", "999",
    "--chat-template", "gemma",
]


# ---- icon rendering -----------------------------------------------------

# Phase colors — one per WorkerState.phase.
_PHASE_COLOR = {
    "starting": (160, 160, 160),
    "idle": (46, 204, 113),        # green — ready, polling
    "translating": (52, 152, 219), # blue — actively working
    "paused": (241, 196, 15),      # yellow — user paused
    "error": (231, 76, 60),        # red — auth/network/adapter error
    "stopping": (127, 127, 127),
}


def _tower_icon(phase: str, size: int = 64) -> Image.Image:
    """Draw the ziggurat/babel-tower silhouette used on babeltower.lat's
    landing page logo, tinted by the current phase color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = _PHASE_COLOR.get(phase, _PHASE_COLOR["idle"]) + (255,)
    # viewBox in the React SVG is 0..24. Scale into our pixel grid.
    s = size / 24
    # Stacked tiers (widest at bottom). Matches the React component in
    # frontend/src/app/page.tsx::TowerIcon.
    for x0, y0, x1, y1 in [
        (3, 15, 21, 20),   # base
        (4, 12, 20, 15),
        (6,  9, 18, 12),
        (8,  6, 16,  9),
        (10, 4, 14,  6),
    ]:
        d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], fill=c)
    # Spire at the top
    d.rectangle([11.5 * s, 2 * s, 12.5 * s, 4 * s], fill=c)
    # Ground line
    d.rectangle([3 * s, 20 * s, 21 * s, 20.8 * s], fill=c)
    return img


# ---- llama-server subprocess management --------------------------------


class LlamaManager:
    """Minimal supervisor for a locally-running llama-server. We don't aim
    to be systemd — just enough to offer Start/Restart menu items.
    llama-server keeps running if the tray quits; relaunching the tray
    picks up an existing healthy instance."""

    def __init__(self, log_path: Path = LLAMA_LOG_DEFAULT):
        self._log_path = log_path
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        try:
            with httpx.Client(timeout=1.0) as c:
                return c.get("http://127.0.0.1:8080/health").status_code == 200
        except httpx.HTTPError:
            return False

    def start(self) -> str:
        with self._lock:
            if self.is_running():
                return "already running"
            binary = shutil.which("llama-server")
            if not binary:
                return "llama-server not on PATH — brew install llama.cpp"
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(self._log_path, "a")
            log_handle.write(f"\n--- starting llama-server at {datetime.utcnow().isoformat()} ---\n")
            log_handle.flush()
            self._proc = subprocess.Popen(
                [binary, *LLAMA_ARGS],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # don't tie to tray's process group
            )
            return f"starting (pid {self._proc.pid})"

    def stop(self) -> str:
        with self._lock:
            # Be permissive: kill our own child if we have one, then a
            # blanket pkill in case an earlier tray/terminal started it.
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None
            subprocess.run(["pkill", "-f", "llama-server -hf"], check=False)
            return "stopped"

    def restart(self) -> str:
        self.stop()
        time.sleep(1.0)
        return self.start()


# ---- menu builders ------------------------------------------------------


def _title(state: WorkerState, llama_ok: bool) -> str:
    if state.phase == "translating":
        n, total = state.chunks_done, state.chunks_total
        tps = f" · {state.tokens_per_second:.0f} tok/s" if state.tokens_per_second else ""
        name = state.document_filename or f"job {state.current_job_id}"
        return f"babel · {n}/{total} · {name}{tps}"
    if state.phase == "error" and state.last_error:
        msg = state.last_error
        return f"babel · error: {msg[:60]}{'…' if len(msg) > 60 else ''}"
    if state.phase == "idle" and not llama_ok:
        return "babel · idle · llama-server down"
    return f"babel · {state.phase}"


def _activity_submenu(controller: Controller) -> pystray.Menu:
    events = controller.events[-10:][::-1]  # newest first
    if not events:
        return pystray.Menu(pystray.MenuItem("No activity yet", None, enabled=False))
    items: list[pystray.MenuItem] = []
    for ts, msg in events:
        stamp = ts.strftime("%H:%M:%S")
        items.append(pystray.MenuItem(f"{stamp} — {msg}", None, enabled=False))
    return pystray.Menu(*items)


def _build_menu(
    controller: Controller,
    llama: LlamaManager,
    admin_url: str,
    log_path: Path,
) -> pystray.Menu:
    state = controller.state
    llama_ok = llama.is_running()

    def open_admin(_icon, _item):
        webbrowser.open(admin_url)

    def open_logs(_icon, _item):
        if sys.platform == "darwin":
            subprocess.run(["open", str(log_path)], check=False)
        elif shutil.which("xdg-open"):
            subprocess.run(["xdg-open", str(log_path)], check=False)

    def start_llama(icon, _item):
        controller.log_event(f"llama-server: {llama.start()}")
        _refresh(icon, controller, llama)

    def restart_llama(icon, _item):
        controller.log_event(f"llama-server: {llama.restart()}")
        _refresh(icon, controller, llama)

    def toggle_pause(icon, _item):
        if controller.paused:
            controller.resume()
        else:
            controller.pause()
        _refresh(icon, controller, llama)

    def quit_app(icon, _item):
        controller.stop()
        icon.stop()

    pause_label = "Resume polling" if controller.paused else "Pause polling"
    llama_label = "llama-server: restart" if llama_ok else "llama-server: start"
    llama_action = restart_llama if llama_ok else start_llama

    return pystray.Menu(
        pystray.MenuItem(_title(state, llama_ok), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(llama_label, llama_action),
        pystray.MenuItem(pause_label, toggle_pause),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Recent activity", _activity_submenu(controller)),
        pystray.MenuItem("Open admin panel", open_admin),
        pystray.MenuItem("View logs", open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )


# ---- redraw loop --------------------------------------------------------


def _refresh(icon: "pystray.Icon", controller: Controller, llama: LlamaManager) -> None:
    state = controller.state
    icon.icon = _tower_icon(state.phase)
    icon.title = _title(state, llama.is_running())
    icon.menu = _build_menu(
        controller, llama, icon._admin_url, icon._log_path  # type: ignore[attr-defined]
    )


def _watch(icon: "pystray.Icon", controller: Controller, llama: LlamaManager) -> None:
    """Background thread: repaint icon on state change OR every 10s so the
    llama-server liveness badge stays fresh even while the worker is idle."""
    while not controller.stopped:
        controller.changed.wait(timeout=10.0)
        controller.changed.clear()
        try:
            _refresh(icon, controller, llama)
        except Exception:
            log.exception("redraw failed")


# ---- entry point --------------------------------------------------------


def run(
    cfg: Config,
    *,
    admin_url: str = ADMIN_URL_DEFAULT,
    log_path: Path = LOG_PATH_DEFAULT,
) -> None:
    controller = Controller()
    llama = LlamaManager()

    icon = pystray.Icon(
        "babel-worker",
        _tower_icon("starting"),
        "babel · starting",
        menu=_build_menu(controller, llama, admin_url, log_path),
    )
    icon._admin_url = admin_url  # type: ignore[attr-defined]
    icon._log_path = log_path    # type: ignore[attr-defined]

    loop_thread = threading.Thread(
        target=run_loop, args=(cfg, controller), daemon=True, name="babel-worker-loop"
    )
    watch_thread = threading.Thread(
        target=_watch, args=(icon, controller, llama), daemon=True, name="babel-worker-tray"
    )

    def on_ready(icon):
        icon.visible = True
        loop_thread.start()
        watch_thread.start()
        controller.log_event("tray started")

    try:
        icon.run(setup=on_ready)
    finally:
        controller.stop()
        time.sleep(0.2)
