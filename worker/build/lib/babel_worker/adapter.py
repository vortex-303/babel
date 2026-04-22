"""TranslateGemma-aware llama.cpp client — a copy of backend/app/adapters/llamacpp.py.

Kept deliberately self-contained so the worker has zero filesystem coupling
to the backend package. When the backend adapter changes, mirror the prompt
builder here; the PR reviewer (you) should flag any drift."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_LANG_NAMES: dict[str, str] = {
    "ar": "Arabic", "bn": "Bengali", "bg": "Bulgarian", "ca": "Catalan",
    "zh": "Chinese", "zh-Hant": "Chinese", "hr": "Croatian", "cs": "Czech",
    "da": "Danish", "nl": "Dutch", "en": "English", "fi": "Finnish",
    "fr": "French", "de": "German", "el": "Greek", "he": "Hebrew",
    "hi": "Hindi", "hu": "Hungarian", "id": "Indonesian", "it": "Italian",
    "ja": "Japanese", "ko": "Korean", "ms": "Malay", "no": "Norwegian",
    "fa": "Persian", "pl": "Polish", "pt": "Portuguese", "pt-BR": "Portuguese",
    "pt-PT": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
    "es": "Spanish", "es-AR": "Spanish", "es-MX": "Spanish", "es-ES": "Spanish",
    "es-US": "Spanish", "sv": "Swedish", "ta": "Tamil", "th": "Thai",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
    "cy": "Welsh",
}

_LANG_ALIASES: dict[str, str] = {"es-419": "es", "zh-Hans": "zh"}

_VARIANT_HINTS: dict[str, str] = {
    "es-AR": (
        " specializing in rioplatense Spanish (Argentina/Uruguay): voseo "
        "(vos/tenés/sos), LATAM vocabulary (auto, celular, computadora), "
        "Argentine idioms where natural"
    ),
    "es-MX": (
        " specializing in Mexican Spanish: tuteo, Mexican vocabulary "
        "(carro, celular, padre/chido)"
    ),
    "es-ES": (
        " specializing in Peninsular Spanish (Spain): tuteo plus vosotros, "
        "Iberian vocabulary (coche, móvil, ordenador)"
    ),
    "es-US": (
        " specializing in US Spanish: accessible to bilingual readers, "
        "avoid hyper-regional slang"
    ),
    "pt-BR": " specializing in Brazilian Portuguese",
    "pt-PT": " specializing in European Portuguese",
}


def _normalize_code(code: str) -> str:
    return _LANG_ALIASES.get(code, code)


def _language_name(code: str) -> str:
    if code in _LANG_NAMES:
        return _LANG_NAMES[code]
    base = code.split("-")[0]
    return _LANG_NAMES.get(base, code)


def build_prompt(
    source: str,
    target: str,
    text: str,
    *,
    glossary: list[tuple[str, str]] | None = None,
) -> str:
    src_code = _normalize_code(source)
    tgt_code = _normalize_code(target)
    src_name = _language_name(src_code)
    tgt_name = _language_name(tgt_code)
    variant_hint = _VARIANT_HINTS.get(tgt_code, "")

    glossary_clause = ""
    if glossary:
        lines = "\n".join(f"- {src} → {tgt}" for src, tgt in glossary)
        glossary_clause = (
            f"\nUse exactly these translations for the following terms, "
            f"keeping them consistent and never altering spelling or case:\n"
            f"{lines}\n"
        )

    return (
        "<start_of_turn>user\n"
        f"You are a professional {src_name} ({src_code}) to {tgt_name} "
        f"({tgt_code}) translator{variant_hint}. Your goal is to accurately "
        f"convey the meaning and nuances of the original {src_name} text "
        f"while adhering to {tgt_name} grammar, vocabulary, and cultural "
        "sensitivities.\n"
        f"{glossary_clause}"
        f"Produce only the {tgt_name} translation, without any additional "
        f"explanations or commentary. Please translate the following "
        f"{src_name} text into {tgt_name}:\n\n\n"
        f"{text.strip()}"
        "<end_of_turn>\n"
        "<start_of_turn>model\n"
    )


@dataclass
class TranslationResult:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class LlamaCppClient:
    """Minimal POST /completion client against a local llama-server."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 600.0,
        temperature: float = 0.1,
        n_predict: int = 3072,
    ):
        self._base = f"http://{host}:{port}"
        self._timeout = timeout_seconds
        self._temperature = temperature
        self._n_predict = n_predict

    def health(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self._base}/health")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    def translate(
        self,
        *,
        source_lang: str,
        target_lang: str,
        text: str,
        context: str | None = None,
        glossary: list[tuple[str, str]] | None = None,
    ) -> TranslationResult:
        # `context` is the previous translated chunk tail. We currently don't
        # include it in the TranslateGemma prompt (strict template) but keep
        # the argument so the loop's signature can evolve without breaking.
        _ = context  # noqa: F841 — explicit unused
        prompt = build_prompt(source_lang, target_lang, text, glossary=glossary)
        payload = {
            "prompt": prompt,
            "temperature": self._temperature,
            "n_predict": self._n_predict,
            "cache_prompt": True,
            "stream": False,
            "stop": ["<end_of_turn>", "<start_of_turn>", "<eos>"],
        }
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(f"{self._base}/completion", json=payload)
            r.raise_for_status()
            data = r.json()
        content = (data.get("content") or "").strip()
        if not content:
            raise RuntimeError(f"llama-server returned empty completion: {data}")
        return TranslationResult(
            text=content,
            tokens_in=data.get("tokens_evaluated"),
            tokens_out=data.get("tokens_predicted"),
        )
