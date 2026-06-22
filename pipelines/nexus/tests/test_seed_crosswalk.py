"""Tests for nexus.assets.entity_resolution.seed.build_seed_crosswalk_matches."""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pytest

from nexus.assets.entity_resolution.seed import SEED_CSV, build_seed_crosswalk_matches

_Con = duckdb.DuckDBPyConnection

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
# Seed CSV (in-memory, written to tmp_path):
#   org_nvidia  NVIDIA          nvidia
#   org_asml    ASML            asml
#   org_asml    ASML            asml netherlands   (second variant same org_id)
#   org_tsmc    TSMC            taiwan semiconductor manufacturing
#   org_ghost   Ghost Corp      ghost corp          (no match in staging — excluded)
#
# PatentsView orgs staging:
#   A001  "nvidia"             → maps to org_nvidia
#   A002  "asml"               → maps to org_asml
#   A003  "asml netherlands"   → maps to org_asml (second variant)
#   A004  "taiwan semiconductor manufacturing"  → maps to org_tsmc
#   A005  "something else"     → no seed entry — not in output

SEED_CSV_CONTENT = """\
org_id,canonical_name,normalized_patentsview,openalex_institution_id
org_nvidia,NVIDIA,nvidia,
org_asml,ASML,asml,
org_asml,ASML,asml netherlands,
org_tsmc,TSMC,taiwan semiconductor manufacturing,
org_ghost,Ghost Corp,ghost corp,
"""

_PV_STAGING = pl.DataFrame(
    {
        "assignee_id": ["A001", "A002", "A003", "A004", "A005"],
        "display_name": [
            "NVIDIA Corporation",
            "ASML Holding N.V.",
            "ASML NETHERLANDS B.V.",
            "Taiwan Semiconductor Manufacturing Company, Ltd.",
            "Some Other Company",
        ],
        "normalized_name": [
            "nvidia",
            "asml",
            "asml netherlands",
            "taiwan semiconductor manufacturing",
            "something else",
        ],
        "match_method": ["native_id"] * 5,
        "confidence": ["high"] * 5,
    }
)


@pytest.fixture
def fixture_paths(tmp_path: Path) -> tuple[str, str]:
    """Write seed CSV and staging Parquet to tmp_path; return (seed_path, staging_path)."""
    seed_path = str(tmp_path / "seed.csv")
    staging_path = str(tmp_path / "staging.parquet")
    (tmp_path / "seed.csv").write_text(SEED_CSV_CONTENT)
    _PV_STAGING.write_parquet(staging_path)
    return seed_path, staging_path


@pytest.fixture
def con() -> _Con:
    return duckdb.connect()


# ---------------------------------------------------------------------------
# Matching correctness
# ---------------------------------------------------------------------------


def test_known_org_matched(fixture_paths: tuple[str, str], con: _Con) -> None:
    """org_nvidia must appear in output with the correct assignee_id."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    nvidia_rows = [r for r in df.to_dicts() if r["org_id"] == "org_nvidia"]
    assert len(nvidia_rows) == 1
    assert nvidia_rows[0]["assignee_id"] == "A001"


def test_org_with_two_variants_produces_two_rows(fixture_paths: tuple[str, str], con: _Con) -> None:
    """org_asml has two seed entries matching A002 and A003 — both must appear."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    asml_ids = [r["assignee_id"] for r in df.to_dicts() if r["org_id"] == "org_asml"]
    assert set(asml_ids) == {"A002", "A003"}


def test_seed_entry_with_no_match_excluded(fixture_paths: tuple[str, str], con: _Con) -> None:
    """org_ghost has no matching normalized_name in staging — must not appear."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    assert "org_ghost" not in df["org_id"].to_list()


def test_staging_org_with_no_seed_entry_excluded(fixture_paths: tuple[str, str], con: _Con) -> None:
    """A005 ('something else') has no seed entry — must not appear in output."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    assert "A005" not in df["assignee_id"].to_list()


def test_total_row_count(fixture_paths: tuple[str, str], con: _Con) -> None:
    """4 matches: nvidia(1) + asml(2) + tsmc(1) = 4."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    assert len(df) == 4


# ---------------------------------------------------------------------------
# Provenance tags
# ---------------------------------------------------------------------------


def test_match_method_is_seed_crosswalk(fixture_paths: tuple[str, str], con: _Con) -> None:
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    assert (df["match_method"] == "seed_crosswalk").all()


def test_confidence_is_high(fixture_paths: tuple[str, str], con: _Con) -> None:
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    assert (df["confidence"] == "high").all()


# ---------------------------------------------------------------------------
# Display name and org metadata carried through
# ---------------------------------------------------------------------------


def test_display_name_from_staging(fixture_paths: tuple[str, str], con: _Con) -> None:
    """display_name must come from the staging Parquet (raw PatentsView form)."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    row = next(r for r in df.to_dicts() if r["assignee_id"] == "A001")
    assert row["display_name"] == "NVIDIA Corporation"


def test_canonical_name_from_seed(fixture_paths: tuple[str, str], con: _Con) -> None:
    """canonical_name must come from the seed CSV."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    row = next(r for r in df.to_dicts() if r["assignee_id"] == "A001")
    assert row["canonical_name"] == "NVIDIA"


def test_openalex_institution_id_preserved(fixture_paths: tuple[str, str], con: _Con) -> None:
    """openalex_institution_id from the CSV is passed through (empty string for now)."""
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    # All entries in fixture CSV have blank openalex_institution_id
    assert df["openalex_institution_id"].is_null().all() or (
        df["openalex_institution_id"].cast(str).str.len_chars() == 0
    ).all()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_output_schema(fixture_paths: tuple[str, str], con: _Con) -> None:
    seed_path, staging_path = fixture_paths
    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    expected = {
        "org_id",
        "canonical_name",
        "assignee_id",
        "display_name",
        "openalex_institution_id",
        "match_method",
        "confidence",
    }
    assert set(df.columns) == expected


# ---------------------------------------------------------------------------
# Edge case — empty staging
# ---------------------------------------------------------------------------


def test_empty_staging_returns_empty_df(tmp_path: Path, con: _Con) -> None:
    """If staging has no rows, output is an empty DataFrame with correct schema."""
    empty = pl.DataFrame(
        schema={
            "assignee_id": pl.String,
            "display_name": pl.String,
            "normalized_name": pl.String,
            "match_method": pl.String,
            "confidence": pl.String,
        }
    )
    seed_path = str(tmp_path / "seed.csv")
    staging_path = str(tmp_path / "staging.parquet")
    (tmp_path / "seed.csv").write_text(SEED_CSV_CONTENT)
    empty.write_parquet(staging_path)

    df = build_seed_crosswalk_matches(seed_path, staging_path, con)
    assert len(df) == 0
    assert set(df.columns) == {
        "org_id", "canonical_name", "assignee_id", "display_name",
        "openalex_institution_id", "match_method", "confidence",
    }


# ---------------------------------------------------------------------------
# Production seed CSV sanity checks (no R2 needed)
# ---------------------------------------------------------------------------


def test_production_seed_csv_exists() -> None:
    """The production seed CSV must be committed alongside this test."""
    assert SEED_CSV.exists(), f"seed_crosswalk.csv not found at {SEED_CSV}"


def test_production_seed_csv_has_required_columns() -> None:
    """The production CSV must have exactly the four expected columns."""
    df = pl.read_csv(str(SEED_CSV))
    expected = {"org_id", "canonical_name", "normalized_patentsview", "openalex_institution_id"}
    assert set(df.columns) == expected


def test_production_seed_csv_no_blank_org_id() -> None:
    """Every row must have a non-blank org_id."""
    df = pl.read_csv(str(SEED_CSV))
    assert df["org_id"].is_null().sum() == 0
    assert (df["org_id"].str.len_chars() > 0).all()


def test_production_seed_csv_no_blank_normalized_patentsview() -> None:
    """Every row must have a non-blank normalized_patentsview."""
    df = pl.read_csv(str(SEED_CSV))
    assert df["normalized_patentsview"].is_null().sum() == 0
    assert (df["normalized_patentsview"].str.len_chars() > 0).all()


def test_production_seed_csv_normalized_forms_are_lowercase() -> None:
    """All normalized_patentsview values must already be lowercase (pre-normalized)."""
    df = pl.read_csv(str(SEED_CSV))
    col = df["normalized_patentsview"].drop_nulls()
    assert (col == col.str.to_lowercase()).all(), (
        "Some normalized_patentsview entries contain uppercase characters"
    )
