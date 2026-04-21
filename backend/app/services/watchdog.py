from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlmodel import select

from app.db import new_session
from app.models import Chunk, Job, JobStatus

log = logging.getLogger("babel.watchdog")


def _reap_stuck_jobs(stuck_minutes: int) -> int:
    """Mark TRANSLATING jobs as FAILED if no chunk has progressed in N minutes.

    Returns the count of jobs reaped this pass. Safe to call repeatedly; no-op
    when nothing is stale. Writes only if it finds something to fail."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=stuck_minutes)
    reaped = 0

    with new_session() as session:
        running = session.exec(
            select(Job).where(Job.status == JobStatus.TRANSLATING)
        ).all()

        for job in running:
            # Find the most recent chunk progress for this job. Falls back to
            # the job's started_at if no chunk has been translated yet.
            last_chunk = session.exec(
                select(Chunk.translated_at)
                .where(Chunk.job_id == job.id)
                .where(Chunk.translated_at.is_not(None))
                .order_by(Chunk.translated_at.desc())
                .limit(1)
            ).first()

            last_activity = last_chunk or job.started_at
            if last_activity is None:
                continue  # job just started, no heartbeat yet

            if last_activity < cutoff:
                idle = now - last_activity
                minutes = int(idle.total_seconds() // 60)
                log.warning(
                    "reaping stuck job %s: no progress for %d min (last: %s)",
                    job.id,
                    minutes,
                    last_activity.isoformat(),
                )
                job.status = JobStatus.FAILED
                job.error = (
                    f"stuck: no chunk progress for {minutes} min "
                    f"(watchdog threshold {stuck_minutes} min)"
                )
                job.finished_at = now
                session.add(job)
                reaped += 1

        if reaped:
            session.commit()

    return reaped


async def watchdog_loop(
    *, interval_seconds: int = 60, stuck_minutes: int = 10
) -> None:
    """Run _reap_stuck_jobs periodically. Cancellation-safe."""
    log.info(
        "watchdog loop started (interval=%ds, stuck_threshold=%dmin)",
        interval_seconds,
        stuck_minutes,
    )
    try:
        while True:
            try:
                _reap_stuck_jobs(stuck_minutes)
            except Exception:
                log.exception("watchdog sweep failed; will retry next tick")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        log.info("watchdog loop cancelled")
        raise
