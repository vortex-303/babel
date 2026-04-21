from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Capture capitalized word sequences (e.g. "Alice", "Cheshire Cat", "River Thames").
# Requires the first char to be uppercase, allows apostrophes and hyphens,
# chains multi-word capitalized sequences.
_TERM_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s(\"'‘“]))"
    r"[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü'’-]*"
    r"(?:\s+[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü'’-]*){0,3}"
)

# Words that are almost always spurious hits (sentence starters, pronouns,
# common title words). Lowercased match.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "of",
        "for", "with", "from", "by", "is", "are", "was", "were", "be", "been",
        "being", "it", "its", "he", "she", "they", "we", "you", "i", "this",
        "that", "these", "those", "there", "here", "then", "when", "while",
        "which", "who", "whom", "whose", "what", "why", "how", "not", "no",
        "yes", "so", "as", "than", "though", "although", "because", "since",
        "until", "after", "before", "during", "about", "over", "under", "into",
        "through", "between", "among", "against", "without", "within", "upon",
        "down", "up", "out", "off", "very", "just", "only", "even", "also",
        "still", "already", "never", "always", "sometimes", "often", "once",
        "twice", "said", "replied", "cried", "answered", "asked", "called",
        "went", "came", "got", "put", "took", "gave", "made", "done", "seen",
        "heard", "saw", "had", "has", "have", "will", "would", "could",
        "should", "might", "must", "shall", "can", "may", "let", "chapter",
        "page", "contents", "end", "beginning", "first", "second", "third",
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten",
    }
)


@dataclass
class ExtractedTerm:
    source_term: str
    occurrences: int


def extract_terms(
    text: str, *, min_occurrences: int = 2, top_n: int = 50
) -> list[ExtractedTerm]:
    """Pull candidate glossary terms from plain text.

    Strategy: match multi-word capitalized phrases. Fold case for counting so
    "Alice" and "alice" at sentence start both count toward the same entry.
    Filter out common stopword-only matches and drop any single-word term that
    is actually just a stopword with a capital letter (sentence-start noise)."""
    raw_counts: Counter[str] = Counter()

    for match in _TERM_RE.finditer(text):
        term = match.group(0).strip()
        if not term:
            continue

        words = term.split()

        # Strip leading AND trailing stopwords ("The Cheshire Cat" → "Cheshire
        # Cat", "Alice And" → "Alice"). Happens frequently with sentence-start
        # matches like "The Rabbit" where "The" is capitalized only because
        # it's at the start of a sentence.
        while words and words[0].lower() in _STOPWORDS:
            words.pop(0)
        while words and words[-1].lower() in _STOPWORDS:
            words.pop()

        if not words:
            continue

        term = " ".join(words)
        raw_counts[term] += 1

    # Coalesce case variants: prefer the most common casing for display.
    folded: dict[str, Counter[str]] = {}
    for term, n in raw_counts.items():
        key = term.lower()
        folded.setdefault(key, Counter())[term] += n

    results: list[ExtractedTerm] = []
    for counter in folded.values():
        total = sum(counter.values())
        if total < min_occurrences:
            continue
        best_form = counter.most_common(1)[0][0]
        results.append(ExtractedTerm(source_term=best_form, occurrences=total))

    results.sort(key=lambda t: (-t.occurrences, t.source_term.lower()))
    return results[:top_n]
