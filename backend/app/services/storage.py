from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol

import httpx


class Storage(Protocol):
    """Object storage interface. Two implementations today: local filesystem
    and Supabase Storage. Sync API — fine for the upload/download path sizes
    we actually process (a handful of MB up to ~100 MB), and keeps the
    existing sync routes in routers/* untouched."""

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    @contextmanager
    def as_local_path(self, key: str) -> Iterator[Path]:
        """Yield a local filesystem path to the object. LocalStorage returns
        the real file; SupabaseStorage downloads to a temp path which is
        deleted when the context exits. Callers treat the path read-only."""
        ...


class LocalStorage:
    """Backs keys with files on local disk under `root`. Legacy absolute
    paths stored before the storage abstraction existed are still honored
    (any key starting with '/' is treated as an absolute path)."""

    name = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _resolve(self, key: str) -> Path:
        if key.startswith("/"):
            return Path(key)  # legacy row
        return self.root / key

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    @contextmanager
    def as_local_path(self, key: str) -> Iterator[Path]:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"object not found: {key}")
        yield path


class SupabaseStorage:
    """Minimal REST client for Supabase Storage. Uses the service-role key,
    so this must never be exposed to the frontend."""

    name = "supabase"

    def __init__(self, url: str, service_key: str, bucket: str, timeout: float = 60.0):
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        }
        self._timeout = timeout
        self._transport: httpx.BaseTransport | None = None

    def set_transport(self, transport: httpx.BaseTransport) -> None:
        """Test hook — inject an httpx.MockTransport."""
        self._transport = transport

    def _client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=self._timeout)
        return httpx.Client(timeout=self._timeout)

    def _object_url(self, key: str) -> str:
        return f"{self._base}/object/{self._bucket}/{key.lstrip('/')}"

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        url = self._object_url(key)
        headers = {**self._headers, "x-upsert": "true"}
        if content_type:
            headers["Content-Type"] = content_type
        with self._client() as c:
            r = c.put(url, content=data, headers=headers)
            r.raise_for_status()

    def get_bytes(self, key: str) -> bytes:
        url = self._object_url(key)
        with self._client() as c:
            r = c.get(url, headers=self._headers)
            r.raise_for_status()
            return r.content

    def delete(self, key: str) -> None:
        url = self._object_url(key)
        with self._client() as c:
            r = c.delete(url, headers=self._headers)
            # 200 OK on delete, 404 if already gone — both fine for our use.
            if r.status_code not in (200, 404):
                r.raise_for_status()

    def exists(self, key: str) -> bool:
        url = self._object_url(key)
        with self._client() as c:
            r = c.head(url, headers=self._headers)
            return r.status_code == 200

    @contextmanager
    def as_local_path(self, key: str) -> Iterator[Path]:
        data = self.get_bytes(key)
        # Preserve the file suffix so downstream libraries (pymupdf, ebooklib,
        # python-docx) sniff the right format.
        suffix = Path(key).suffix or ""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            temp_path = Path(tmp.name)
        try:
            yield temp_path
        finally:
            temp_path.unlink(missing_ok=True)


def get_storage() -> Storage:
    """Factory: Supabase when configured, local otherwise. Called at request
    time so config changes apply without a restart (tests mutate settings)."""
    from app.config import settings

    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseStorage(
            url=settings.supabase_url,
            service_key=settings.supabase_service_key,
            bucket=settings.storage_bucket,
        )
    return LocalStorage(root=settings.uploads_dir)
