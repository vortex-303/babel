from __future__ import annotations

import pytest
from sqlmodel import select

from app.adapters.base import TranslationRequest, TranslationResult
from app.models import Chunk, Document, Job, JobStatus
from app.services.translate import translate_job


class FakeAdapter:
    name = "fake"

    def __init__(self, transformer=None, raise_on_idx: int | None = None):
        self._transformer = transformer or (lambda t: f"[ES] {t}")
        self._raise_on_idx = raise_on_idx
        self.calls: list[TranslationRequest] = []

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        self.calls.append(req)
        if self._raise_on_idx is not None and len(self.calls) - 1 == self._raise_on_idx:
            raise RuntimeError("boom")
        return TranslationResult(text=self._transformer(req.text), model_name="fake")

    async def health(self) -> bool:
        return True


def _seed(session_factory, *, chunks: list[str]) -> int:
    with session_factory() as s:
        doc = Document(
            filename="book.txt",
            mime_type="text/plain",
            size_bytes=100,
            page_count=1,
            word_count=42,
            token_count=100,
            stored_path="/tmp/book.txt",
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)

        job = Job(
            document_id=doc.id,
            status=JobStatus.AWAITING_GLOSSARY_REVIEW,
            source_lang="en",
            target_lang="es",
            model_adapter="fake",
            model_name="fake",
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
async def test_translate_job_marks_chunks_and_done(session_factory):
    job_id = _seed(session_factory, chunks=["Hello.", "World.", "Goodbye."])

    adapter = FakeAdapter()
    await translate_job(job_id, adapter, session_factory)

    assert [r.text for r in adapter.calls] == ["Hello.", "World.", "Goodbye."]
    assert all(r.source_lang == "en" and r.target_lang == "es" for r in adapter.calls)

    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.DONE
        assert job.translated_chunks == 3
        assert job.error is None
        assert job.started_at is not None
        assert job.finished_at is not None

        chunks = s.exec(
            select(Chunk).where(Chunk.job_id == job_id).order_by(Chunk.idx)
        ).all()
        assert [c.translated_text for c in chunks] == [
            "[ES] Hello.",
            "[ES] World.",
            "[ES] Goodbye.",
        ]
        assert all(c.translated_at is not None for c in chunks)


@pytest.mark.asyncio
async def test_translate_job_marks_failed_on_adapter_error(session_factory):
    job_id = _seed(session_factory, chunks=["a", "b", "c"])

    adapter = FakeAdapter(raise_on_idx=1)
    await translate_job(job_id, adapter, session_factory)

    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.FAILED
        assert job.error and "boom" in job.error
        assert job.translated_chunks == 1

        chunks = s.exec(
            select(Chunk).where(Chunk.job_id == job_id).order_by(Chunk.idx)
        ).all()
        assert chunks[0].translated_text == "[ES] a"
        assert chunks[1].translated_text is None
        assert chunks[2].translated_text is None


@pytest.mark.asyncio
async def test_translate_job_no_op_for_missing_job(session_factory):
    adapter = FakeAdapter()
    await translate_job(9999, adapter, session_factory)
    assert adapter.calls == []
