from __future__ import annotations

from app.adapters.base import TranslationAdapter, TranslationRequest, TranslationResult
from app.adapters.llamacpp import LlamaCppAdapter
from app.config import settings

IMPLEMENTED_ADAPTERS: frozenset[str] = frozenset({"llamacpp"})


def get_adapter(name: str) -> TranslationAdapter:
    if name == "llamacpp":
        return LlamaCppAdapter(
            host=settings.llamacpp_host,
            port=settings.llamacpp_port,
            model_name=settings.llamacpp_model,
        )
    raise NotImplementedError(
        f"adapter {name!r} not yet implemented; available: {sorted(IMPLEMENTED_ADAPTERS)}"
    )


__all__ = [
    "IMPLEMENTED_ADAPTERS",
    "TranslationAdapter",
    "TranslationRequest",
    "TranslationResult",
    "get_adapter",
]
