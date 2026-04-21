from __future__ import annotations

from app.adapters.llamacpp import build_prompt


def test_es_ar_rioplatense_hint():
    p = build_prompt("en", "es-AR", "Hello.")
    assert "rioplatense" in p.lower()
    assert "voseo" in p.lower()
    assert "Spanish (es-AR)" in p


def test_es_mx_mexican_hint():
    p = build_prompt("en", "es-MX", "Hello.")
    assert "mexican" in p.lower()
    assert "Spanish (es-MX)" in p


def test_es_es_peninsular_hint():
    p = build_prompt("en", "es-ES", "Hello.")
    assert "peninsular" in p.lower()
    assert "Spanish (es-ES)" in p


def test_pt_br_hint():
    p = build_prompt("en", "pt-BR", "Hello.")
    assert "brazilian" in p.lower()
    assert "Portuguese (pt-BR)" in p


def test_plain_es_has_no_variant_hint():
    p = build_prompt("en", "es", "Hello.")
    assert "rioplatense" not in p.lower()
    assert "brazilian" not in p.lower()
    assert "Spanish (es)" in p


def test_es_419_normalizes_to_es():
    p = build_prompt("en", "es-419", "Hello.")
    assert "es-419" not in p
    assert "Spanish (es)" in p
