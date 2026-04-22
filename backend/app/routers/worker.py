from __future__ import annotations

import os
import socket
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.deps import WorkerIdentity, require_worker
from app.models import Chunk, Document, GlossaryTerm, Job, JobStatus, Profile
from app.services import credits as credits_svc

router = APIRouter(prefix="/worker", tags=["worker"])


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


class QueueItem(BaseModel):
    job_id: int
    document_filename: str | None
    document_word_count: int | None
    source_lang: str
    target_lang: str
    model_adapter: str
    chunk_count: int
    priority: int
    queued_at: str | None
    submitted_by_admin: bool


@router.get("/queue", response_model=list[QueueItem])
def list_queue(
    session: Session = Depends(get_session),
    worker: WorkerIdentity = Depends(require_worker),
) -> list[QueueItem]:
    """Read-only list of jobs a worker could claim. Used by the tray UI in
    manual mode so the operator can pick which to run."""
    stmt = (
        select(Job, Document)
        .join(Document)
        .where(Job.status == JobStatus.QUEUED)
        .order_by(Job.priority.desc(), Job.queued_at.asc())
    )
    if not worker.is_admin_worker:
        stmt = stmt.where(Document.owner_id == worker.user_id)
    rows = session.exec(stmt).all()
    return [
        QueueItem(
            job_id=job.id,
            document_filename=doc.filename if doc else None,
            document_word_count=doc.word_count if doc else None,
            source_lang=job.source_lang,
            target_lang=job.target_lang,
            model_adapter=job.model_adapter,
            chunk_count=job.chunk_count,
            priority=job.priority,
            queued_at=job.queued_at.isoformat() if job.queued_at else None,
            submitted_by_admin=job.submitted_by_admin,
        )
        for job, doc in rows
    ]


@router.post("/claim/{job_id}", response_model=ClaimResponse)
def claim_specific(
    job_id: int,
    session: Session = Depends(get_session),
    worker: WorkerIdentity = Depends(require_worker),
) -> ClaimResponse:
    """Atomically claim a specific QUEUED job by id. Returns 409 if somebody
    else already claimed it or it's no longer queued. User-workers can only
    claim jobs tied to documents they own."""
    from app.config import settings

    stmt = select(Job).where(Job.id == job_id).where(Job.status == JobStatus.QUEUED)
    if session.bind and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = session.exec(stmt).first()
    if job is None:
        raise HTTPException(status_code=409, detail="job not claimable")
    if not worker.is_admin_worker:
        doc = session.get(Document, job.document_id)
        if doc is None or doc.owner_id != worker.user_id:
            raise HTTPException(status_code=403, detail="job not owned by caller")
    return _claim_and_serialize(job, session, settings.context_chars)


@router.post("/claim-next", response_model=ClaimResponse | None)
def claim_next(
    session: Session = Depends(get_session),
    worker: WorkerIdentity = Depends(require_worker),
) -> ClaimResponse | None:
    """Atomically claim the next QUEUED job (highest priority, oldest first).

    Admin workers claim from the global queue. User workers only see jobs
    whose source document they own — so self-hosted users translate their
    own books and nothing else. Empty queue → null; worker re-polls."""
    from app.config import settings

    stmt = (
        select(Job)
        .join(Document)
        .where(Job.status == JobStatus.QUEUED)
        .order_by(Job.priority.desc(), Job.queued_at.asc())
        .limit(1)
    )
    if not worker.is_admin_worker:
        stmt = stmt.where(Document.owner_id == worker.user_id)
    if session.bind and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    job = session.exec(stmt).first()
    if job is None:
        return None

    return _claim_and_serialize(job, session, settings.context_chars)


def _claim_and_serialize(
    job: Job, session: Session, context_chars: int
) -> ClaimResponse:
    """Flip job → TRANSLATING, gather chunks + glossary, return the claim
    payload. Caller is responsible for having already fetched (and, on
    Postgres, locked) the Job row."""
    job.status = JobStatus.TRANSLATING
    job.started_at = datetime.utcnow()
    job.translated_chunks = 0
    job.error = None
    session.add(job)

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
        context_chars=context_chars,
    )


class ChunkUpdate(BaseModel):
    translated_text: str


@router.post("/jobs/{job_id}/chunks/{idx}")
def upload_chunk(
    job_id: int,
    idx: int,
    body: ChunkUpdate,
    session: Session = Depends(get_session),
    worker: WorkerIdentity = Depends(require_worker),
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
def mark_done(
    job_id: int,
    session: Session = Depends(get_session),
    worker: WorkerIdentity = Depends(require_worker),
) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job.status = JobStatus.DONE
    job.finished_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)

    # Charge the owner for cloud fulfillment only. Self-hosted jobs (worker
    # == doc owner) are free because the user already supplied the compute.
    doc = session.get(Document, job.document_id)
    self_hosted = (
        not worker.is_admin_worker
        and doc is not None
        and doc.owner_id == worker.user_id
    )
    if not self_hosted and doc and doc.owner_id and doc.owner_id != "*":
        profile = session.get(Profile, doc.owner_id)
        credits_svc.charge_for_job(
            session,
            job,
            profile=profile,
            guest_session_id=None if profile else doc.owner_id,
        )

    return {"ok": True, "status": job.status.value, "self_hosted": self_hosted}


class FailBody(BaseModel):
    error: str


@router.post("/jobs/{job_id}/fail")
def mark_failed(
    job_id: int,
    body: FailBody,
    session: Session = Depends(get_session),
    worker: WorkerIdentity = Depends(require_worker),
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
def heartbeat(
    body: HeartbeatBody,
    worker: WorkerIdentity = Depends(require_worker),
) -> dict:
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
