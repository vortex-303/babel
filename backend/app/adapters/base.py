from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TranslationRequest:
    text: str
    source_lang: str
    target_lang: str
    context: str | None = None
    # Optional term glossary: [(source_term, target_term), ...] the model
    # must preserve exactly. Filtered per-chunk by the orchestrator so we
    # don't bloat prompts with entries that never appear.
    glossary: list[tuple[str, str]] | None = None


@dataclass
class TranslationResult:
    text: str
    model_name: str
    tokens_in: int | None = None
    tokens_out: int | None = None


@runtime_checkable
class TranslationAdapter(Protocol):
    name: str

    async def translate(self, req: TranslationRequest) -> TranslationResult: ...

    async def health(self) -> bool: ...
