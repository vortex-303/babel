from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TranslationRequest:
    text: str
    source_lang: str
    target_lang: str
    context: str | None = None


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
