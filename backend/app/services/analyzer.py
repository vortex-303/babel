from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from app.services.ingest import Ingested

_ENC = tiktoken.get_encoding("cl100k_base")


ADAPTER_PROFILES: dict[str, dict] = {
    "llamacpp": {
        "label": "llama.cpp / TranslateGemma",
        "tokens_per_second": 35.0,
        "cost_per_1k_tokens": 0.0,
    },
    "ollama": {
        "label": "Ollama local",
        "tokens_per_second": 25.0,
        "cost_per_1k_tokens": 0.0,
    },
    "gemini": {
        "label": "Gemini 2.5 Pro",
        "tokens_per_second": 120.0,
        "cost_per_1k_tokens": 0.00125,
    },
    "claude": {
        "label": "Claude Sonnet 4.6",
        "tokens_per_second": 80.0,
        "cost_per_1k_tokens": 0.003,
    },
}


@dataclass
class Chunk:
    idx: int
    text: str
    token_count: int


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text, disallowed_special=()))


def chunk_document(
    ingested: Ingested,
    chunk_tokens: int,
    overlap_tokens: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf: list[tuple[str, int]] = []
    buf_tokens = 0
    idx = 0
    for chapter in ingested.chapters:
        for para in chapter.paragraphs:
            ptoks = count_tokens(para)
            if buf and buf_tokens + ptoks > chunk_tokens:
                text = "\n\n".join(p for p, _ in buf)
                chunks.append(Chunk(idx=idx, text=text, token_count=buf_tokens))
                idx += 1
                if overlap_tokens > 0:
                    tail: list[tuple[str, int]] = []
                    tail_tokens = 0
                    for entry in reversed(buf):
                        _, t = entry
                        if tail and tail_tokens + t > overlap_tokens:
                            break
                        tail.insert(0, entry)
                        tail_tokens += t
                    buf = tail
                    buf_tokens = tail_tokens
                else:
                    buf = []
                    buf_tokens = 0
            buf.append((para, ptoks))
            buf_tokens += ptoks
    if buf:
        text = "\n\n".join(p for p, _ in buf)
        chunks.append(Chunk(idx=idx, text=text, token_count=buf_tokens))
    return chunks


@dataclass
class Estimate:
    chunk_count: int
    total_tokens: int
    word_count: int
    estimated_seconds: int
    estimated_cost_usd: float
    tokens_per_second: float
    adapter_label: str


def estimate(
    chunks: list[Chunk],
    word_count: int,
    adapter: str,
) -> Estimate:
    profile = ADAPTER_PROFILES.get(adapter, ADAPTER_PROFILES["llamacpp"])
    total_tokens = sum(c.token_count for c in chunks)
    tps = max(profile["tokens_per_second"], 1.0)
    out_multiplier = 1.15
    seconds = int((total_tokens * out_multiplier) / tps)
    cost = round((total_tokens / 1000.0) * float(profile["cost_per_1k_tokens"]), 4)
    return Estimate(
        chunk_count=len(chunks),
        total_tokens=total_tokens,
        word_count=word_count,
        estimated_seconds=seconds,
        estimated_cost_usd=cost,
        tokens_per_second=tps,
        adapter_label=profile["label"],
    )
