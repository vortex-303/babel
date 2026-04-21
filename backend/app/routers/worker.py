from __future__ import annotations

import os
import socket
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_worker
from app.models import Chunk, Document, GlossaryTerm, Job, JobStatus

router = APIRouter(prefix="/worker", tags=["worker"], dependencies=[Depends(require_worker)])


# In-memory heartbeat tracking. Cheap and good enough for admin visibility.
# Survives a single Fly machine's lifetime; if the machine restarts we forget,
# which is fine — worker re-posts within seconds.
_HEARTBEATS: dict[str, dict] = {}


class ChunkOut(BaseModel):
    id: int
    idx: int
    source_text: str


class GlossaryEntryOut(BaseModel):
    source_term: str
    target_term: str


class ClaimResponse(BaseModel):
    job_id: int
    document_filename: str | None
    source_lang: str
    target_lang: str
    model_adapter: str
    model_name: str
    chunks: list[ChunkOut]
    glossary: list[GlossaryEntryOut]
    context_chars: int


@router.post("/claim-next", response_model=ClaimResponse | None)
def claim_next(session: Session = Depends(get_session)) -> ClaimResponse | None:
    """Atomically claim the next QUEUED job (highest priority, oldest first).

    Flips status to TRANSLATING in the same transaction so two concurrent
    workers can't race on the same job. Returns null when the queue is
    empty — the worker polls again after a short delay."""
    from app.config import settings

    # Single-statement claim using FOR UPDATE SKIP LOCKED so parallel workers
    # grab distinct jobs. Falls back to plain select on SQLite.
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.QUEUED)
        .order_by(Job.priority.desc(), Job.queued_at.asc())
        .limit(1)
    )
    if session.bind and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    job = session.exec(stmt).first()
    if job is None:
        return None

    job.status = JobStatus.TRANSLATING
    job.started_at = datetime.utcnow()
    job.translated_chunks = 0
    job.error = None
    session.add(job)

    # Fetch chunks + glossary in the same session so the response is
    # consistent with the status transition.
    chunks = session.exec(
        select(Chunk).where(Chunk.job_id == job.id).order_by(Chunk.idx)
    ).all()

    glossary = [
        GlossaryEntryOut(source_term=g.source_term, target_term=g.target_term)
        for g in session.exec(
            select(GlossaryTerm)
            .where(GlossaryTerm.job_id == job.id)
            .where(GlossaryTerm.target_term.is_not(None))
            .where(GlossaryTerm.target_term != "")
        ).all()
    ]

    doc = session.get(Document, job.document_id)
    session.commit()
    session.refresh(job)

    return ClaimResponse(
        job_id=job.id,
        document_filename=doc.filename if doc else None,
        source_lang=job.source_lang,
        target_lang=job.target_lang,
        model_adapter=job.model_adapter,
        model_name=job.model_name,
        chunks=[
            ChunkOut(id=c.id, idx=c.idx, source_text=c.source_text) for c in chunks
        ],
        glossary=glossary,
        context_chars=settings.context_chars,
    )


class ChunkUpdate(BaseModel):
    translated_text: str


@router.post("/jobs/{job_id}/chunks/{idx}")
def upload_chunk(
    job_id: int,
    idx: int,
    body: ChunkUpdate,
    session: Session = Depends(get_session),
) -> dict:
    """Save one translated chunk. Idempotent — re-uploads overwrite. Keeps
    job.translated_chunks in sync with actual non-null chunks rather than
    blindly incrementing, so retries don't double-count."""
    chunk = session.exec(
        select(Chunk).where(Chunk.job_id == job_id).where(Chunk.idx == idx)
    ).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk not found")

    chunk.translated_text = body.translated_text
    chunk.translated_at = datetime.utcnow()
    session.add(chunk)

    # Recompute counter from reality.
    translated_count = session.exec(
        select(Chunk)
        .where(Chunk.job_id == job_id)
        .where(Chunk.translated_text.is_not(None))
    ).all()
    count = len(translated_count)

    job = session.get(Job, job_id)
    if job:
        job.translated_chunks = count
        session.add(job)

    session.commit()
    return {
        "ok": True,
        "translated_chunks": count,
        "chunk_count": job.chunk_count if job else None,
    }


@router.post("/jobs/{job_id}/done")
def mark_done(job_id: int, session: Session = Depends(get_session)) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job.status = JobStatus.DONE
    job.finished_at = datetime.utcnow()
    session.add(job)
    session.commit()
    return {"ok": True, "status": job.status.value}


class FailBody(BaseModel):
    error: str


@router.post("/jobs/{job_id}/fail")
def mark_failed(
    job_id: int,
    body: FailBody,
    session: Session = Depends(get_session),
) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job.status = JobStatus.FAILED
    job.error = body.error[:500]
    job.finished_at = datetime.utcnow()
    session.add(job)
    session.commit()
    return {"ok": True, "status": job.status.value}


class HeartbeatBody(BaseModel):
    worker_id: str
    hostname: str | None = None
    gpu: str | None = None
    tokens_per_second: float | None = None
    current_job_id: int | None = None


@router.post("/heartbeat")
def heartbeat(body: HeartbeatBody) -> dict:
    _HEARTBEATS[body.worker_id] = {
        **body.model_dump(),
        "last_seen": datetime.utcnow().isoformat(),
        "fly_region": os.environ.get("FLY_REGION"),
        "fly_machine": socket.gethostname(),
    }
    # Prune workers we haven't heard from in an hour so the admin page
    # doesn't show stale entries forever.
    cutoff = datetime.utcnow().timestamp() - 3600
    stale = [
        wid
        for wid, h in _HEARTBEATS.items()
        if datetime.fromisoformat(h["last_seen"]).timestamp() < cutoff
    ]
    for wid in stale:
        _HEARTBEATS.pop(wid, None)
    return {"ok": True, "known_workers": len(_HEARTBEATS)}


def known_workers() -> list[dict]:
    """Read-only view for the admin router."""
    return list(_HEARTBEATS.values())
