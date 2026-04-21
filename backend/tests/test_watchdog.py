from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session

from app.models import Chunk, Document, Job, JobStatus


def _seed_job(session_factory, *, chunk_translated_at) -> int:
    with session_factory() as s:
        doc = Document(
            filename="x.txt",
            mime_type="text/plain",
            size_bytes=10,
            word_count=1,
            token_count=1,
            stored_path="/tmp/x.txt",
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)
        job = Job(
            document_id=doc.id,
            status=JobStatus.TRANSLATING,
            source_lang="en",
            target_lang="es",
            model_adapter="rec",
            model_name="rec",
            chunk_count=1,
            started_at=datetime.utcnow() - timedelta(minutes=30),
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        s.add(
            Chunk(
                job_id=job.id,
                idx=0,
                source_text="x",
                token_count=1,
                translated_text="y" if chunk_translated_at else None,
                translated_at=chunk_translated_at,
            )
        )
        s.commit()
        return job.id


def test_watchdog_reaps_job_with_stale_chunk_progress(session_factory, monkeypatch):
    old = datetime.utcnow() - timedelta(minutes=30)
    job_id = _seed_job(session_factory, chunk_translated_at=old)

    from app.services import watchdog

    monkeypatch.setattr(watchdog, "new_session", session_factory)

    reaped = watchdog._reap_stuck_jobs(stuck_minutes=10)

    assert reaped == 1
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert job.error and "stuck" in job.error
        assert job.finished_at is not None


def test_watchdog_leaves_fresh_jobs_alone(session_factory, monkeypatch):
    recent = datetime.utcnow() - timedelta(seconds=30)
    job_id = _seed_job(session_factory, chunk_translated_at=recent)

    from app.services import watchdog

    monkeypatch.setattr(watchdog, "new_session", session_factory)

    reaped = watchdog._reap_stuck_jobs(stuck_minutes=10)

    assert reaped == 0
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.TRANSLATING


def test_watchdog_uses_started_at_when_no_chunks_done(session_factory, monkeypatch):
    job_id = _seed_job(session_factory, chunk_translated_at=None)

    from app.services import watchdog

    monkeypatch.setattr(watchdog, "new_session", session_factory)

    # started_at was 30 min ago, threshold 10 min → should reap.
    reaped = watchdog._reap_stuck_jobs(stuck_minutes=10)

    assert reaped == 1
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.FAILED
