"""HTTP client for the babel backend's /api/worker/* endpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger("babel_worker.client")


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


class BackendClient:
    def __init__(self, backend_url: str, worker_token: str, timeout: float = 60.0):
        self._base = backend_url.rstrip("/") + "/api"
        self._headers = {"Authorization": f"Bearer {worker_token}"}
        self._client = httpx.Client(timeout=timeout, headers=self._headers)

    def close(self) -> None:
        self._client.close()

    def claim_next(self) -> ClaimedJob | None:
        r = self._client.post(f"{self._base}/worker/claim-next")
        r.raise_for_status()
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
        r = self._client.post(
            f"{self._base}/worker/jobs/{job_id}/chunks/{idx}",
            json={"translated_text": translated_text},
        )
        r.raise_for_status()
        return r.json()

    def mark_done(self, job_id: int) -> None:
        r = self._client.post(f"{self._base}/worker/jobs/{job_id}/done")
        r.raise_for_status()

    def mark_failed(self, job_id: int, error: str) -> None:
        r = self._client.post(
            f"{self._base}/worker/jobs/{job_id}/fail",
            json={"error": error},
        )
        r.raise_for_status()

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
            self._client.post(
                f"{self._base}/worker/heartbeat",
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
