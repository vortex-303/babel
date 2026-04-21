from __future__ import annotations

import pytest
from sqlmodel import select

from app.adapters.base import TranslationRequest, TranslationResult
from app.adapters.llamacpp import build_prompt
from app.models import Chunk, Document, GlossaryTerm, Job, JobStatus
from app.services.translate import translate_job


def test_build_prompt_includes_glossary_when_supplied():
    p = build_prompt(
        "en",
        "es",
        "Alice fell down the rabbit hole.",
        glossary=[("Alice", "Alicia"), ("Wonderland", "País de las Maravillas")],
    )
    assert "Use exactly these translations" in p
    assert "- Alice → Alicia" in p
    assert "- Wonderland → País de las Maravillas" in p
    # Source text still present.
    assert "Alice fell down the rabbit hole." in p


def test_build_prompt_omits_glossary_clause_when_empty():
    p = build_prompt("en", "es", "x", glossary=[])
    assert "Use exactly these translations" not in p

    p2 = build_prompt("en", "es", "x", glossary=None)
    assert "Use exactly these translations" not in p2


class _Recorder:
    name = "rec"

    def __init__(self):
        self.calls: list[TranslationRequest] = []

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        self.calls.append(req)
        return TranslationResult(text=f"ES:{req.text}", model_name="rec")

    async def health(self) -> bool:
        return True


def _seed(session_factory, *, chunks, glossary):
    with session_factory() as s:
        doc = Document(
            filename="alice.txt",
            mime_type="text/plain",
            size_bytes=100,
            page_count=1,
            word_count=50,
            token_count=80,
            stored_path="/tmp/alice.txt",
        )
        s.add(doc)
        s.commit()
        s.refresh(doc)

        job = Job(
            document_id=doc.id,
            status=JobStatus.AWAITING_GLOSSARY_REVIEW,
            source_lang="en",
            target_lang="es",
            model_adapter="rec",
            model_name="rec",
            chunk_count=len(chunks),
        )
        s.add(job)
        s.commit()
        s.refresh(job)

        for i, text in enumerate(chunks):
            s.add(Chunk(job_id=job.id, idx=i, source_text=text, token_count=len(text)))

        for src, tgt in glossary:
            s.add(
                GlossaryTerm(
                    job_id=job.id,
                    source_term=src,
                    target_term=tgt,
                    occurrences=1,
                    locked=True,
                )
            )

        s.commit()
        return job.id


@pytest.mark.asyncio
async def test_orchestrator_passes_glossary_to_adapter(session_factory):
    job_id = _seed(
        session_factory,
        chunks=["Alice met the Cheshire Cat.", "Plain sentence."],
        glossary=[("Alice", "Alicia"), ("Cheshire Cat", "Gato de Cheshire")],
    )

    adapter = _Recorder()
    await translate_job(job_id, adapter, session_factory, context_chars=0)

    # Chunk 0 mentions both terms → both should be passed.
    chunk0_glossary = adapter.calls[0].glossary or []
    by_src = {src: tgt for src, tgt in chunk0_glossary}
    assert by_src.get("Alice") == "Alicia"
    assert by_src.get("Cheshire Cat") == "Gato de Cheshire"

    # Chunk 1 has neither term → glossary should be None (skipped).
    assert adapter.calls[1].glossary is None


@pytest.mark.asyncio
async def test_orchestrator_skips_glossary_entries_without_target(session_factory):
    job_id = _seed(
        session_factory,
        chunks=["Alice walked."],
        glossary=[],  # no terms
    )

    # Add an entry with a NULL target manually — this should be filtered out.
    with session_factory() as s:
        s.add(
            GlossaryTerm(
                job_id=job_id,
                source_term="Alice",
                target_term=None,
                occurrences=1,
                locked=True,
            )
        )
        s.commit()

    adapter = _Recorder()
    await translate_job(job_id, adapter, session_factory, context_chars=0)

    # Even though Alice appears in the chunk, the glossary entry has no
    # target → the orchestrator filters it out → adapter sees no glossary.
    assert adapter.calls[0].glossary is None


@pytest.mark.asyncio
async def test_orchestrator_no_glossary_when_table_empty(session_factory):
    job_id = _seed(
        session_factory,
        chunks=["Alice walked into the garden."],
        glossary=[],
    )

    adapter = _Recorder()
    await translate_job(job_id, adapter, session_factory, context_chars=0)

    assert adapter.calls[0].glossary is None
