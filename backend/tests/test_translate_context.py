from __future__ import annotations

import pytest
from sqlmodel import select

from app.adapters.base import TranslationRequest, TranslationResult
from app.models import Chunk, Document, Job, JobStatus
from app.services.translate import translate_job


class RecordingAdapter:
    name = "rec"

    def __init__(self):
        self.calls: list[TranslationRequest] = []

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        self.calls.append(req)
        return TranslationResult(text=f"ES:{req.text}", model_name="rec")

    async def health(self) -> bool:
        return True


class CancelingAdapter:
    name = "cancel"

    def __init__(self, session_factory, job_id: int, after: int):
        self.calls = 0
        self._factory = session_factory
        self._job_id = job_id
        self._after = after

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        self.calls += 1
        if self.calls == self._after:
            with self._factory() as s:
                job = s.get(Job, self._job_id)
                if job is not None:
                    job.status = JobStatus.FAILED
                    job.error = "canceled by user"
                    s.add(job)
                    s.commit()
        return TranslationResult(text=f"ES:{req.text}", model_name="cancel")

    async def health(self) -> bool:
        return True


def _seed(session_factory, *, chunks: list[str]) -> int:
    with session_factory() as s:
        doc = Document(
            filename="a.txt",
            mime_type="text/plain",
            size_bytes=100,
            page_count=1,
            word_count=10,
            token_count=20,
            stored_path="/tmp/a.txt",
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)

        job = Job(
            document_id=doc.id,
            status=JobStatus.AWAITING_GLOSSARY_REVIEW,
            source_lang="en",
            target_lang="es-AR",
            model_adapter="rec",
            model_name="rec",
            chunk_count=len(chunks),
        )
        s.add(job)
        s.commit()
        s.refresh(job)

        for i, text in enumerate(chunks):
            s.add(Chunk(job_id=job.id, idx=i, source_text=text, token_count=len(text)))
        s.commit()
        return job.id


@pytest.mark.asyncio
async def test_first_chunk_has_no_context(session_factory):
    job_id = _seed(session_factory, chunks=["A.", "B.", "C."])
    adapter = RecordingAdapter()
    await translate_job(job_id, adapter, session_factory, context_chars=50)

    assert adapter.calls[0].context is None


@pytest.mark.asyncio
async def test_subsequent_chunks_receive_prev_translated_tail(session_factory):
    job_id = _seed(session_factory, chunks=["Alpha.", "Beta.", "Gamma."])
    adapter = RecordingAdapter()
    await translate_job(job_id, adapter, session_factory, context_chars=100)

    # chunk 1 should have context equal to the full translated text of chunk 0,
    # which is "ES:Alpha." (shorter than 100 chars).
    assert adapter.calls[1].context == "ES:Alpha."
    # chunk 2 should have context from chunk 1, "ES:Beta.".
    assert adapter.calls[2].context == "ES:Beta."


@pytest.mark.asyncio
async def test_context_respects_char_cap(session_factory):
    long_tail = "x" * 500
    # Use an adapter that returns a long translation so we can verify trimming.
    class LongAdapter:
        name = "long"

        def __init__(self):
            self.calls: list[TranslationRequest] = []

        async def translate(self, req: TranslationRequest) -> TranslationResult:
            self.calls.append(req)
            return TranslationResult(text=long_tail, model_name="long")

        async def health(self) -> bool:
            return True

    job_id = _seed(session_factory, chunks=["one", "two"])
    adapter = LongAdapter()
    await translate_job(job_id, adapter, session_factory, context_chars=50)
    assert adapter.calls[1].context == long_tail[-50:]
    assert len(adapter.calls[1].context) == 50


@pytest.mark.asyncio
async def test_cancel_stops_translation(session_factory):
    job_id = _seed(session_factory, chunks=["a", "b", "c", "d", "e"])
    adapter = CancelingAdapter(session_factory, job_id, after=2)

    await translate_job(job_id, adapter, session_factory, context_chars=0)

    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert "canceled" in (job.error or "").lower()
        chunks = s.exec(
            select(Chunk).where(Chunk.job_id == job_id).order_by(Chunk.idx)
        ).all()
        translated = [c.translated_text for c in chunks]
        # First 2 chunks got translated (adapter ran for them); after the 2nd
        # call the adapter flipped the job to FAILED, so the loop sees the
        # status change before processing chunk 3 and bails.
        assert translated[0] is not None
        assert translated[1] is not None
        assert translated[3] is None
        assert translated[4] is None
