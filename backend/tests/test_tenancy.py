"""Phase D0 tenancy — per-session file isolation + admin bypass."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Document


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    monkeypatch.setattr(settings, "admin_code", "admin-pass")
    # Make the upload route use a temp uploads dir so the file write
    # doesn't collide with other tests' shared state.
    import tempfile
    from pathlib import Path

    monkeypatch.setattr(settings, "uploads_dir", Path(tempfile.mkdtemp()))

    c = TestClient(app)
    c._engine = engine  # type: ignore[attr-defined]
    yield c
    app.dependency_overrides.clear()


def _upload(client: TestClient, session: str, content: bytes = b"hello world\n\nthis is a tiny test document with enough words to pass ingest\n\n" * 5) -> int:
    r = client.post(
        "/documents",
        headers={"X-Session-ID": session},
        files={"file": ("doc.txt", io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- session isolation ----------


def test_upload_stamps_owner_id(client):
    doc_id = _upload(client, "session-alpha")
    with Session(client._engine) as s:
        doc = s.get(Document, doc_id)
        assert doc.owner_id == "session-alpha"


def test_list_filters_by_session(client):
    _upload(client, "session-alpha")
    _upload(client, "session-beta")

    r = client.get("/documents", headers={"X-Session-ID": "session-alpha"})
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) == 1
    assert docs[0]["owner_id"] == "session-alpha"


def test_get_other_sessions_doc_404s(client):
    alpha_doc = _upload(client, "session-alpha")

    r = client.get(
        f"/documents/{alpha_doc}",
        headers={"X-Session-ID": "session-beta"},
    )
    assert r.status_code == 404


def test_delete_other_sessions_doc_404s(client):
    alpha_doc = _upload(client, "session-alpha")

    r = client.delete(
        f"/documents/{alpha_doc}",
        headers={"X-Session-ID": "session-beta"},
    )
    assert r.status_code == 404
    # Doc still exists for its real owner
    r2 = client.get(
        f"/documents/{alpha_doc}",
        headers={"X-Session-ID": "session-alpha"},
    )
    assert r2.status_code == 200


def test_missing_session_id_returns_400(client):
    r = client.get("/documents")
    assert r.status_code == 400
    assert "X-Session-ID" in r.json()["detail"]


# ---------- admin bypass ----------


def test_admin_sees_all_documents(client):
    _upload(client, "session-alpha")
    _upload(client, "session-beta")

    r = client.get("/documents", headers={"X-Admin-Code": "admin-pass"})
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_admin_can_read_any_document(client):
    beta_doc = _upload(client, "session-beta")
    r = client.get(
        f"/documents/{beta_doc}",
        headers={"X-Admin-Code": "admin-pass"},
    )
    assert r.status_code == 200


def test_admin_upload_is_not_stamped_as_a_session(client):
    r = client.post(
        "/documents",
        headers={"X-Admin-Code": "admin-pass"},
        files={
            "file": (
                "admin.txt",
                io.BytesIO(b"admin content with enough words to get through ingest\n" * 5),
                "text/plain",
            )
        },
    )
    assert r.status_code == 200
    with Session(client._engine) as s:
        doc = s.get(Document, r.json()["id"])
        assert doc.owner_id is None  # admin → legacy NULL, admin-only visible


# ---------- per-session upload cap ----------


def test_upload_cap_is_per_session(client, monkeypatch):
    monkeypatch.setattr(settings, "max_documents_nonadmin", 2)
    _upload(client, "session-alpha")
    _upload(client, "session-alpha")

    # Third upload for this session blocked
    r = client.post(
        "/documents",
        headers={"X-Session-ID": "session-alpha"},
        files={"file": ("x.txt", io.BytesIO(b"third " * 50), "text/plain")},
    )
    assert r.status_code == 429

    # But a DIFFERENT session can still upload (slot is per-session)
    _upload(client, "session-beta")
