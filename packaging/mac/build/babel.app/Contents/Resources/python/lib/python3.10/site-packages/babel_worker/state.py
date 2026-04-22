"""Shared state between the worker loop (background thread) and the tray
icon (main thread). Everything here is thread-safe — the loop mutates via
setters under a lock, the tray reads the dataclass snapshot."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime


@dataclass(frozen=True)
class WorkerState:
    phase: str = "starting"  # starting | idle | translating | paused | error | stopping
    current_job_id: int | None = None
    document_filename: str | None = None
    chunks_done: int = 0
    chunks_total: int = 0
    tokens_per_second: float | None = None
    last_error: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)


class Controller:
    """Thread-safe handle. The loop calls .update() to announce progress;
    the tray reads .state for display and calls .pause()/.resume()/.stop()
    to request action. The loop checks those flags at chunk boundaries."""

    def __init__(self, auto_claim: bool = False) -> None:
        self._lock = threading.RLock()
        self._state = WorkerState()
        self._pause = threading.Event()
        self._stop = threading.Event()
        # Set whenever state changes so watchers (e.g. tray) can redraw.
        self.changed = threading.Event()
        # Bounded activity log shown in the tray menu. Tuples of
        # (timestamp_utc, short_message).
        self._events: deque[tuple[datetime, str]] = deque(maxlen=20)
        # Pull-mode: keep latest queue snapshot so the tray can render it
        # without hitting the network itself.
        self._queue: list = []
        # When the user clicks a queued job in the tray, the loop picks
        # this up on its next iteration.
        self._pending_claim: int | None = None
        # Auto-claim toggle — can be flipped at runtime from the tray.
        self._auto_claim = auto_claim

    @property
    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    def update(self, **fields) -> None:
        with self._lock:
            self._state = replace(self._state, **fields)
        self.changed.set()

    def log_event(self, msg: str) -> None:
        with self._lock:
            self._events.append((datetime.utcnow(), msg))
        self.changed.set()

    @property
    def events(self) -> list[tuple[datetime, str]]:
        with self._lock:
            return list(self._events)

    # --- queue snapshot (manual mode) -----------------------------------

    def set_queue(self, queue: list) -> None:
        with self._lock:
            self._queue = list(queue)
        self.changed.set()

    @property
    def queue(self) -> list:
        with self._lock:
            return list(self._queue)

    def request_claim(self, job_id: int) -> None:
        """Tray calls this when the operator clicks a queued job. Loop
        picks it up on the next iteration and calls /worker/claim/{id}."""
        with self._lock:
            self._pending_claim = job_id
        self.changed.set()

    def take_pending_claim(self) -> int | None:
        with self._lock:
            claim, self._pending_claim = self._pending_claim, None
            return claim

    # --- auto/manual toggle ---------------------------------------------

    @property
    def auto_claim(self) -> bool:
        with self._lock:
            return self._auto_claim

    def set_auto_claim(self, enabled: bool) -> None:
        with self._lock:
            self._auto_claim = enabled
        self.log_event(f"auto-claim: {'on' if enabled else 'off'}")

    # --- pause / resume --------------------------------------------------

    def pause(self) -> None:
        self._pause.set()
        self.update(phase="paused")

    def resume(self) -> None:
        self._pause.clear()
        # Loop will set idle/translating on next iteration; tray shows
        # paused → idle transition for ~1 poll interval.
        if self._state.phase == "paused":
            self.update(phase="idle")

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    # --- stop ------------------------------------------------------------

    def stop(self) -> None:
        self._stop.set()
        self.update(phase="stopping")

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()
