"""Tests for nexus.assets.entity_resolution.assemble.build_org_crosswalk."""

from __future__ import annotations

import polars as pl

from nexus.assets.entity_resolution.assemble import build_org_crosswalk

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
# PatentsView:
#   A001 "NVIDIA Corporation"     → normalized "nvidia"       (in seed → org_nvidia)
#   A002 "Intel Corporation"      → normalized "intel"        (in seed → org_intel)
#   A003 "Unknown Fab Inc"        → normalized "unknown fab"  (not in seed, matched via fuzzy)
#   A004 "Random Corp"            → normalized "random"       (PV-only fallback)
#
# OpenAlex:
#   I001 "NVIDIA"                 → normalized "nvidia"       (fuzzy → A001 → org_nvidia)
#   I002 "Intel"                  → normalized "intel"        (fuzzy → A002 → org_intel)
#   I003 "Unknown Fab"            → normalized "unknown fab"  (fuzzy → A003, new org_id)
#   I004 "MIT"                    → normalized "mit"          (OA-only fallback)
#
# Seed matches:
#   (org_nvidia, NVIDIA, A001, NVIDIA Corporation, seed_crosswalk, high)
#   (org_intel,  Intel,  A002, Intel Corporation,  seed_crosswalk, high)
#
# Fuzzy bridge:
#   (I001, A001, 100.0, fuzzy_high, high)
#   (I002, A002, 100.0, fuzzy_high, high)
#   (I003, A003,  95.0, fuzzy_high, high)

_SEED = pl.DataFrame(
    {
        "org_id": ["org_nvidia", "org_intel"],
        "canonical_name": ["NVIDIA", "Intel"],
        "assignee_id": ["A001", "A002"],
        "display_name": ["NVIDIA Corporation", "Intel Corporation"],
        "openalex_institution_id": ["", ""],
        "match_method": ["seed_crosswalk", "seed_crosswalk"],
        "confidence": ["high", "high"],
    }
)

_FUZZY = pl.DataFrame(
    {
        "institution_id": ["I001", "I002", "I003"],
        "assignee_id": ["A001", "A002", "A003"],
        "similarity": [100.0, 100.0, 95.0],
        "match_method": ["fuzzy_high", "fuzzy_high", "fuzzy_high"],
        "confidence": ["high", "high", "high"],
    }
)

_PV = pl.DataFrame(
    {
        "assignee_id": ["A001", "A002", "A003", "A004"],
        "display_name": [
            "NVIDIA Corporation",
            "Intel Corporation",
            "Unknown Fab Inc",
            "Random Corp",
        ],
        "normalized_name": ["nvidia", "intel", "unknown fab", "random"],
        "match_method": ["native_id"] * 4,
        "confidence": ["high"] * 4,
    }
)

_OA = pl.DataFrame(
    {
        "institution_id": ["I001", "I002", "I003", "I004"],
        "display_name": ["NVIDIA", "Intel", "Unknown Fab", "MIT"],
        "normalized_name": ["nvidia", "intel", "unknown fab", "mit"],
        "match_method": ["ror"] * 4,
        "confidence": ["high"] * 4,
    }
)


_SEED_OA: pl.DataFrame = pl.DataFrame(
    schema={
        "org_id": pl.String,
        "canonical_name": pl.String,
        "institution_id": pl.String,
        "display_name": pl.String,
        "match_method": pl.String,
        "confidence": pl.String,
    }
)


def _build() -> pl.DataFrame:
    return build_org_crosswalk(_SEED, _SEED_OA, _FUZZY, _PV, _OA)


# ---------------------------------------------------------------------------
# Coverage: every source entity gets one row
# ---------------------------------------------------------------------------


def test_all_pv_assignees_present() -> None:
    df = _build()
    pv_ids = set(df.filter(pl.col("source") == "patentsview")["source_id"].to_list())  # type: ignore[reportUnknownMemberType]
    assert {"A001", "A002", "A003", "A004"} == pv_ids


def test_all_oa_institutions_present() -> None:
    df = _build()
    oa_ids = set(df.filter(pl.col("source") == "openalex")["source_id"].to_list())  # type: ignore[reportUnknownMemberType]
    assert {"I001", "I002", "I003", "I004"} == oa_ids


def test_no_duplicate_source_ids() -> None:
    """Each (source, source_id) pair must appear exactly once."""
    df = _build()
    pairs_list = list(zip(df["source"].to_list(), df["source_id"].to_list(), strict=True))
    assert len(pairs_list) == len(set(pairs_list))


# ---------------------------------------------------------------------------
# Org_id inheritance
# ---------------------------------------------------------------------------


def test_seed_org_id_inherited_by_oa_nvidia() -> None:
    """I001 (NVIDIA OA) must inherit org_id='org_nvidia' from seed via fuzzy bridge."""
    df = _build()
    row = next(r for r in df.to_dicts() if r["source_id"] == "I001")
    assert row["org_id"] == "org_nvidia"


def test_seed_org_id_inherited_by_oa_intel() -> None:
    df = _build()
    row = next(r for r in df.to_dicts() if r["source_id"] == "I002")
    assert row["org_id"] == "org_intel"


def test_non_seed_pv_and_oa_share_org_id() -> None:
    """A003 (not in seed) and I003 (fuzzy-matched to A003) must share the same org_id."""
    df = _build()
    pv_row = next(r for r in df.to_dicts() if r["source_id"] == "A003")
    oa_row = next(r for r in df.to_dicts() if r["source_id"] == "I003")
    assert pv_row["org_id"] == oa_row["org_id"]


def test_pv_fallback_org_id_prefix() -> None:
    """A004 (PV-only, no fuzzy match) must get an org_id starting with 'org_pv_'."""
    df = _build()
    row = next(r for r in df.to_dicts() if r["source_id"] == "A004")
    assert row["org_id"].startswith("org_pv_")


def test_oa_fallback_org_id_prefix() -> None:
    """I004 (OA-only, no PV match) must get an org_id starting with 'org_oa_'."""
    df = _build()
    row = next(r for r in df.to_dicts() if r["source_id"] == "I004")
    assert row["org_id"].startswith("org_oa_")


# ---------------------------------------------------------------------------
# Match method propagation
# ---------------------------------------------------------------------------


def test_seed_rows_carry_seed_crosswalk_method() -> None:
    df = _build()
    pv_nvidia = next(r for r in df.to_dicts() if r["source_id"] == "A001")
    assert pv_nvidia["match_method"] == "seed_crosswalk"


def test_fuzzy_matched_oa_carries_fuzzy_method() -> None:
    df = _build()
    oa_nvidia = next(r for r in df.to_dicts() if r["source_id"] == "I001")
    assert oa_nvidia["match_method"] == "fuzzy_high"


def test_oa_fallback_carries_ror_method() -> None:
    df = _build()
    row = next(r for r in df.to_dicts() if r["source_id"] == "I004")
    assert row["match_method"] == "ror"


def test_pv_fallback_carries_native_id_method() -> None:
    df = _build()
    row = next(r for r in df.to_dicts() if r["source_id"] == "A004")
    assert row["match_method"] == "native_id"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_seed_oa_match_uses_known_org_id() -> None:
    """Stanford: PV legal name and OA display name differ — linked via openalex_institution_id."""
    seed_oa = pl.DataFrame(
        {
            "org_id": ["org_stanford"],
            "canonical_name": ["Stanford University"],
            "institution_id": ["https://openalex.org/I97018004"],
            "display_name": ["Stanford University"],
            "match_method": ["seed_crosswalk"],
            "confidence": ["high"],
        }
    )
    oa_with_stanford = pl.concat([
        _OA,
        pl.DataFrame({
            "institution_id": ["https://openalex.org/I97018004"],
            "display_name": ["Stanford University"],
            "normalized_name": ["stanford university"],
            "match_method": ["ror"],
            "confidence": ["high"],
        }),
    ])
    df = build_org_crosswalk(_SEED, seed_oa, _FUZZY, _PV, oa_with_stanford)
    row = next(r for r in df.to_dicts() if r["source_id"] == "https://openalex.org/I97018004")
    assert row["org_id"] == "org_stanford"
    assert row["match_method"] == "seed_crosswalk"


def test_output_schema() -> None:
    df = _build()
    expected = {"org_id", "source", "source_id", "canonical_name", "match_method", "confidence"}
    assert set(df.columns) == expected


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_all_returns_empty_df() -> None:
    empty_seed = pl.DataFrame(
        schema={
            "org_id": pl.String,
            "canonical_name": pl.String,
            "assignee_id": pl.String,
            "display_name": pl.String,
            "openalex_institution_id": pl.String,
            "match_method": pl.String,
            "confidence": pl.String,
        }
    )
    empty_fuzzy = pl.DataFrame(
        schema={
            "institution_id": pl.String,
            "assignee_id": pl.String,
            "similarity": pl.Float64,
            "match_method": pl.String,
            "confidence": pl.String,
        }
    )
    empty_pv = pl.DataFrame(
        schema={
            "assignee_id": pl.String,
            "display_name": pl.String,
            "normalized_name": pl.String,
            "match_method": pl.String,
            "confidence": pl.String,
        }
    )
    empty_oa = pl.DataFrame(
        schema={
            "institution_id": pl.String,
            "display_name": pl.String,
            "normalized_name": pl.String,
            "match_method": pl.String,
            "confidence": pl.String,
        }
    )
    empty_seed_oa = pl.DataFrame(
        schema={
            "org_id": pl.String,
            "canonical_name": pl.String,
            "institution_id": pl.String,
            "display_name": pl.String,
            "match_method": pl.String,
            "confidence": pl.String,
        }
    )
    df = build_org_crosswalk(empty_seed, empty_seed_oa, empty_fuzzy, empty_pv, empty_oa)
    assert len(df) == 0
    assert set(df.columns) == {
        "org_id", "source", "source_id", "canonical_name", "match_method", "confidence"
    }
