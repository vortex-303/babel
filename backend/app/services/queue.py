from __future__ import annotations

import asyncio
import logging

from sqlmodel import select

from app.adapters import get_adapter
from app.db import new_session
from app.models import Job, JobStatus
from app.services.translate import translate_job

log = logging.getLogger("babel.queue")

# Mode is stored in settings but surfaced via a small in-memory override so
# admins can flip it at runtime through the admin API without restarting.
_runtime_mode: str | None = None


def get_mode(default: str) -> str:
    return _runtime_mode if _runtime_mode is not None else default


def set_mode(mode: str) -> None:
    global _runtime_mode
    if mode not in {"auto", "manual"}:
        raise ValueError("mode must be 'auto' or 'manual'")
    _runtime_mode = mode
    log.info("queue mode set to %s", mode)


def _pick_next_job() -> int | None:
    """Return the id of the next QUEUED job to run, or None if nothing ready.

    Order: highest priority first, then oldest queued_at. Only returns jobs
    whose status is strictly QUEUED — anything still in PENDING_APPROVAL must
    be accepted by an admin (or auto-promoted in auto mode) before it's
    eligible."""
    with new_session() as s:
        row = s.exec(
            select(Job)
            .where(Job.status == JobStatus.QUEUED)
            .order_by(Job.priority.desc(), Job.queued_at.asc())
            .limit(1)
        ).first()
        return row.id if row else None


def _is_worker_busy() -> bool:
    with new_session() as s:
        row = s.exec(
            select(Job).where(Job.status == JobStatus.TRANSLATING).limit(1)
        ).first()
        return row is not None


async def queue_loop(*, interval_seconds: int = 3) -> None:
    """Serialize translation work: at most one TRANSLATING job at a time.

    Every `interval_seconds`, check for a QUEUED job. If one exists and
    nothing else is translating, invoke translate_job. The orchestrator then
    flips the status to TRANSLATING → DONE/FAILED via its own commits."""
    log.info("queue loop started (interval=%ds)", interval_seconds)
    try:
        while True:
            try:
                if not _is_worker_busy():
                    job_id = _pick_next_job()
                    if job_id is not None:
                        with new_session() as s:
                            job = s.get(Job, job_id)
                            if job is None:
                                continue
                            adapter_name = job.model_adapter
                        adapter = get_adapter(adapter_name)
                        log.info("dispatching job %s → %s", job_id, adapter_name)
                        # Awaited inline: the worker IS the serializer.
                        await translate_job(job_id, adapter, new_session)
            except Exception:
                log.exception("queue loop tick failed; continuing")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        log.info("queue loop cancelled")
        raise
