from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select

from app.config import settings
from app.db import init_db, new_session
from app.models import Job, JobStatus
from app.routers import documents, jobs


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _mark_stale_translations_failed()
    yield


app = FastAPI(title="babel", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3838", "http://localhost:3838"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(jobs.router)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "adapter": settings.model_adapter,
        "source": settings.source_lang,
        "target": settings.target_lang,
    }
