"""Tests for the NPL matcher pure functions."""

import pytest

from nexus.assets.transform.npl_matcher import (
    _dedup_matches,  # pyright: ignore[reportPrivateUsage]
    _fuzzy_match_all,  # pyright: ignore[reportPrivateUsage]
    _tokenize,  # pyright: ignore[reportPrivateUsage]
    build_inverted_index,
    evaluate_matches,
)

# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


def test_tokenize_basic() -> None:
    tokens = _tokenize("Deep Learning for Silicon Photonics")
    assert "learning" in tokens
    assert "silicon" in tokens
    assert "photonics" in tokens
    # short words dropped
    assert "for" not in tokens
    assert "deep" not in tokens  # 4 chars < 5


def test_tokenize_empty() -> None:
    assert _tokenize("") == frozenset()


def test_tokenize_case_insensitive() -> None:
    assert _tokenize("SILICON") == _tokenize("silicon")


# ---------------------------------------------------------------------------
# build_inverted_index
# ---------------------------------------------------------------------------


def test_build_inverted_index_basic() -> None:
    pairs = [
        ("W1", "Silicon Photonics for Integrated Circuits"),
        ("W2", "Neuromorphic Computing with Memristors"),
        ("W3", "Photonic Integration on Silicon Wafers"),
    ]
    index = build_inverted_index(pairs)
    # "silicon" appears in W1 and W3
    assert set(index.get("silicon", [])) == {"W1", "W3"}
    # "neuromorphic" only in W2
    assert index.get("neuromorphic") == ["W2"]
    # "photonic" only in W3 ("Photonic Integration on Silicon Wafers")
    assert set(index.get("photonic", [])) == {"W3"}


def test_build_inverted_index_max_postings() -> None:
    # Token appearing in more titles than max_postings is dropped
    pairs = [("W" + str(i), "model neural network") for i in range(5)]
    index = build_inverted_index(pairs, max_postings=3)
    # "model" (5 chars, 5 occurrences) exceeds max_postings=3 → dropped
    assert "model" not in index
    # "neural" (6 chars, 5 occurrences) also dropped
    assert "neural" not in index


def test_build_inverted_index_empty() -> None:
    assert build_inverted_index([]) == {}


# ---------------------------------------------------------------------------
# evaluate_matches
# ---------------------------------------------------------------------------


def test_evaluate_matches_perfect() -> None:
    pairs = {("P1", "W1"), ("P2", "W2")}
    gold = {("P1", "W1"), ("P2", "W2")}
    result = evaluate_matches(pairs, gold)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["tp"] == 2
    assert result["fp"] == 0
    assert result["fn"] == 0


def test_evaluate_matches_zero_precision() -> None:
    pairs = {("P1", "W9")}  # no gold match
    gold = {("P1", "W1")}
    result = evaluate_matches(pairs, gold)
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["fp"] == 1.0
    assert result["fn"] == 1.0


def test_evaluate_matches_partial() -> None:
    pairs = {("P1", "W1"), ("P2", "W9")}  # W9 is a false positive
    gold = {("P1", "W1"), ("P3", "W3")}
    result = evaluate_matches(pairs, gold)
    assert result["tp"] == 1.0
    assert result["fp"] == 1.0
    assert result["fn"] == 1.0
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)


def test_evaluate_matches_empty_predictions() -> None:
    result = evaluate_matches(set(), {("P1", "W1")})
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0


# ---------------------------------------------------------------------------
# _fuzzy_match_all
# ---------------------------------------------------------------------------

_OA_TITLES: dict[str, str] = {
    "W100": "Advances in EUV Lithography for Semiconductor Manufacturing",
    "W101": "Silicon Photonics Integration on Standard CMOS Platforms",
    "W102": "Neuromorphic Computing Architectures Using Memristive Devices",
    "W999": "Unrelated Topic in Completely Different Domain",
}

_INDEX = build_inverted_index(list(_OA_TITLES.items()))


def test_fuzzy_match_finds_euv() -> None:
    npl_rows = [
        (
            "US12345",
            0,
            "Smith, J. et al. (2019). Advances in EUV Lithography for Semiconductor "
            "Manufacturing. Journal of Applied Physics, vol. 120, pp. 101-115.",
        ),
    ]
    results = _fuzzy_match_all(npl_rows, _OA_TITLES, _INDEX)
    assert len(results) == 1
    patent_id, work_id, score = results[0]
    assert patent_id == "US12345"
    assert work_id == "W100"
    # token_set_ratio with full citation strings (author names, journal info, etc.)
    # gives a lower score than raw-title comparison; ≥ 80 confirms a clear match
    assert score >= 80


def test_fuzzy_match_no_match_below_min_len() -> None:
    npl_rows = [("US99999", 0, "Short")]
    results = _fuzzy_match_all(npl_rows, _OA_TITLES, _INDEX)
    assert results == []


def test_fuzzy_match_multiple_npl_strings() -> None:
    npl_rows = [
        (
            "P1", 0,
            "Doe, A. (2020). Silicon Photonics Integration on Standard CMOS Platforms. "
            "Optics Letters, 45(3), 123-130.",
        ),
        (
            "P2", 0,
            "Green, B. (2018). Neuromorphic Computing Architectures Using Memristive "
            "Devices for Edge AI Applications.",
        ),
    ]
    results = _fuzzy_match_all(npl_rows, _OA_TITLES, _INDEX)
    by_patent = {r[0]: (r[1], r[2]) for r in results}
    assert by_patent["P1"][0] == "W101"
    assert by_patent["P2"][0] == "W102"
    assert by_patent["P1"][1] >= 90
    assert by_patent["P2"][1] >= 90


# ---------------------------------------------------------------------------
# _dedup_matches
# ---------------------------------------------------------------------------


def test_dedup_prefers_high_over_medium() -> None:
    matches = [
        {"patent_id": "P1", "work_id": "W1", "confidence": "medium",
         "match_method": "npl_citation", "doi_extracted": None},
        {"patent_id": "P1", "work_id": "W1", "confidence": "high",
         "match_method": "npl_citation", "doi_extracted": "10.1234/abc"},
    ]
    result = _dedup_matches(matches)
    assert len(result) == 1
    assert result[0]["confidence"] == "high"
    assert result[0]["doi_extracted"] == "10.1234/abc"


def test_dedup_different_works_kept() -> None:
    matches = [
        {"patent_id": "P1", "work_id": "W1", "confidence": "high",
         "match_method": "npl_citation", "doi_extracted": "10.1/a"},
        {"patent_id": "P1", "work_id": "W2", "confidence": "medium",
         "match_method": "npl_citation", "doi_extracted": None},
    ]
    result = _dedup_matches(matches)
    assert len(result) == 2


def test_dedup_high_not_overwritten_by_medium() -> None:
    matches = [
        {"patent_id": "P1", "work_id": "W1", "confidence": "high",
         "match_method": "npl_citation", "doi_extracted": "10.1/a"},
        {"patent_id": "P1", "work_id": "W1", "confidence": "medium",
         "match_method": "npl_citation", "doi_extracted": None},
    ]
    result = _dedup_matches(matches)
    assert len(result) == 1
    assert result[0]["confidence"] == "high"
