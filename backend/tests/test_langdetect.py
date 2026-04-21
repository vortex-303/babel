from __future__ import annotations

from app.services.langdetect_util import detect_language


def test_detects_english():
    code, conf = detect_language(
        "The quick brown fox jumps over the lazy dog. It was a warm "
        "summer afternoon and the river ran wide and calm past the "
        "old mill."
    )
    assert code == "en"
    assert conf is not None and conf > 0.8


def test_detects_spanish():
    code, conf = detect_language(
        "El río era ancho y tranquilo. Alicia estaba sentada en la "
        "orilla, observando a un conejo con chaleco que pasaba corriendo "
        "hacia su madriguera."
    )
    assert code == "es"
    assert conf is not None and conf > 0.8


def test_short_text_returns_none():
    assert detect_language("Hello.") == (None, None)
    assert detect_language("") == (None, None)


def test_whitespace_only_returns_none():
    assert detect_language("   \n\n  ") == (None, None)
