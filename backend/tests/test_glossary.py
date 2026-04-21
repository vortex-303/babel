from __future__ import annotations

from app.services.glossary import extract_terms


ALICE = """
Alice was beginning to get very tired of sitting by her sister on the bank.
Suddenly a White Rabbit with pink eyes ran close by her.

Alice thought to herself. "Well!" thought Alice. The White Rabbit was late.
The Cheshire Cat appeared on the tree. The Cheshire Cat vanished slowly.
The Mad Hatter poured tea. The March Hare agreed. The Mad Hatter laughed.

Down the rabbit hole Alice went. Alice fell for a long time.
"""


def test_extracts_alice_as_top_term():
    terms = extract_terms(ALICE, min_occurrences=2, top_n=20)
    names = [t.source_term for t in terms]
    assert "Alice" in names
    assert any(n.startswith("White Rabbit") for n in names)
    assert any(n.startswith("Cheshire Cat") for n in names)


def test_filters_single_stopwords():
    text = "The the the. A a a. And and and."
    terms = extract_terms(text, min_occurrences=2, top_n=10)
    assert all(t.source_term.lower() not in {"the", "a", "and"} for t in terms)


def test_respects_min_occurrences():
    # "Alice" appears 3 times in ALICE; "Mad Hatter" appears 2.
    terms = extract_terms(ALICE, min_occurrences=3, top_n=20)
    names = [t.source_term for t in terms]
    assert "Alice" in names
    # Mad Hatter only appears twice → excluded at threshold 3.
    assert not any(n.startswith("Mad Hatter") for n in names)


def test_respects_top_n():
    terms = extract_terms(ALICE, min_occurrences=1, top_n=3)
    assert len(terms) <= 3


def test_occurrences_counts_are_accurate():
    terms = extract_terms(ALICE, min_occurrences=2, top_n=50)
    by_name = {t.source_term: t.occurrences for t in terms}
    # "Alice" appears 4 times in ALICE
    assert by_name.get("Alice", 0) >= 3
