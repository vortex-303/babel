from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Chunk, Document, GlossaryTerm, Job, JobStatus


@pytest.fixture
def client(monkeypatch):
    # Fresh in-memory DB for each test. StaticPool is load-bearing: SQLite
    # `:memory:` otherwise creates a new DB per connection, which breaks the
    # moment the TestClient opens a second request against the same engine.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    monkeypatch.setattr(settings, "worker_token", "test-token")

    c = TestClient(app)
    # Stash engine so tests can seed directly.
    c._engine = engine  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()


def _seed_queued_job(engine, *, source_lang="en", target_lang="es"):
    with Session(engine) as s:
        doc = Document(
            filename="alice.txt",
            mime_type="text/plain",
            size_bytes=100,
            word_count=50,
            token_count=80,
            stored_path="source/alice.txt",
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)

        job = Job(
            document_id=doc.id,
            status=JobStatus.QUEUED,
            source_lang=source_lang,
            target_lang=target_lang,
            model_adapter="llamacpp",
            model_name="test-model",
            chunk_count=2,
            priority=0,
        )
        s.add(job)
        s.commit()
        s.refresh(job)

        for i, text in enumerate(["Alice fell down.", "The rabbit ran fast."]):
            s.add(Chunk(job_id=job.id, idx=i, source_text=text, token_count=10))

        # One glossary entry
        s.add(
            GlossaryTerm(
                job_id=job.id,
                source_term="Alice",
                target_term="Alicia",
                occurrences=1,
                locked=True,
            )
        )
        s.commit()
        return job.id


# ---------- auth ----------


def test_unauthenticated_claim_returns_401(client):
    r = client.post("/worker/claim-next")
    assert r.status_code == 401


def test_wrong_token_returns_403(client):
    r = client.post(
        "/worker/claim-next", headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 403


def test_gate_disabled_when_token_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "worker_token", "")
    r = client.post(
        "/worker/claim-next", headers={"Authorization": "Bearer anything"}
    )
    assert r.status_code == 403
    assert "not configured" in r.json()["detail"]


# ---------- claim-next ----------


def test_claim_next_returns_null_on_empty_queue(client):
    r = client.post(
        "/worker/claim-next", headers={"Authorization": "Bearer test-token"}
    )
    assert r.status_code == 200
    assert r.json() is None


def test_claim_next_returns_job_and_flips_status(client):
    job_id = _seed_queued_job(client._engine)

    r = client.post(
        "/worker/claim-next", headers={"Authorization": "Bearer test-token"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == job_id
    assert data["source_lang"] == "en"
    assert data["target_lang"] == "es"
    assert len(data["chunks"]) == 2
    assert data["chunks"][0]["source_text"] == "Alice fell down."
    assert data["glossary"] == [{"source_term": "Alice", "target_term": "Alicia"}]

    # Job must have transitioned to TRANSLATING.
    with Session(client._engine) as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.TRANSLATING
        assert job.started_at is not None


def test_claim_next_respects_priority(client):
    e = client._engine
    with Session(e) as s:
        doc = Document(
            filename="x", mime_type="text/plain", size_bytes=1,
            word_count=1, token_count=1, stored_path="x",
        )
        s.add(doc)
        s.commit(); s.refresh(doc)
        low = Job(
            document_id=doc.id, status=JobStatus.QUEUED,
            source_lang="en", target_lang="es",
            model_adapter="llamacpp", model_name="m",
            chunk_count=0, priority=0,
        )
        high = Job(
            document_id=doc.id, status=JobStatus.QUEUED,
            source_lang="en", target_lang="es",
            model_adapter="llamacpp", model_name="m",
            chunk_count=0, priority=10,
        )
        s.add(low); s.add(high); s.commit(); s.refresh(high)
        high_id = high.id

    r = client.post(
        "/worker/claim-next", headers={"Authorization": "Bearer test-token"}
    )
    assert r.json()["job_id"] == high_id


# ---------- chunk upload ----------


def test_upload_chunk_writes_translated_text(client):
    job_id = _seed_queued_job(client._engine)
    # First claim so the job has status TRANSLATING.
    client.post("/worker/claim-next", headers={"Authorization": "Bearer test-token"})

    r = client.post(
        f"/worker/jobs/{job_id}/chunks/0",
        headers={"Authorization": "Bearer test-token"},
        json={"translated_text": "Alicia cayó."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["translated_chunks"] == 1
    assert body["chunk_count"] == 2


def test_upload_chunk_is_idempotent(client):
    job_id = _seed_queued_job(client._engine)
    client.post("/worker/claim-next", headers={"Authorization": "Bearer test-token"})

    for _ in range(3):
        r = client.post(
            f"/worker/jobs/{job_id}/chunks/0",
            headers={"Authorization": "Bearer test-token"},
            json={"translated_text": "Alicia cayó."},
        )
        assert r.status_code == 200
        # Counter reflects distinct translated chunks, not the number of posts.
        assert r.json()["translated_chunks"] == 1


def test_upload_missing_chunk_returns_404(client):
    job_id = _seed_queued_job(client._engine)
    r = client.post(
        f"/worker/jobs/{job_id}/chunks/999",
        headers={"Authorization": "Bearer test-token"},
        json={"translated_text": "x"},
    )
    assert r.status_code == 404


# ---------- done / fail ----------


def test_mark_done_transitions_status(client):
    job_id = _seed_queued_job(client._engine)
    client.post("/worker/claim-next", headers={"Authorization": "Bearer test-token"})

    r = client.post(
        f"/worker/jobs/{job_id}/done",
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 200

    with Session(client._engine) as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.DONE
        assert job.finished_at is not None


def test_mark_failed_stores_error(client):
    job_id = _seed_queued_job(client._engine)
    client.post("/worker/claim-next", headers={"Authorization": "Bearer test-token"})

    r = client.post(
        f"/worker/jobs/{job_id}/fail",
        headers={"Authorization": "Bearer test-token"},
        json={"error": "llama-server went down"},
    )
    assert r.status_code == 200

    with Session(client._engine) as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert "llama-server" in (job.error or "")


# ---------- heartbeat ----------


def test_heartbeat_accepts_minimal_body(client):
    r = client.post(
        "/worker/heartbeat",
        headers={"Authorization": "Bearer test-token"},
        json={"worker_id": "test-worker"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------- list queue / targeted claim ----------


def test_queue_lists_queued_jobs(client):
    job_id = _seed_queued_job(client._engine)
    r = client.get(
        "/worker/queue", headers={"Authorization": "Bearer test-token"}
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["job_id"] == job_id
    assert body[0]["source_lang"] == "en"
    assert body[0]["chunk_count"] == 2


def test_queue_is_empty_when_nothing_queued(client):
    r = client.get(
        "/worker/queue", headers={"Authorization": "Bearer test-token"}
    )
    assert r.status_code == 200
    assert r.json() == []


def test_claim_specific_transitions_that_job(client):
    job_id = _seed_queued_job(client._engine)

    r = client.post(
        f"/worker/claim/{job_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 200
    assert r.json()["job_id"] == job_id

    with Session(client._engine) as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.TRANSLATING


def test_claim_specific_409_on_already_claimed(client):
    job_id = _seed_queued_job(client._engine)
    # Take it first
    client.post(
        f"/worker/claim/{job_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    # Second claim should fail cleanly
    r = client.post(
        f"/worker/claim/{job_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert r.status_code == 409


def test_claim_specific_auth_required(client):
    job_id = _seed_queued_job(client._engine)
    r = client.post(f"/worker/claim/{job_id}")
    assert r.status_code == 401
    r = client.post(
        f"/worker/claim/{job_id}",
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 403
