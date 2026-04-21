from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import Session, func, select

from app.config import settings
from app.db import get_session, new_session
from app.deps import require_admin
from app.models import Chunk, Document, GlossaryTerm, Job, JobStatus
from app.services import queue as job_queue

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/whoami")
def whoami(_: None = Depends(require_admin)) -> dict:
    """Cheap admin-identity probe for the frontend to know it's authorized."""
    return {"admin": True, "queue_mode": job_queue.get_mode(settings.queue_mode)}


@router.get("/health")
async def admin_health(_: None = Depends(require_admin)) -> dict:
    """Everything an admin needs to know at a glance: backend, llama-server,
    current queue depth, current job in flight."""
    llama_ok = False
    llama_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                f"http://{settings.llamacpp_host}:{settings.llamacpp_port}/health"
            )
            llama_ok = r.status_code == 200
    except Exception as e:
        llama_error = str(e)

    with new_session() as s:
        queued = s.exec(
            select(func.count()).select_from(Job).where(Job.status == JobStatus.QUEUED)
        ).one()
        pending = s.exec(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.PENDING_APPROVAL)
        ).one()
        active = s.exec(
            select(Job).where(Job.status == JobStatus.TRANSLATING).limit(1)
        ).first()
        active_info = None
        if active:
            doc = s.get(Document, active.document_id)
            active_info = {
                "id": active.id,
                "filename": doc.filename if doc else None,
                "translated_chunks": active.translated_chunks,
                "chunk_count": active.chunk_count,
                "started_at": active.started_at.isoformat() if active.started_at else None,
            }

    return {
        "backend": True,
        "llama_server": {
            "ok": llama_ok,
            "host": settings.llamacpp_host,
            "port": settings.llamacpp_port,
            "error": llama_error,
        },
        "queue": {
            "mode": job_queue.get_mode(settings.queue_mode),
            "queued": int(queued),
            "pending_approval": int(pending),
            "active": active_info,
        },
    }


class ModeBody(BaseModel):
    mode: str


@router.post("/mode")
def set_queue_mode(
    body: ModeBody, _: None = Depends(require_admin)
) -> dict:
    try:
        job_queue.set_mode(body.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"mode": job_queue.get_mode(settings.queue_mode)}


@router.get("/queue")
def list_queue(
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
) -> list[dict]:
    """All jobs that are not yet done/failed: pending approval, queued, or
    currently running. Ordered by status then queue position."""
    rows = session.exec(
        select(Job, Document)
        .join(Document)
        .where(
            Job.status.in_(
                (
                    JobStatus.PENDING_APPROVAL,
                    JobStatus.QUEUED,
                    JobStatus.TRANSLATING,
                )
            )
        )
        .order_by(Job.status.asc(), Job.priority.desc(), Job.queued_at.asc())
    ).all()
    return [_serialize_queue_entry(job, doc) for job, doc in rows]


@router.post("/queue/{job_id}/accept")
def accept_job(
    job_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
) -> dict:
    job = _require_job(session, job_id)
    if job.status != JobStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
    job.status = JobStatus.QUEUED
    job.queued_at = job.queued_at or datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    doc = session.get(Document, job.document_id)
    return _serialize_queue_entry(job, doc)


@router.post("/queue/{job_id}/reject")
def reject_job(
    job_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
) -> dict:
    job = _require_job(session, job_id)
    if job.status not in (JobStatus.PENDING_APPROVAL, JobStatus.QUEUED):
        raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
    job.status = JobStatus.REJECTED
    job.finished_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    doc = session.get(Document, job.document_id)
    return _serialize_queue_entry(job, doc)


class PriorityBody(BaseModel):
    priority: int


@router.post("/queue/{job_id}/priority")
def set_priority(
    job_id: int,
    body: PriorityBody,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
) -> dict:
    job = _require_job(session, job_id)
    if job.status not in (JobStatus.QUEUED, JobStatus.PENDING_APPROVAL):
        raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
    job.priority = body.priority
    session.add(job)
    session.commit()
    session.refresh(job)
    doc = session.get(Document, job.document_id)
    return _serialize_queue_entry(job, doc)


@router.post("/purge")
def purge(
    older_than_days: int | None = Query(None, ge=0),
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
) -> dict:
    """Remove documents + their jobs/chunks older than the retention window.
    Admin-initiated; no automatic cron yet (future iteration). Files on disk
    are unlinked best-effort. Returns counts per category."""
    cutoff = datetime.utcnow() - timedelta(
        days=older_than_days if older_than_days is not None else settings.retention_days
    )
    old_docs = session.exec(
        select(Document).where(Document.uploaded_at < cutoff)
    ).all()
    doc_ids = [d.id for d in old_docs]
    files_removed = 0
    for d in old_docs:
        try:
            Path(d.stored_path).unlink(missing_ok=True)
            files_removed += 1
        except Exception:  # keep purging other rows
            pass

    if doc_ids:
        job_ids = [
            j.id
            for j in session.exec(select(Job).where(Job.document_id.in_(doc_ids))).all()
        ]
        if job_ids:
            session.exec(delete(Chunk).where(Chunk.job_id.in_(job_ids)))
            session.exec(delete(GlossaryTerm).where(GlossaryTerm.job_id.in_(job_ids)))
        session.exec(delete(Job).where(Job.document_id.in_(doc_ids)))
        session.exec(delete(Document).where(Document.id.in_(doc_ids)))
        session.commit()

    return {
        "documents_removed": len(doc_ids),
        "files_unlinked": files_removed,
        "cutoff": cutoff.isoformat(),
    }


def _require_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _serialize_queue_entry(job: Job, doc: Document | None) -> dict[str, Any]:
    return {
        "id": job.id,
        "document_filename": doc.filename if doc else None,
        "document_word_count": doc.word_count if doc else None,
        "status": job.status.value,
        "source_lang": job.source_lang,
        "target_lang": job.target_lang,
        "model_adapter": job.model_adapter,
        "priority": job.priority,
        "submitted_by_admin": job.submitted_by_admin,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "translated_chunks": job.translated_chunks,
        "chunk_count": job.chunk_count,
    }
