from __future__ import annotations

import httpx

from app.adapters.base import TranslationAdapter, TranslationRequest, TranslationResult

# Human-readable names for codes we display to the model. Covers everything
# our frontend selector can produce. Unknown codes fall back to the base
# (everything before the first `-`), then to the code itself.
_LANG_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "bn": "Bengali",
    "bg": "Bulgarian",
    "ca": "Catalan",
    "zh": "Chinese",
    "zh-Hant": "Chinese",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "no": "Norwegian",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese",
    "pt-BR": "Portuguese",
    "pt-PT": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "es": "Spanish",
    "es-AR": "Spanish",
    "es-MX": "Spanish",
    "es-ES": "Spanish",
    "es-US": "Spanish",
    "sv": "Swedish",
    "ta": "Tamil",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "cy": "Welsh",
}

# TranslateGemma's baked-in `languages` dict supports BCP-47-ish country codes
# (es-AR, pt-BR, etc.) but NOT macro-regional codes like es-419 or zh-Hans.
# We map unsupported codes to the closest supported base so the model's
# prompt instructions stay sensible.
_LANG_ALIASES: dict[str, str] = {
    "es-419": "es",
    "zh-Hans": "zh",
}

# Variant-style hints injected into the translator role sentence so the model
# produces regional vocabulary. The lang code itself is also in the prompt,
# so these reinforce rather than replace the code signal.
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


def build_prompt(source: str, target: str, text: str) -> str:
    """Render a TranslateGemma-compatible prompt for the /completion endpoint.

    Matches the model's embedded Jinja chat template byte-for-byte (minus the
    leading bos_token, which llama-server injects via the tokenizer)."""
    src_code = _normalize_code(source)
    tgt_code = _normalize_code(target)
    src_name = _language_name(src_code)
    tgt_name = _language_name(tgt_code)
    variant_hint = _VARIANT_HINTS.get(tgt_code, "")

    return (
        "<start_of_turn>user\n"
        f"You are a professional {src_name} ({src_code}) to {tgt_name} "
        f"({tgt_code}) translator{variant_hint}. Your goal is to accurately "
        f"convey the meaning and nuances of the original {src_name} text "
        f"while adhering to {tgt_name} grammar, vocabulary, and cultural "
        "sensitivities.\n"
        f"Produce only the {tgt_name} translation, without any additional "
        f"explanations or commentary. Please translate the following "
        f"{src_name} text into {tgt_name}:\n\n\n"
        f"{text.strip()}"
        "<end_of_turn>\n"
        "<start_of_turn>model\n"
    )


class LlamaCppAdapter(TranslationAdapter):
    name = "llamacpp"

    def __init__(
        self,
        host: str,
        port: int,
        model_name: str,
        timeout_seconds: float = 600.0,
        temperature: float = 0.1,
        n_predict: int = 3072,
    ):
        self._base = f"http://{host}:{port}"
        self._model = model_name
        self._timeout = timeout_seconds
        self._temperature = temperature
        self._n_predict = n_predict
        self._transport: httpx.AsyncBaseTransport | None = None

    def _client(self, timeout: float) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport, timeout=timeout)
        return httpx.AsyncClient(timeout=timeout)

    def set_transport(self, transport: httpx.AsyncBaseTransport) -> None:
        """Test hook — inject a MockTransport."""
        self._transport = transport

    async def health(self) -> bool:
        try:
            async with self._client(5.0) as c:
                r = await c.get(f"{self._base}/health")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        prompt = build_prompt(req.source_lang, req.target_lang, req.text)

        payload = {
            "prompt": prompt,
            "temperature": self._temperature,
            "n_predict": self._n_predict,
            "cache_prompt": True,
            "stream": False,
            "stop": ["<end_of_turn>", "<start_of_turn>", "<eos>"],
        }
        async with self._client(self._timeout) as c:
            r = await c.post(f"{self._base}/completion", json=payload)
            r.raise_for_status()
            data = r.json()

        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"llama-server returned empty completion: {data}")

        return TranslationResult(
            text=content.strip(),
            model_name=self._model,
            tokens_in=data.get("tokens_evaluated"),
            tokens_out=data.get("tokens_predicted"),
        )
