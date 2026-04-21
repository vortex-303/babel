from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlmodel import Session, select

from app.adapters import TranslationAdapter, TranslationRequest
from app.models import Chunk, GlossaryTerm, Job, JobStatus


SessionFactory = Callable[[], Session]


async def translate_job(
    job_id: int,
    adapter: TranslationAdapter,
    session_factory: SessionFactory,
    context_chars: int = 600,
) -> None:
    """Translate every chunk for a job sequentially.

    Each chunk after the first is sent with the tail of the previous
    translated chunk as `context` — the adapter slots this into the prompt
    as "previous passage, for continuity; do not re-translate", so tone and
    vocabulary carry across chunk boundaries without re-translation."""

    with session_factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        source = job.source_lang
        target = job.target_lang
        job.status = JobStatus.TRANSLATING
        job.started_at = datetime.utcnow()
        job.translated_chunks = 0
        job.error = None
        session.add(job)
        session.commit()

    with session_factory() as session:
        chunk_ids = [
            c.id
            for c in session.exec(
                select(Chunk).where(Chunk.job_id == job_id).order_by(Chunk.idx)
            ).all()
        ]
        # Glossary once per job — it doesn't change mid-run. Only include
        # entries that have a target_term set by the user (or defaulted).
        glossary_all: list[tuple[str, str]] = [
            (g.source_term, g.target_term)
            for g in session.exec(
                select(GlossaryTerm)
                .where(GlossaryTerm.job_id == job_id)
                .where(GlossaryTerm.target_term.is_not(None))
                .where(GlossaryTerm.target_term != "")
            ).all()
        ]

    prev_translated: str | None = None
    for chunk_id in chunk_ids:
        # Check for cancellation each iteration — if a user hit /cancel the
        # job row flips to FAILED and we should stop ASAP.
        with session_factory() as session:
            current = session.get(Job, job_id)
            if current is None or current.status != JobStatus.TRANSLATING:
                return
            chunk = session.get(Chunk, chunk_id)
            if chunk is None:
                continue
            source_text = chunk.source_text

        context = (
            prev_translated[-context_chars:]
            if prev_translated and context_chars > 0
            else None
        )

        # Keep the prompt compact by filtering the glossary to terms that
        # actually appear in this chunk's source text.
        chunk_glossary = (
            [(src, tgt) for src, tgt in glossary_all if src in source_text]
            if glossary_all
            else None
        ) or None

        try:
            result = await adapter.translate(
                TranslationRequest(
                    text=source_text,
                    source_lang=source,
                    target_lang=target,
                    context=context,
                    glossary=chunk_glossary,
                )
            )
        except Exception as e:
            with session_factory() as session:
                failed = session.get(Job, job_id)
                if failed is not None and failed.status == JobStatus.TRANSLATING:
                    failed.status = JobStatus.FAILED
                    failed.error = f"chunk {chunk_id}: {e}"
                    failed.finished_at = datetime.utcnow()
                    session.add(failed)
                    session.commit()
            return

        prev_translated = result.text

        with session_factory() as session:
            chunk = session.get(Chunk, chunk_id)
            if chunk is not None:
                chunk.translated_text = result.text
                chunk.translated_at = datetime.utcnow()
                session.add(chunk)
            running = session.get(Job, job_id)
            if running is not None:
                running.translated_chunks += 1
                session.add(running)
            session.commit()

    with session_factory() as session:
        done = session.get(Job, job_id)
        if done is not None and done.status == JobStatus.TRANSLATING:
            done.status = JobStatus.DONE
            done.finished_at = datetime.utcnow()
            session.add(done)
            session.commit()
