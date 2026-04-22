import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select

from app.config import settings
from app.db import init_db, new_session
from app.models import Job, JobStatus
from app.routers import admin, billing, documents, jobs, passkey, worker
from app.services.queue import queue_loop
from app.services.watchdog import watchdog_loop


def _mark_stale_translations_failed() -> None:
    """Any job stuck in TRANSLATING at boot is dead (its asyncio task died
    with the previous process). Mark them FAILED so the UI doesn't lie."""
    with new_session() as session:
        stale = session.exec(
            select(Job).where(Job.status == JobStatus.TRANSLATING)
        ).all()
        for job in stale:
            job.status = JobStatus.FAILED
            job.error = job.error or "canceled: server restarted mid-translation"
            job.finished_at = datetime.utcnow()
            session.add(job)
        if stale:
            session.commit()


def _init_sentry_if_configured() -> None:
    """Opt-in Sentry hookup. Stays silent when SENTRY_DSN isn't set."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _mark_stale_translations_failed()
    _init_sentry_if_configured()
    watchdog_task = asyncio.create_task(
        watchdog_loop(
            interval_seconds=settings.watchdog_interval_seconds,
            stuck_minutes=settings.watchdog_stuck_minutes,
        )
    )
    # Only run the in-process queue worker when explicitly enabled. On Fly
    # there's no llama-server, so the loop would just churn the queue.
    # Pull-workers (worker/) handle production; inproc is for local dev.
    queue_task: asyncio.Task | None = None
    if settings.inproc_worker:
        queue_task = asyncio.create_task(
            queue_loop(interval_seconds=settings.queue_interval_seconds)
        )
    try:
        yield
    finally:
        tasks = [t for t in (watchdog_task, queue_task) if t is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="babel", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3838", "http://localhost:3838"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(worker.router)
app.include_router(billing.router)
app.include_router(passkey.router)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "adapter": settings.model_adapter,
        "source": settings.source_lang,
        "target": settings.target_lang,
    }


@app.get("/status")
def status() -> dict:
    """Public worker-availability signal for the UI. No auth — only exposes
    aggregate counts, never worker ids or IPs. 'Recent' = heartbeat in the
    last 30s (workers beat every ~5s)."""
    from app.routers.worker import known_workers

    now = datetime.utcnow().timestamp()
    recent = 0
    for h in known_workers():
        try:
            seen = datetime.fromisoformat(h["last_seen"]).timestamp()
        except Exception:
            continue
        if now - seen <= 30:
            recent += 1
    return {"workers_online": recent}
