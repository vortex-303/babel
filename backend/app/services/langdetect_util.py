from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect_langs

# Deterministic detection — default is non-deterministic per call.
DetectorFactory.seed = 0

# Short text fragments produce unreliable detection; require at least this
# many characters before trusting the result.
_MIN_CHARS = 80


def detect_language(text: str) -> tuple[str | None, float | None]:
    """Return (language_code, confidence) or (None, None) if indeterminate."""
    if not text:
        return None, None
    sample = text.strip()
    if len(sample) < _MIN_CHARS:
        return None, None
    try:
        ranked = detect_langs(sample[:20000])
    except LangDetectException:
        return None, None
    if not ranked:
        return None, None
    top = ranked[0]
    return top.lang, round(float(top.prob), 3)
