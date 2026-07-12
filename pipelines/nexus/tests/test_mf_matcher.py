"""Tests for the Marx & Fuegi NPL-link asset's pure helpers."""

from nexus.assets.transform.mf_matcher import mf_confidence


def test_mf_confidence_front_page_is_high() -> None:
    assert mf_confidence("front") == "high"


def test_mf_confidence_both_is_high() -> None:
    assert mf_confidence("both") == "high"


def test_mf_confidence_body_only_is_medium() -> None:
    assert mf_confidence("body") == "medium"


def test_mf_confidence_unknown_value_is_medium() -> None:
    # Defensive: any value that isn't explicitly front-page-ish falls to medium
    # rather than raising, since Marx & Fuegi's wherefound is external data.
    assert mf_confidence("unexpected") == "medium"
