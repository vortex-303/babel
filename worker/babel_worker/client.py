"""HTTP client for the babel backend's /api/worker/* endpoints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

import httpx

log = logging.getLogger("babel_worker.client")

T = TypeVar("T")

# 5xx from Fly during scale-up/maintenance + any network timeout should
# not kill a running job. Retry with exponential backoff before surfacing.
# With _MAX_RETRIES=6 and _INITIAL_BACKOFF=3, total patience is roughly
# 3+6+12+24+48+96 ≈ 3 minutes before we give up — enough for a Fly machine
# to cold-start and take traffic.
_RETRY_STATUS = {502, 503, 504}
_MAX_RETRIES = 6
_INITIAL_BACKOFF_SECONDS = 3.0


def _retry(op_name: str, fn: Callable[[], T]) -> T:
    delay = _INITIAL_BACKOFF_SECONDS
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES:
                raise
            log.warning(
                "%s got %s — retry %d/%d in %.1fs",
                op_name, e.response.status_code, attempt, _MAX_RETRIES, delay,
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            if attempt == _MAX_RETRIES:
                raise
            log.warning(
                "%s network blip (%s) — retry %d/%d in %.1fs",
                op_name, type(e).__name__, attempt, _MAX_RETRIES, delay,
            )
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"unreachable: {op_name} retry exhausted without raise")


@dataclass
class QueueItem:
    """Summary of a queued job — what the tray UI shows for the operator
    to pick from. Doesn't include chunk text (too large for the menu)."""
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


@dataclass
class ChunkToTranslate:
    id: int
    idx: int
    source_text: str


@dataclass
class ClaimedJob:
    job_id: int
    document_filename: str | None
    source_lang: str
    target_lang: str
    model_adapter: str
    model_name: str
    chunks: list[ChunkToTranslate]
    glossary: list[tuple[str, str]]
    context_chars: int


class SupabaseAuth:
    """Handles the Supabase password → access_token exchange + refresh.

    The access token has a short lifetime (default 1h). We keep it in memory
    and refresh 60s before expiry. A hard-failure during refresh falls back
    to re-login with the stored email+password, so the worker recovers even
    after a long pause (laptop closed overnight)."""

    def __init__(self, supabase_url: str, anon_key: str, email: str, password: str):
        self._url = supabase_url.rstrip("/")
        self._anon = anon_key
        self._email = email
        self._password = password
        self._access: str | None = None
        self._refresh: str | None = None
        self._expires_at: float = 0.0

    def bearer(self) -> str:
        """Return a valid access token, refreshing / re-logging-in as needed."""
        now = time.time()
        if self._access and now < self._expires_at - 60:
            return self._access
        if self._refresh:
            try:
                self._do_refresh()
                return self._access  # type: ignore[return-value]
            except httpx.HTTPError as e:
                log.warning("refresh failed (%s) — re-logging in", e)
        self._do_login()
        return self._access  # type: ignore[return-value]

    def _do_login(self) -> None:
        r = httpx.post(
            f"{self._url}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": self._anon, "Content-Type": "application/json"},
            json={"email": self._email, "password": self._password},
            timeout=30.0,
        )
        if r.status_code >= 400:
            raise SystemExit(
                f"Supabase login failed ({r.status_code}): {r.text[:300]}\n"
                f"Check BABEL_WORKER_EMAIL + BABEL_WORKER_PASSWORD."
            )
        self._apply(r.json())

    def _do_refresh(self) -> None:
        r = httpx.post(
            f"{self._url}/auth/v1/token",
            params={"grant_type": "refresh_token"},
            headers={"apikey": self._anon, "Content-Type": "application/json"},
            json={"refresh_token": self._refresh},
            timeout=30.0,
        )
        r.raise_for_status()
        self._apply(r.json())

    def _apply(self, payload: dict) -> None:
        self._access = payload["access_token"]
        self._refresh = payload.get("refresh_token", self._refresh)
        expires_in = int(payload.get("expires_in", 3600))
        self._expires_at = time.time() + expires_in


class BackendClient:
    def __init__(
        self,
        backend_url: str,
        worker_token: str = "",
        supabase: SupabaseAuth | None = None,
        timeout: float = 180.0,
    ):
        # `backend_url` should point at the FastAPI root. When pointing
        # directly at Fly (api.babeltower.lat) that's just the bare URL.
        # Only prepend the /api prefix if the user pointed us at Vercel
        # (babeltower.lat, which rewrites /api/* → Fly). Detection: look for
        # the api.* subdomain; anything else gets the /api prefix.
        base = backend_url.rstrip("/")
        if "://api." not in base:
            base = base + "/api"
        self._base = base
        self._supabase = supabase
        self._worker_token = worker_token
        # httpx auth header is set per-request when using Supabase so the
        # short-lived access_token is always fresh.
        self._client = httpx.Client(timeout=timeout)

    def _auth_header(self) -> dict[str, str]:
        if self._supabase is not None:
            return {"Authorization": f"Bearer {self._supabase.bearer()}"}
        return {"Authorization": f"Bearer {self._worker_token}"}

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {**kw.pop("headers", {}), **self._auth_header()}
        return self._client.request(method, f"{self._base}{path}", headers=headers, **kw)

    def close(self) -> None:
        self._client.close()

    def claim_next(self) -> ClaimedJob | None:
        def _do() -> ClaimedJob | None:
            r = self._request("POST", "/worker/claim-next")
            r.raise_for_status()
            return self._parse_claim(r)
        return _retry("claim-next", _do)

    def claim(self, job_id: int) -> ClaimedJob | None:
        """Claim a specific job by id. Returns None if it's been snatched by
        someone else or is no longer QUEUED."""
        def _do() -> ClaimedJob | None:
            r = self._request("POST", f"/worker/claim/{job_id}")
            if r.status_code == 409:
                return None
            r.raise_for_status()
            return self._parse_claim(r)
        return _retry(f"claim({job_id})", _do)

    def list_queue(self) -> list[QueueItem]:
        def _do() -> list[QueueItem]:
            r = self._request("GET", "/worker/queue")
            r.raise_for_status()
            return [
                QueueItem(
                    job_id=q["job_id"],
                    document_filename=q.get("document_filename"),
                    document_word_count=q.get("document_word_count"),
                    source_lang=q["source_lang"],
                    target_lang=q["target_lang"],
                    model_adapter=q["model_adapter"],
                    chunk_count=q["chunk_count"],
                    priority=q["priority"],
                    queued_at=q.get("queued_at"),
                    submitted_by_admin=q.get("submitted_by_admin", False),
                )
                for q in r.json()
            ]
        return _retry("list-queue", _do)

    def _parse_claim(self, r: httpx.Response) -> ClaimedJob | None:
        if r.status_code == 204 or not r.content or r.content == b"null":
            return None
        data = r.json()
        if data is None:
            return None
        return ClaimedJob(
            job_id=data["job_id"],
            document_filename=data.get("document_filename"),
            source_lang=data["source_lang"],
            target_lang=data["target_lang"],
            model_adapter=data["model_adapter"],
            model_name=data["model_name"],
            chunks=[
                ChunkToTranslate(id=c["id"], idx=c["idx"], source_text=c["source_text"])
                for c in data["chunks"]
            ],
            glossary=[
                (g["source_term"], g["target_term"]) for g in data["glossary"]
            ],
            context_chars=data["context_chars"],
        )

    def upload_chunk(self, job_id: int, idx: int, translated_text: str) -> dict:
        def _do() -> dict:
            r = self._request(
                "POST",
                f"/worker/jobs/{job_id}/chunks/{idx}",
                json={"translated_text": translated_text},
            )
            r.raise_for_status()
            return r.json()
        return _retry(f"upload-chunk({job_id}.{idx})", _do)

    def mark_done(self, job_id: int) -> None:
        def _do() -> None:
            r = self._request("POST", f"/worker/jobs/{job_id}/done")
            r.raise_for_status()
        _retry(f"mark-done({job_id})", _do)

    def mark_failed(self, job_id: int, error: str) -> None:
        def _do() -> None:
            r = self._request(
                "POST",
                f"/worker/jobs/{job_id}/fail",
                json={"error": error},
            )
            r.raise_for_status()
        _retry(f"mark-failed({job_id})", _do)

    def heartbeat(
        self,
        *,
        worker_id: str,
        hostname: str | None = None,
        gpu: str | None = None,
        tokens_per_second: float | None = None,
        current_job_id: int | None = None,
    ) -> None:
        try:
            self._request(
                "POST",
                "/worker/heartbeat",
                json={
                    "worker_id": worker_id,
                    "hostname": hostname,
                    "gpu": gpu,
                    "tokens_per_second": tokens_per_second,
                    "current_job_id": current_job_id,
                },
            )
        except httpx.HTTPError as e:
            # Heartbeats are nice-to-have; never block the worker because
            # of a transient backend hiccup.
            log.warning("heartbeat failed: %s", e)
