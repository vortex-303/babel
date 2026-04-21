from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services.storage import LocalStorage, SupabaseStorage, get_storage


# ---------- LocalStorage ----------


def test_local_storage_put_get_delete(tmp_path: Path):
    s = LocalStorage(root=tmp_path)
    s.put("source/alice.txt", b"hello world")

    assert s.exists("source/alice.txt")
    assert s.get_bytes("source/alice.txt") == b"hello world"
    assert (tmp_path / "source/alice.txt").exists()

    s.delete("source/alice.txt")
    assert not s.exists("source/alice.txt")


def test_local_storage_as_local_path_returns_real_file(tmp_path: Path):
    s = LocalStorage(root=tmp_path)
    s.put("x.pdf", b"pdf-bytes")

    with s.as_local_path("x.pdf") as p:
        assert p == tmp_path / "x.pdf"
        assert p.read_bytes() == b"pdf-bytes"

    # Unlike SupabaseStorage, LocalStorage must NOT delete the underlying
    # file when the context exits — it's the canonical copy.
    assert (tmp_path / "x.pdf").exists()


def test_local_storage_legacy_absolute_paths(tmp_path: Path):
    """Old rows stored an absolute filesystem path in stored_path before the
    storage abstraction existed. LocalStorage must still read those."""
    p = tmp_path / "legacy.pdf"
    p.write_bytes(b"legacy-bytes")

    s = LocalStorage(root=tmp_path / "new_root")
    assert s.exists(str(p))
    assert s.get_bytes(str(p)) == b"legacy-bytes"


def test_local_storage_missing_key_raises(tmp_path: Path):
    s = LocalStorage(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        with s.as_local_path("nope.pdf"):
            pass


# ---------- SupabaseStorage ----------


def _make_supabase(handler) -> SupabaseStorage:
    s = SupabaseStorage(
        url="https://example.supabase.co",
        service_key="test-service-key",
        bucket="babel",
    )
    s.set_transport(httpx.MockTransport(handler))
    return s


def test_supabase_put_hits_correct_url_with_auth():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["headers"] = dict(req.headers)
        captured["body"] = req.content
        return httpx.Response(200, json={"Key": "babel/source/x.txt"})

    s = _make_supabase(handler)
    s.put("source/x.txt", b"data", content_type="text/plain")

    assert captured["url"] == (
        "https://example.supabase.co/storage/v1/object/babel/source/x.txt"
    )
    assert captured["method"] == "PUT"
    assert captured["headers"]["authorization"] == "Bearer test-service-key"
    assert captured["headers"]["apikey"] == "test-service-key"
    assert captured["headers"]["x-upsert"] == "true"
    assert captured["headers"]["content-type"] == "text/plain"
    assert captured["body"] == b"data"


def test_supabase_get_bytes_returns_body():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path == "/storage/v1/object/babel/source/x.txt"
        return httpx.Response(200, content=b"file-contents")

    s = _make_supabase(handler)
    assert s.get_bytes("source/x.txt") == b"file-contents"


def test_supabase_as_local_path_downloads_and_cleans_up():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"alice-pdf")

    s = _make_supabase(handler)
    with s.as_local_path("source/alice.pdf") as p:
        assert p.exists()
        assert p.suffix == ".pdf"  # preserves suffix for mimetype sniffing
        assert p.read_bytes() == b"alice-pdf"
        cached_path = p

    # After the context exits the temp file must be gone.
    assert not cached_path.exists()


def test_supabase_delete_tolerates_404():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    s = _make_supabase(handler)
    s.delete("source/missing.pdf")  # should not raise


def test_supabase_exists_returns_false_on_404():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    s = _make_supabase(handler)
    assert s.exists("nope") is False


def test_supabase_exists_returns_true_on_200():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    s = _make_supabase(handler)
    assert s.exists("yup") is True


# ---------- factory ----------


def test_factory_picks_local_when_supabase_unconfigured(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    monkeypatch.setattr(settings, "uploads_dir", tmp_path)

    s = get_storage()
    assert isinstance(s, LocalStorage)
    assert s.root == tmp_path


def test_factory_picks_supabase_when_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "sk-test")
    monkeypatch.setattr(settings, "storage_bucket", "mybucket")

    s = get_storage()
    assert isinstance(s, SupabaseStorage)
    assert s._bucket == "mybucket"
