from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import Chunk, Document, Job, JobStatus
from app.services import queue as job_queue


def test_queue_mode_default():
    job_queue._runtime_mode = None
    assert job_queue.get_mode("auto") == "auto"
    assert job_queue.get_mode("manual") == "manual"


def test_queue_mode_override():
    job_queue._runtime_mode = None
    job_queue.set_mode("manual")
    assert job_queue.get_mode("auto") == "manual"
    job_queue.set_mode("auto")
    assert job_queue.get_mode("manual") == "auto"
    # Cleanup for other tests.
    job_queue._runtime_mode = None


def test_queue_mode_rejects_invalid():
    with pytest.raises(ValueError):
        job_queue.set_mode("paused")


def _seed_job(
    session_factory, *, status: JobStatus, queued_at: datetime | None = None, priority: int = 0
) -> int:
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
            status=status,
            source_lang="en",
            target_lang="es",
            model_adapter="rec",
            model_name="rec",
            chunk_count=1,
            queued_at=queued_at,
            priority=priority,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        s.add(Chunk(job_id=job.id, idx=0, source_text="x", token_count=1))
        s.commit()
        return job.id


def test_pick_next_returns_oldest_queued(session_factory, monkeypatch):
    monkeypatch.setattr(job_queue, "new_session", session_factory)

    now = datetime.utcnow()
    older = _seed_job(
        session_factory, status=JobStatus.QUEUED, queued_at=now - timedelta(minutes=5)
    )
    _ = _seed_job(
        session_factory, status=JobStatus.QUEUED, queued_at=now
    )

    assert job_queue._pick_next_job() == older


def test_pick_next_respects_priority(session_factory, monkeypatch):
    monkeypatch.setattr(job_queue, "new_session", session_factory)

    now = datetime.utcnow()
    _low = _seed_job(
        session_factory,
        status=JobStatus.QUEUED,
        queued_at=now - timedelta(minutes=10),
        priority=0,
    )
    high = _seed_job(
        session_factory,
        status=JobStatus.QUEUED,
        queued_at=now,
        priority=10,
    )

    assert job_queue._pick_next_job() == high


def test_pick_next_skips_pending_approval(session_factory, monkeypatch):
    monkeypatch.setattr(job_queue, "new_session", session_factory)

    _seed_job(
        session_factory,
        status=JobStatus.PENDING_APPROVAL,
        queued_at=datetime.utcnow(),
    )
    assert job_queue._pick_next_job() is None


def test_is_worker_busy_detects_translating(session_factory, monkeypatch):
    monkeypatch.setattr(job_queue, "new_session", session_factory)
    assert job_queue._is_worker_busy() is False
    _seed_job(session_factory, status=JobStatus.TRANSLATING)
    assert job_queue._is_worker_busy() is True
