from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel import Session, func, select

from app.adapters import IMPLEMENTED_ADAPTERS, get_adapter
from app.config import settings
from app.db import get_session, new_session
from app.models import Chunk, Document, GlossaryTerm, Job, JobStatus
from app.services.analyzer import ADAPTER_PROFILES, chunk_document, estimate
from app.services.assemble import ASSEMBLERS
from app.services.glossary import extract_terms
from app.services.ingest import ingest as ingest_document
from app.services.translate import translate_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobBody(BaseModel):
    document_id: int
    source_lang: str | None = None
    target_lang: str | None = None
    model_adapter: str | None = None
    model_name: str | None = None


@router.post("")
def create_job(body: CreateJobBody, session: Session = Depends(get_session)) -> dict:
    doc = session.get(Document, body.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    adapter = body.model_adapter or settings.model_adapter
    if adapter not in ADAPTER_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown adapter {adapter!r}; supported: "
            + ", ".join(ADAPTER_PROFILES.keys()),
        )

    job = Job(
        document_id=doc.id,
        status=JobStatus.UPLOADED,
        source_lang=body.source_lang or settings.source_lang,
        target_lang=body.target_lang or settings.target_lang,
        model_adapter=adapter,
        model_name=body.model_name or settings.llamacpp_model,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return _serialize_job(job, doc)


@router.get("")
def list_jobs(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(Job, Document).join(Document).order_by(Job.created_at.desc())).all()
    return [_serialize_job(job, doc) for job, doc in rows]


@router.get("/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    doc = session.get(Document, job.document_id)
    return _serialize_job(job, doc)


@router.post("/{job_id}/analyze")
def analyze_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    doc = session.get(Document, job.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document missing")

    stored = Path(doc.stored_path)
    if not stored.exists():
        raise HTTPException(status_code=410, detail="uploaded file no longer on disk")

    job.status = JobStatus.ANALYZING
    session.add(job)
    session.commit()

    ingested = ingest_document(stored)
    chunks = chunk_document(ingested, settings.chunk_tokens, settings.chunk_overlap)
    est = estimate(chunks, ingested.word_count, job.model_adapter)

    session.exec(delete(Chunk).where(Chunk.job_id == job.id))
    for c in chunks:
        session.add(
            Chunk(
                job_id=job.id,
                idx=c.idx,
                source_text=c.text,
                token_count=c.token_count,
            )
        )

    job.chunk_count = est.chunk_count
    job.translated_chunks = 0
    job.estimated_seconds = est.estimated_seconds
    job.estimated_cost_usd = est.estimated_cost_usd
    job.status = JobStatus.AWAITING_GLOSSARY_REVIEW
    job.error = None
    session.add(job)
    session.commit()
    session.refresh(job)

    return {
        **_serialize_job(job, doc),
        "analysis": {
            "total_tokens": est.total_tokens,
            "tokens_per_second": est.tokens_per_second,
            "adapter_label": est.adapter_label,
            "chunk_preview": [
                {"idx": c.idx, "tokens": c.token_count, "preview": c.text[:240]}
                for c in chunks[:3]
            ],
        },
    }


@router.get("/{job_id}/chunks")
def list_chunks(job_id: int, session: Session = Depends(get_session)) -> list[dict]:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    rows = session.exec(
        select(Chunk).where(Chunk.job_id == job_id).order_by(Chunk.idx)
    ).all()
    return [
        {
            "idx": c.idx,
            "tokens": c.token_count,
            "source_preview": c.source_text[:200],
            "translated": c.translated_text,
        }
        for c in rows
    ]


@router.post("/{job_id}/translate")
def start_translate(
    job_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.model_adapter not in IMPLEMENTED_ADAPTERS:
        raise HTTPException(
            status_code=400,
            detail=f"adapter {job.model_adapter!r} has no runtime yet; "
            + f"implemented: {sorted(IMPLEMENTED_ADAPTERS)}",
        )
    if job.status in (JobStatus.TRANSLATING, JobStatus.REVIEWING, JobStatus.ASSEMBLING):
        raise HTTPException(status_code=409, detail=f"job is {job.status.value}")

    chunk_count = session.exec(
        select(func.count()).select_from(Chunk).where(Chunk.job_id == job_id)
    ).one()
    if not chunk_count:
        raise HTTPException(status_code=400, detail="no chunks — call /analyze first")

    adapter = get_adapter(job.model_adapter)
    background.add_task(translate_job, job_id, adapter, new_session)

    job.status = JobStatus.TRANSLATING
    job.error = None
    session.add(job)
    session.commit()
    session.refresh(job)

    doc = session.get(Document, job.document_id)
    return _serialize_job(job, doc)


class GlossaryEntry(BaseModel):
    id: int | None = None
    source_term: str
    target_term: str | None = None
    notes: str | None = None
    locked: bool = True
    occurrences: int = 0


class GlossaryUpdate(BaseModel):
    entries: list[GlossaryEntry]


@router.post("/{job_id}/extract-glossary")
def extract_glossary(
    job_id: int,
    session: Session = Depends(get_session),
    top_n: int = Query(50, ge=1, le=200),
    min_occurrences: int = Query(2, ge=1),
) -> list[dict]:
    """Scan the source document for capitalized multi-word terms, persist them
    as GlossaryTerm rows (replaces any existing rows for this job). Returns
    the extracted list for UI review."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    doc = session.get(Document, job.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document missing")
    stored = Path(doc.stored_path)
    if not stored.exists():
        raise HTTPException(status_code=410, detail="uploaded file no longer on disk")

    ingested = ingest_document(stored)
    extracted = extract_terms(
        ingested.full_text,
        top_n=top_n,
        min_occurrences=min_occurrences,
    )

    session.exec(delete(GlossaryTerm).where(GlossaryTerm.job_id == job_id))
    for term in extracted:
        session.add(
            GlossaryTerm(
                job_id=job_id,
                source_term=term.source_term,
                target_term=None,
                occurrences=term.occurrences,
                locked=True,
            )
        )
    session.commit()

    return _list_glossary(job_id, session)


@router.get("/{job_id}/glossary")
def get_glossary(job_id: int, session: Session = Depends(get_session)) -> list[dict]:
    if not session.get(Job, job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return _list_glossary(job_id, session)


@router.put("/{job_id}/glossary")
def update_glossary(
    job_id: int,
    body: GlossaryUpdate,
    session: Session = Depends(get_session),
) -> list[dict]:
    if not session.get(Job, job_id):
        raise HTTPException(status_code=404, detail="job not found")
    # Wipe + rewrite. Keeps the endpoint idempotent and avoids juggling ids.
    session.exec(delete(GlossaryTerm).where(GlossaryTerm.job_id == job_id))
    for e in body.entries:
        if not e.source_term.strip():
            continue
        session.add(
            GlossaryTerm(
                job_id=job_id,
                source_term=e.source_term.strip(),
                target_term=(e.target_term or None),
                notes=e.notes,
                locked=e.locked,
                occurrences=e.occurrences,
            )
        )
    session.commit()
    return _list_glossary(job_id, session)


def _list_glossary(job_id: int, session: Session) -> list[dict]:
    rows = session.exec(
        select(GlossaryTerm)
        .where(GlossaryTerm.job_id == job_id)
        .order_by(GlossaryTerm.occurrences.desc(), GlossaryTerm.source_term)
    ).all()
    return [
        {
            "id": g.id,
            "source_term": g.source_term,
            "target_term": g.target_term,
            "notes": g.notes,
            "locked": g.locked,
            "occurrences": g.occurrences,
        }
        for g in rows
    ]


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.TRANSLATING:
        raise HTTPException(
            status_code=409,
            detail=f"job is {job.status.value}, not translating",
        )
    job.status = JobStatus.FAILED
    job.error = "canceled by user"
    job.finished_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    doc = session.get(Document, job.document_id)
    return _serialize_job(job, doc)


@router.get("/{job_id}/download")
def download_job(
    job_id: int,
    format: str = Query("md", pattern="^(md|docx|epub)$"),
    session: Session = Depends(get_session),
) -> Response:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    doc = session.get(Document, job.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document missing")
    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=f"job is {job.status.value}, not done",
        )

    assembler = ASSEMBLERS.get(format)
    if assembler is None:
        raise HTTPException(status_code=400, detail=f"unknown format {format!r}")

    chunks = session.exec(
        select(Chunk).where(Chunk.job_id == job_id).order_by(Chunk.idx)
    ).all()
    if not chunks:
        raise HTTPException(status_code=400, detail="no chunks to assemble")

    out = assembler(job, doc, chunks)
    return Response(
        content=out.content,
        media_type=out.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{out.filename}"',
        },
    )


def _serialize_job(job: Job, doc: Document | None) -> dict:
    return {
        "id": job.id,
        "document_id": job.document_id,
        "document_filename": doc.filename if doc else None,
        "document_word_count": doc.word_count if doc else None,
        "status": job.status.value,
        "source_lang": job.source_lang,
        "target_lang": job.target_lang,
        "model_adapter": job.model_adapter,
        "model_name": job.model_name,
        "chunk_count": job.chunk_count,
        "translated_chunks": job.translated_chunks,
        "estimated_seconds": job.estimated_seconds,
        "estimated_cost_usd": job.estimated_cost_usd,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
