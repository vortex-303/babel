"""Main worker loop — poll, translate, push."""

from __future__ import annotations

import logging
import signal
import socket
import threading
import time

import httpx

from babel_worker.adapter import LlamaCppClient
from babel_worker.client import BackendClient, ClaimedJob
from babel_worker.config import Config

log = logging.getLogger("babel_worker.loop")

_stop = threading.Event()


def _install_signals() -> None:
    def handler(signum, _frame):
        log.info("received signal %s — shutting down after current chunk", signum)
        _stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def _filter_glossary(
    glossary: list[tuple[str, str]], chunk_text: str
) -> list[tuple[str, str]] | None:
    matches = [(s, t) for s, t in glossary if s in chunk_text]
    return matches or None


def _run_job(
    job: ClaimedJob, backend: BackendClient, llama: LlamaCppClient, cfg: Config
) -> None:
    log.info(
        "job %s: %d chunks, %s → %s (%s)",
        job.job_id,
        len(job.chunks),
        job.source_lang,
        job.target_lang,
        job.document_filename or "?",
    )

    prev_translated: str | None = None
    start = time.time()
    for chunk in job.chunks:
        if _stop.is_set():
            backend.mark_failed(job.job_id, "worker stopped mid-job (graceful shutdown)")
            return

        context = (
            prev_translated[-cfg.__dict__.get("context_chars", job.context_chars) :]
            if prev_translated and job.context_chars > 0
            else None
        )
        gloss = _filter_glossary(job.glossary, chunk.source_text)

        t0 = time.time()
        try:
            result = llama.translate(
                source_lang=job.source_lang,
                target_lang=job.target_lang,
                text=chunk.source_text,
                context=context,
                glossary=gloss,
            )
        except Exception as e:
            log.exception("chunk %s.%s translate failed", job.job_id, chunk.idx)
            backend.mark_failed(
                job.job_id, f"chunk {chunk.idx}: {type(e).__name__}: {e}"
            )
            return

        try:
            backend.upload_chunk(job.job_id, chunk.idx, result.text)
        except httpx.HTTPError as e:
            log.exception("upload chunk %s.%s failed", job.job_id, chunk.idx)
            backend.mark_failed(
                job.job_id, f"upload chunk {chunk.idx}: {type(e).__name__}: {e}"
            )
            return

        prev_translated = result.text
        dt = time.time() - t0
        log.info(
            "  chunk %d/%d ok (%.1fs, out=%s tok)",
            chunk.idx + 1,
            len(job.chunks),
            dt,
            result.tokens_out,
        )

        # Heartbeat mid-job so admin sees activity.
        backend.heartbeat(
            worker_id=cfg.worker_id,
            hostname=socket.gethostname(),
            current_job_id=job.job_id,
            tokens_per_second=(
                (result.tokens_out / dt) if (result.tokens_out and dt > 0) else None
            ),
        )

    backend.mark_done(job.job_id)
    log.info("job %s DONE in %.1fs", job.job_id, time.time() - start)


def run(cfg: Config) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _install_signals()

    llama = LlamaCppClient(cfg.llama_host, cfg.llama_port)
    if not llama.health():
        log.error(
            "llama-server not reachable at http://%s:%s — start it first",
            cfg.llama_host,
            cfg.llama_port,
        )

    backend = BackendClient(cfg.backend_url, cfg.worker_token)
    log.info(
        "worker %s polling %s every %ss",
        cfg.worker_id,
        cfg.backend_url,
        cfg.poll_interval_seconds,
    )

    last_heartbeat = 0.0
    try:
        while not _stop.is_set():
            # Heartbeat even when idle.
            if time.time() - last_heartbeat > cfg.heartbeat_interval_seconds:
                backend.heartbeat(
                    worker_id=cfg.worker_id, hostname=socket.gethostname()
                )
                last_heartbeat = time.time()

            try:
                job = backend.claim_next()
            except httpx.HTTPError as e:
                log.warning("claim-next failed: %s — retrying", e)
                _stop.wait(cfg.poll_interval_seconds)
                continue

            if job is None:
                _stop.wait(cfg.poll_interval_seconds)
                continue

            _run_job(job, backend, llama, cfg)
            last_heartbeat = 0.0  # force a fresh heartbeat after job
    finally:
        backend.close()
        log.info("worker stopped")
