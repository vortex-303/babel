from __future__ import annotations

from app.services.analyzer import chunk_document, count_tokens, estimate
from app.services.ingest import Chapter, Ingested


def _ingested(paragraphs: list[str]) -> Ingested:
    return Ingested(chapters=[Chapter(title="t", paragraphs=paragraphs)], page_count=1)


def test_chunking_no_overlap_splits_at_limit():
    paras = [f"Paragraph number {i} with some words." for i in range(40)]
    chunks = chunk_document(_ingested(paras), chunk_tokens=50, overlap_tokens=0)
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 50 + count_tokens(paras[0])
    total = sum(len(c.text.split("\n\n")) for c in chunks)
    assert total == len(paras)


def test_chunking_with_overlap_repeats_tail_paragraphs():
    paras = [f"Paragraph {i} carrying a handful of tokens here." for i in range(30)]
    chunks = chunk_document(_ingested(paras), chunk_tokens=60, overlap_tokens=25)
    assert len(chunks) >= 2
    prev_paras = chunks[0].text.split("\n\n")
    next_paras = chunks[1].text.split("\n\n")
    assert prev_paras[-1] in next_paras, "chunk 0's last paragraph should overlap into chunk 1"


def test_chunking_no_overlap_has_no_shared_paragraphs():
    paras = [f"Paragraph {i} carrying a handful of tokens here." for i in range(30)]
    chunks = chunk_document(_ingested(paras), chunk_tokens=60, overlap_tokens=0)
    assert len(chunks) >= 2
    seen: set[str] = set()
    for c in chunks:
        for p in c.text.split("\n\n"):
            assert p not in seen
            seen.add(p)


def test_chunking_respects_overlap_budget():
    paras = [f"Sentence {i} here with content." for i in range(50)]
    chunk_tok = 40
    overlap = 15
    chunks = chunk_document(_ingested(paras), chunk_tokens=chunk_tok, overlap_tokens=overlap)
    for c in chunks[1:]:
        first_para = c.text.split("\n\n")[0]
        assert count_tokens(first_para) <= chunk_tok


def test_estimate_cost_zero_for_local_adapter():
    paras = ["Hello world."]
    chunks = chunk_document(_ingested(paras), chunk_tokens=100, overlap_tokens=0)
    est = estimate(chunks, word_count=2, adapter="llamacpp")
    assert est.estimated_cost_usd == 0.0
    assert est.chunk_count == 1
    assert est.total_tokens > 0


def test_estimate_cost_nonzero_for_cloud_adapter():
    paras = ["Hello world this is a slightly longer sentence to count tokens."] * 20
    chunks = chunk_document(_ingested(paras), chunk_tokens=100, overlap_tokens=0)
    est = estimate(chunks, word_count=200, adapter="gemini")
    assert est.estimated_cost_usd > 0
    assert est.adapter_label.lower().startswith("gemini")
