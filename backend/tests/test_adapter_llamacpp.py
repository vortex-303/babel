from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.base import TranslationRequest
from app.adapters.llamacpp import LlamaCppAdapter, build_prompt


def _make_adapter(handler) -> LlamaCppAdapter:
    adapter = LlamaCppAdapter(host="127.0.0.1", port=8080, model_name="test-model")
    adapter.set_transport(httpx.MockTransport(handler))
    return adapter


def test_build_prompt_matches_translategemma_template():
    prompt = build_prompt("en", "es", "Hello world.")
    assert prompt.startswith("<start_of_turn>user\n")
    assert prompt.endswith("<start_of_turn>model\n")
    assert "English (en)" in prompt
    assert "Spanish (es)" in prompt
    # Body text appears verbatim — template trims whitespace.
    assert "Hello world." in prompt
    # Template leaves two newlines then a blank line between the instruction
    # and the source text (literal "\n\n\n" in the Jinja).
    assert "Spanish:\n\n\nHello world." in prompt


def test_build_prompt_injects_variant_hint_for_es_ar():
    prompt = build_prompt("en", "es-AR", "Hello.")
    assert "Spanish (es-AR)" in prompt
    assert "rioplatense" in prompt.lower()
    assert "voseo" in prompt.lower()


def test_build_prompt_maps_unsupported_es_419_to_es():
    prompt = build_prompt("en", "es-419", "Hello.")
    # Should normalize to "es" since the model's dict has no es-419.
    assert "Spanish (es)" in prompt
    assert "es-419" not in prompt


@pytest.mark.asyncio
async def test_translate_hits_completion_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": "Hola mundo.",
                "tokens_evaluated": 12,
                "tokens_predicted": 4,
            },
        )

    adapter = _make_adapter(handler)
    result = await adapter.translate(
        TranslationRequest(text="Hello world.", source_lang="en", target_lang="es")
    )

    assert result.text == "Hola mundo."
    assert result.tokens_in == 12
    assert result.tokens_out == 4
    assert captured["url"].endswith("/completion")
    body = captured["body"]
    assert body["stream"] is False
    assert body["temperature"] == pytest.approx(0.1)
    # The prompt we send MUST include the model's exact translator instruction.
    assert "professional English (en) to Spanish (es) translator" in body["prompt"]
    assert "Hello world." in body["prompt"]
    assert "<end_of_turn>" in body["stop"]


@pytest.mark.asyncio
async def test_translate_raises_on_empty_completion():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "   "})

    adapter = _make_adapter(handler)
    with pytest.raises(RuntimeError, match="empty completion"):
        await adapter.translate(
            TranslationRequest(text="x", source_lang="en", target_lang="es")
        )


@pytest.mark.asyncio
async def test_translate_raises_on_http_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "model not loaded"})

    adapter = _make_adapter(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.translate(
            TranslationRequest(text="x", source_lang="en", target_lang="es")
        )


@pytest.mark.asyncio
async def test_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    adapter = _make_adapter(handler)
    assert await adapter.health() is True


@pytest.mark.asyncio
async def test_health_bad_status():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = _make_adapter(handler)
    assert await adapter.health() is False
