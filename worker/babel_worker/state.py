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

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = WorkerState()
        self._pause = threading.Event()
        self._stop = threading.Event()
        # Set whenever state changes so watchers (e.g. tray) can redraw.
        self.changed = threading.Event()
        # Bounded activity log shown in the tray menu. Tuples of
        # (timestamp_utc, short_message).
        self._events: deque[tuple[datetime, str]] = deque(maxlen=20)

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
