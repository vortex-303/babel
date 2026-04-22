"""Main worker loop — poll, translate, push. Reports state through a
shared Controller so the tray UI can display + pause/resume."""

from __future__ import annotations

import logging
import signal
import socket
import threading
import time

import httpx

from babel_worker.adapter import LlamaCppClient
from babel_worker.client import BackendClient, ClaimedJob, SupabaseAuth
from babel_worker.config import Config
from babel_worker.state import Controller

log = logging.getLogger("babel_worker.loop")


def _install_signals(controller: Controller) -> None:
    # signal.signal() is main-thread-only on Python. When the loop runs
    # under tray mode, pystray owns the main thread — we skip signal
    # registration and rely on controller.stop() being called from the
    # tray's Quit menu (or from launchd on machine shutdown).
    if threading.current_thread() is not threading.main_thread():
        log.debug("signal handler skipped — running in background thread")
        return

    def handler(signum, _frame):
        log.info("signal %s — graceful shutdown after current chunk", signum)
        controller.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def _filter_glossary(
    glossary: list[tuple[str, str]], chunk_text: str
) -> list[tuple[str, str]] | None:
    matches = [(s, t) for s, t in glossary if s in chunk_text]
    return matches or None


def _run_job(
    job: ClaimedJob,
    backend: BackendClient,
    llama: LlamaCppClient,
    cfg: Config,
    controller: Controller,
) -> None:
    log.info(
        "job %s: %d chunks, %s → %s (%s)",
        job.job_id,
        len(job.chunks),
        job.source_lang,
        job.target_lang,
        job.document_filename or "?",
    )
    controller.update(
        phase="translating",
        current_job_id=job.job_id,
        document_filename=job.document_filename,
        chunks_done=0,
        chunks_total=len(job.chunks),
        tokens_per_second=None,
        last_error=None,
    )
    controller.log_event(
        f"Started job #{job.job_id} ({len(job.chunks)} chunks, "
        f"{job.source_lang}→{job.target_lang})"
    )

    prev_translated: str | None = None
    start = time.time()
    for chunk in job.chunks:
        if controller.stopped:
            backend.mark_failed(
                job.job_id, "worker stopped mid-job (graceful shutdown)"
            )
            return

        context = (
            prev_translated[-job.context_chars :]
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
            err = f"chunk {chunk.idx}: {type(e).__name__}: {e}"
            log.exception("chunk %s.%s translate failed", job.job_id, chunk.idx)
            backend.mark_failed(job.job_id, err)
            controller.update(phase="error", last_error=err)
            return

        try:
            backend.upload_chunk(job.job_id, chunk.idx, result.text)
        except httpx.HTTPError as e:
            err = f"upload chunk {chunk.idx}: {type(e).__name__}: {e}"
            log.exception("upload chunk %s.%s failed", job.job_id, chunk.idx)
            backend.mark_failed(job.job_id, err)
            controller.update(phase="error", last_error=err)
            return

        prev_translated = result.text
        dt = time.time() - t0
        tps = (result.tokens_out / dt) if (result.tokens_out and dt > 0) else None
        log.info(
            "  chunk %d/%d ok (%.1fs, out=%s tok)",
            chunk.idx + 1,
            len(job.chunks),
            dt,
            result.tokens_out,
        )
        controller.update(
            chunks_done=chunk.idx + 1,
            tokens_per_second=tps,
        )

        backend.heartbeat(
            worker_id=cfg.worker_id,
            hostname=socket.gethostname(),
            current_job_id=job.job_id,
            tokens_per_second=tps,
        )

    backend.mark_done(job.job_id)
    elapsed = time.time() - start
    log.info("job %s DONE in %.1fs", job.job_id, elapsed)
    controller.log_event(f"Finished job #{job.job_id} in {elapsed:.0f}s")
    controller.update(
        phase="idle",
        current_job_id=None,
        document_filename=None,
        chunks_done=0,
        chunks_total=0,
    )


def run(cfg: Config, controller: Controller | None = None) -> None:
    # Configure logging only if nobody else has. Otherwise we'd duplicate
    # messages when the tray launches the loop from a background thread.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    if controller is None:
        controller = Controller(auto_claim=cfg.auto_claim)
    _install_signals(controller)
    # Wrap the real loop in a try/except so unhandled errors surface in the
    # tray as an "error" phase instead of a silent thread death.
    try:
        _run_inner(cfg, controller)
    except Exception as e:
        log.exception("worker loop crashed")
        controller.update(phase="error", last_error=f"{type(e).__name__}: {e}")
        raise


def _run_inner(cfg: Config, controller: Controller) -> None:

    llama = LlamaCppClient(cfg.llama_host, cfg.llama_port)
    if not llama.health():
        log.error(
            "llama-server not reachable at http://%s:%s — start it first",
            cfg.llama_host,
            cfg.llama_port,
        )
        controller.update(
            phase="error",
            last_error=f"llama-server unreachable at {cfg.llama_host}:{cfg.llama_port}",
        )

    if cfg.uses_supabase_auth:
        sb_auth = SupabaseAuth(
            cfg.supabase_url,
            cfg.supabase_anon_key,
            cfg.user_email,
            cfg.user_password,
        )
        # Log in eagerly so a bad password surfaces up-front, not 5s later.
        sb_auth.bearer()
        backend = BackendClient(cfg.backend_url, supabase=sb_auth)
        log.info("worker signed in as %s (self-host license)", cfg.user_email)
    else:
        backend = BackendClient(cfg.backend_url, worker_token=cfg.worker_token)
        log.info("worker authed with shared admin token")
    log.info(
        "worker %s polling %s every %ss",
        cfg.worker_id,
        cfg.backend_url,
        cfg.poll_interval_seconds,
    )
    controller.update(phase="idle")

    last_heartbeat = 0.0
    try:
        while not controller.stopped:
            if controller.paused:
                time.sleep(0.5)
                if time.time() - last_heartbeat > cfg.heartbeat_interval_seconds:
                    backend.heartbeat(
                        worker_id=cfg.worker_id, hostname=socket.gethostname()
                    )
                    last_heartbeat = time.time()
                continue

            if time.time() - last_heartbeat > cfg.heartbeat_interval_seconds:
                backend.heartbeat(
                    worker_id=cfg.worker_id, hostname=socket.gethostname()
                )
                last_heartbeat = time.time()

            try:
                if controller.auto_claim:
                    job = backend.claim_next()
                else:
                    # Manual mode: refresh queue display, then see if the
                    # operator has clicked a specific job to claim.
                    try:
                        controller.set_queue(backend.list_queue())
                    except httpx.HTTPError as e:
                        log.warning("list-queue failed: %s", e)
                    requested = controller.take_pending_claim()
                    job = backend.claim(requested) if requested else None
                    if requested and job is None:
                        controller.log_event(
                            f"Could not claim job #{requested} — already gone?"
                        )
            except httpx.HTTPError as e:
                log.warning("claim failed: %s — retrying", e)
                controller.update(phase="error", last_error=str(e))
                time.sleep(cfg.poll_interval_seconds)
                continue

            if job is None:
                if controller.state.phase != "idle":
                    controller.update(phase="idle", last_error=None)
                time.sleep(cfg.poll_interval_seconds)
                continue

            _run_job(job, backend, llama, cfg, controller)
            last_heartbeat = 0.0
    finally:
        backend.close()
        log.info("worker stopped")
        controller.update(phase="stopping")
