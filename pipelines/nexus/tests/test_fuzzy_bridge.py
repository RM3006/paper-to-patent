"""Tests for nexus.assets.entity_resolution.fuzzy_bridge.build_fuzzy_bridge."""

from __future__ import annotations

import polars as pl

from nexus.assets.entity_resolution.fuzzy_bridge import build_fuzzy_bridge

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
# PatentsView orgs (PV):
#   A001  "nvidia"
#   A002  "taiwan semiconductor manufacturing"
#   A003  "asml"
#   A004  "intel"
#   A005  "applied materials"   (no OA counterpart in fixture)
#
# OpenAlex institutions (OA):
#   I001  "nvidia"                            → exact match → A001  (fuzzy_high)
#   I002  "taiwan semiconductor manufacturing" → exact match → A002  (fuzzy_high)
#   I003  "asml holding"                       → first token "asml" → A003 (fuzzy_high)
#   I004  "totally unrelated company"          → no first-token match → excluded
#   I005  "intel corporation"                  → first token "intel" → A004 (fuzzy_high)

_PV = pl.DataFrame(
    {
        "assignee_id": ["A001", "A002", "A003", "A004", "A005"],
        "normalized_name": [
            "nvidia",
            "taiwan semiconductor manufacturing",
            "asml",
            "intel",
            "applied materials",
        ],
    }
)

_OA = pl.DataFrame(
    {
        "institution_id": ["I001", "I002", "I003", "I004", "I005"],
        "normalized_name": [
            "nvidia",
            "taiwan semiconductor manufacturing",
            "asml holding",
            "totally unrelated company",
            "intel corporation",
        ],
    }
)


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------


def test_exact_match_nvidia() -> None:
    """OA 'nvidia' matches PV 'nvidia' with score 100 → fuzzy_high."""
    df = build_fuzzy_bridge(_PV, _OA)
    row = next(r for r in df.to_dicts() if r["institution_id"] == "I001")
    assert row["assignee_id"] == "A001"
    assert row["match_method"] == "fuzzy_high"
    assert row["confidence"] == "high"
    assert row["similarity"] >= 90.0


def test_exact_match_tsmc() -> None:
    df = build_fuzzy_bridge(_PV, _OA)
    row = next(r for r in df.to_dicts() if r["institution_id"] == "I002")
    assert row["assignee_id"] == "A002"
    assert row["match_method"] == "fuzzy_high"


def test_near_match_asml_holding() -> None:
    """OA 'asml holding' fuzzy-matches PV 'asml' → fuzzy_high (token_set_ratio ignores extras)."""
    df = build_fuzzy_bridge(_PV, _OA)
    row = next(r for r in df.to_dicts() if r["institution_id"] == "I003")
    assert row["assignee_id"] == "A003"
    assert row["match_method"] == "fuzzy_high"


def test_near_match_intel_corporation() -> None:
    """OA 'intel corporation' → first token 'intel' blocks to A004."""
    df = build_fuzzy_bridge(_PV, _OA)
    row = next(r for r in df.to_dicts() if r["institution_id"] == "I005")
    assert row["assignee_id"] == "A004"
    assert row["match_method"] == "fuzzy_high"


def test_no_block_match_excluded() -> None:
    """OA 'totally unrelated company' has no PV org sharing first token → excluded."""
    df = build_fuzzy_bridge(_PV, _OA)
    assert "I004" not in df["institution_id"].to_list()


def test_pv_only_org_not_in_output() -> None:
    """A005 'applied materials' has no OA counterpart → not in output (output is OA-keyed)."""
    df = build_fuzzy_bridge(_PV, _OA)
    assert "A005" not in df["assignee_id"].to_list()


# ---------------------------------------------------------------------------
# Review threshold
# ---------------------------------------------------------------------------


def test_review_threshold_respected() -> None:
    """A low-similarity pair below HIGH but above REVIEW → fuzzy_review."""
    pv = pl.DataFrame(
        {"assignee_id": ["X001"], "normalized_name": ["semiconductor manufacturing taiwan"]}
    )
    oa = pl.DataFrame(
        {"institution_id": ["Y001"], "normalized_name": ["semiconductor manufacturing"]}
    )
    build_fuzzy_bridge(pv, oa, high_threshold=100, review_threshold=70)
    # token_set_ratio("semiconductor manufacturing", "semiconductor manufacturing taiwan")
    # = 100 with token_set_ratio (shorter set is contained) — so this actually hits high.
    # Use a more clearly different pair instead.
    pv2 = pl.DataFrame({"assignee_id": ["X002"], "normalized_name": ["samsung display"]})
    oa2 = pl.DataFrame({"institution_id": ["Y002"], "normalized_name": ["samsung electronics"]})
    df2 = build_fuzzy_bridge(pv2, oa2, high_threshold=100, review_threshold=60)
    assert len(df2) == 1
    assert df2["match_method"][0] == "fuzzy_review"
    assert df2["confidence"][0] == "medium"


def test_below_review_threshold_excluded() -> None:
    """A pair below the review threshold must not appear in output."""
    pv = pl.DataFrame({"assignee_id": ["X001"], "normalized_name": ["alpha beta gamma"]})
    oa = pl.DataFrame(
        {"institution_id": ["Y001"], "normalized_name": ["alpha completely different"]}
    )
    df = build_fuzzy_bridge(pv, oa, high_threshold=100, review_threshold=100)
    assert len(df) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_pv_returns_empty() -> None:
    empty_pv = pl.DataFrame(schema={"assignee_id": pl.String, "normalized_name": pl.String})
    df = build_fuzzy_bridge(empty_pv, _OA)
    assert len(df) == 0


def test_empty_oa_returns_empty() -> None:
    empty_oa = pl.DataFrame(schema={"institution_id": pl.String, "normalized_name": pl.String})
    df = build_fuzzy_bridge(_PV, empty_oa)
    assert len(df) == 0


def test_output_schema() -> None:
    df = build_fuzzy_bridge(_PV, _OA)
    expected = {"institution_id", "assignee_id", "similarity", "match_method", "confidence"}
    assert set(df.columns) == expected


def test_one_row_per_oa_institution() -> None:
    """Each OA institution appears at most once in output (best PV match only)."""
    df = build_fuzzy_bridge(_PV, _OA)
    matched = [r for r in df.to_dicts() if r["institution_id"] in {"I001", "I002", "I003", "I005"}]
    institution_ids = [r["institution_id"] for r in matched]
    assert len(institution_ids) == len(set(institution_ids))
