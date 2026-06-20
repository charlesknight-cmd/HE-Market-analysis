"""Tests for the conservative singular/plural folding used by the title-word and
keyword-premium charts (analysis.trends.merge_plural_variants).

The invariant: a plural folds into its singular ONLY when both forms are present,
and the must-not-mangle words are never collapsed even when a coincidental shorter
token co-occurs.
"""

from collections import Counter

import pytest

from analysis.trends import merge_plural_variants, _singular_candidates


@pytest.mark.parametrize("counts, expected", [
    # --- legitimate merges (both forms present) ---
    ({"lecturer": 10, "lecturers": 4}, {"lecturer": 14}),
    ({"fellowship": 5, "fellowships": 2}, {"fellowship": 7}),
    ({"scientist": 8, "scientists": 3}, {"scientist": 11}),
    ({"manager": 2, "managers": 2}, {"manager": 4}),
    ({"library": 3, "libraries": 2}, {"library": 5}),        # y -> ies
    ({"process": 5, "processes": 2}, {"process": 7}),         # -es, must NOT be blocked
    ({"class": 3, "classes": 2}, {"class": 5}),               # -es
    ({"bus": 2, "buses": 1, "campus": 4}, {"bus": 3, "campus": 4}),
    # --- orphan plural (no singular present) stays put ---
    ({"professors": 6}, {"professors": 6}),
])
def test_legitimate_and_orphan(counts, expected):
    assert merge_plural_variants(counts) == expected


DANGEROUS = ["business", "studies", "analysis", "analyses", "physics", "campus",
             "mathematics", "news", "access", "status", "species", "series",
             "lens", "bias", "kudos"]


@pytest.mark.parametrize("word", DANGEROUS)
def test_dangerous_words_never_depluralised(word):
    # Alone, and with a coincidental shorter token present, they must be untouched.
    assert merge_plural_variants({word: 5}) == {word: 5}
    assert _singular_candidates(word) == []


@pytest.mark.parametrize("counts", [
    {"studies": 7, "study": 2},           # lexicalised -ies: do NOT collapse
    {"analyses": 3, "analyse": 1},        # Greek/Latin irregular plural
    {"news": 1, "new": 3},                # mass noun
    {"physics": 4, "physic": 1},          # -ics guard
    {"business": 3, "busines": 1},        # -ss guard
    {"campus": 2, "campu": 1},            # -us guard
    {"lens": 2, "len": 1},                # blocklist (lens/len)
    {"bias": 2, "bia": 1},                # blocklist (bias/bia)
])
def test_adversarial_cooccurrence_not_merged(counts):
    assert merge_plural_variants(counts) == counts


def test_counter_input_and_returns_plain_dict():
    out = merge_plural_variants(Counter({"role": 3, "roles": 2}))
    assert out == {"role": 5}
    assert type(out) is dict


def test_determinism():
    counts = {"editor": 1, "editors": 1, "reviewer": 2, "reviewers": 1}
    assert merge_plural_variants(counts) == merge_plural_variants(dict(counts))
