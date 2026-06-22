"""Tests for nexus.assets.entity_resolution.crosswalk staging functions."""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pytest

from nexus.assets.entity_resolution.crosswalk import (
    build_openalex_institutions_staging,
    build_patentsview_orgs_staging,
)

_Con = duckdb.DuckDBPyConnection

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
# Scope patents: P1, P2, P3 (P5 is NOT in the scope corpus).
#
# Assignees:
#   A001  "NVIDIA Corporation"  type 2  on P1 and P2 → included once (dedup)
#   A002  "ASML Holding N.V."   type 3  on P1        → included
#   A003  NULL display_name     type 2  on P1        → excluded (null name)
#   A004  "Jane Doe"            type 4  on P3        → excluded (individual)
#   A005  "Company X Inc"       type 2  on P5        → excluded (P5 not in scope)
#   A006  "Qualcomm Inc"        type 2  on P3        → included
#   A007  "US Dept of Defense"  type 6  on P3        → included (government org)

_SCOPED = pl.DataFrame(
    {
        "patent_id": ["P1", "P2", "P3"],
        "patent_title": ["EUV Scanner", "EUV Mask", "Neuromorphic Chip"],
        "filing_date": ["2020-01-01", "2021-01-01", "2022-01-01"],
    }
)

_ASSIGNEES = pl.DataFrame(
    {
        "patent_id": ["P1", "P2", "P1", "P1", "P3", "P5", "P3", "P3"],
        "assignee_id": ["A001", "A001", "A002", "A003", "A004", "A005", "A006", "A007"],
        "disambig_assignee_organization": [
            "NVIDIA Corporation",
            "NVIDIA Corporation",
            "ASML Holding N.V.",
            None,
            None,        # individual — no org name
            "Company X Inc",
            "Qualcomm Inc",
            "US Dept of Defense",
        ],
        "assignee_type": ["2", "2", "3", "2", "4", "2", "2", "6"],
    }
)


@pytest.fixture
def fixture_parquets(tmp_path: Path) -> tuple[str, str]:
    """Write fixture DataFrames to temp Parquet; return (assignees_path, scoped_path)."""
    assignees_path = str(tmp_path / "assignees.parquet")
    scoped_path = str(tmp_path / "scoped.parquet")
    _ASSIGNEES.write_parquet(assignees_path)
    _SCOPED.write_parquet(scoped_path)
    return assignees_path, scoped_path


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


# ---------------------------------------------------------------------------
# Inclusion / exclusion
# ---------------------------------------------------------------------------


def test_org_types_included(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """Assignees with type 2, 3, 6 and scoped patents are included."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    ids = set(df["assignee_id"].to_list())
    assert "A001" in ids  # type 2, US company
    assert "A002" in ids  # type 3, foreign company
    assert "A006" in ids  # type 2
    assert "A007" in ids  # type 6, government


def test_individual_excluded(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """Assignee A004 (type 4, individual) must not appear."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert "A004" not in df["assignee_id"].to_list()


def test_null_org_name_excluded(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """A003 has NULL disambig_assignee_organization and must be excluded."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert "A003" not in df["assignee_id"].to_list()


def test_out_of_scope_patent_excluded(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """A005 is only on P5, which is not in the scope corpus — must be excluded."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert "A005" not in df["assignee_id"].to_list()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_deduplication_one_row_per_assignee(
    fixture_parquets: tuple[str, str], con: _Con
) -> None:
    """A001 appears on both P1 and P2 (both scoped) — must produce exactly one row."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert df["assignee_id"].to_list().count("A001") == 1


def test_total_row_count(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """Four eligible distinct assignees: A001, A002, A006, A007."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert len(df) == 4


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def test_display_name_preserved_raw(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """display_name carries the original raw string from the source."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    row = df.filter(pl.col("assignee_id") == "A001")  # type: ignore[reportUnknownMemberType]
    assert row["display_name"][0] == "NVIDIA Corporation"


def test_normalized_name_nvidia(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """'NVIDIA Corporation' must normalize to 'nvidia'."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    row = df.filter(pl.col("assignee_id") == "A001")  # type: ignore[reportUnknownMemberType]
    assert row["normalized_name"][0] == "nvidia"


def test_normalized_name_asml(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """'ASML Holding N.V.' must normalize to 'asml'."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    row = df.filter(pl.col("assignee_id") == "A002")  # type: ignore[reportUnknownMemberType]
    assert row["normalized_name"][0] == "asml"


def test_normalized_name_qualcomm(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """'Qualcomm Inc' must normalize to 'qualcomm'."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    row = df.filter(pl.col("assignee_id") == "A006")  # type: ignore[reportUnknownMemberType]
    assert row["normalized_name"][0] == "qualcomm"


# ---------------------------------------------------------------------------
# Provenance tags
# ---------------------------------------------------------------------------


def test_match_method_is_native_id(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """Every row must have match_method='native_id'."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert (df["match_method"] == "native_id").all()


def test_confidence_is_high(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """Every row must have confidence='high'."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert (df["confidence"] == "high").all()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_output_schema(fixture_parquets: tuple[str, str], con: _Con) -> None:
    """Output must have exactly the five expected columns."""
    assignees_path, scoped_path = fixture_parquets
    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    expected = {"assignee_id", "display_name", "normalized_name", "match_method", "confidence"}
    assert set(df.columns) == expected


# ---------------------------------------------------------------------------
# Edge case — empty scope / no matching rows
# ---------------------------------------------------------------------------


def test_empty_scope_returns_empty_dataframe(tmp_path: Path, con: _Con) -> None:
    """If no assignees join to scoped patents, return an empty DataFrame with correct schema."""
    empty_scoped = pl.DataFrame(
        {"patent_id": pl.Series([], dtype=pl.String), "filing_date": pl.Series([], dtype=pl.String)}
    )
    assignees_path = str(tmp_path / "assignees.parquet")
    scoped_path = str(tmp_path / "empty_scoped.parquet")
    _ASSIGNEES.write_parquet(assignees_path)
    empty_scoped.write_parquet(scoped_path)

    df = build_patentsview_orgs_staging(assignees_path, scoped_path, con)
    assert len(df) == 0
    expected = {"assignee_id", "display_name", "normalized_name", "match_method", "confidence"}
    assert set(df.columns) == expected


# ===========================================================================
# OpenAlex institutions staging tests
# ===========================================================================
#
# Fixture works:
#   W1: two institutions — MIT (I001) and Stanford (I002)
#   W2: MIT again (I001) — duplicate, must deduplicate
#   W3: no institutions (empty lists)
#
# Expected distinct institutions: I001 (MIT), I002 (Stanford)

_OA_WORKS = pl.DataFrame(
    {
        "institution_ids": [
            ["https://openalex.org/I001", "https://openalex.org/I002"],
            ["https://openalex.org/I001"],
            [],
        ],
        "institution_display_names": [
            ["Massachusetts Institute of Technology", "Stanford University"],
            ["Massachusetts Institute of Technology"],
            [],
        ],
    }
)


@pytest.fixture
def oa_works_path(tmp_path: Path) -> str:
    path = str(tmp_path / "works.parquet")
    _OA_WORKS.write_parquet(path)
    return path


def test_oa_distinct_institution_count(oa_works_path: str, con: _Con) -> None:
    """Two distinct institution_ids across three works → two output rows."""
    df = build_openalex_institutions_staging(oa_works_path, con)
    assert len(df) == 2


def test_oa_deduplication(oa_works_path: str, con: _Con) -> None:
    """I001 appears in W1 and W2 — must produce exactly one output row."""
    df = build_openalex_institutions_staging(oa_works_path, con)
    assert df["institution_id"].to_list().count("https://openalex.org/I001") == 1


def test_oa_display_name_preserved(oa_works_path: str, con: _Con) -> None:
    """display_name carries the raw OpenAlex form for each institution."""
    df = build_openalex_institutions_staging(oa_works_path, con)
    row = df.filter(  # type: ignore[reportUnknownMemberType]
        pl.col("institution_id") == "https://openalex.org/I002"
    )
    assert row["display_name"][0] == "Stanford University"


def test_oa_normalized_mit(oa_works_path: str, con: _Con) -> None:
    """'Massachusetts Institute of Technology' normalises correctly."""
    df = build_openalex_institutions_staging(oa_works_path, con)
    row = df.filter(  # type: ignore[reportUnknownMemberType]
        pl.col("institution_id") == "https://openalex.org/I001"
    )
    assert row["normalized_name"][0] == "massachusetts institute of technology"


def test_oa_normalized_stanford(oa_works_path: str, con: _Con) -> None:
    """'Stanford University' normalises to 'stanford university'."""
    df = build_openalex_institutions_staging(oa_works_path, con)
    row = df.filter(  # type: ignore[reportUnknownMemberType]
        pl.col("institution_id") == "https://openalex.org/I002"
    )
    assert row["normalized_name"][0] == "stanford university"


def test_oa_match_method_is_ror(oa_works_path: str, con: _Con) -> None:
    df = build_openalex_institutions_staging(oa_works_path, con)
    assert (df["match_method"] == "ror").all()


def test_oa_confidence_is_high(oa_works_path: str, con: _Con) -> None:
    df = build_openalex_institutions_staging(oa_works_path, con)
    assert (df["confidence"] == "high").all()


def test_oa_output_schema(oa_works_path: str, con: _Con) -> None:
    df = build_openalex_institutions_staging(oa_works_path, con)
    expected = {"institution_id", "display_name", "normalized_name", "match_method", "confidence"}
    assert set(df.columns) == expected


def test_oa_empty_works_returns_empty_df(tmp_path: Path, con: _Con) -> None:
    """Works Parquet with no institutions → empty DataFrame with correct schema."""
    empty = pl.DataFrame(
        schema={
            "institution_ids": pl.List(pl.String),
            "institution_display_names": pl.List(pl.String),
        }
    )
    path = str(tmp_path / "empty.parquet")
    empty.write_parquet(path)
    df = build_openalex_institutions_staging(path, con)
    assert len(df) == 0
    expected = {"institution_id", "display_name", "normalized_name", "match_method", "confidence"}
    assert set(df.columns) == expected
