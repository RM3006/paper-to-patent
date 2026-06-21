"""Tests for nexus.assets.ingest.patentsview.filter_patents_to_scope."""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl  # noqa: F401 — used in fixture DataFrames
import pytest

from nexus.assets.ingest.patentsview import (
    SCOPE_CPC_PREFIXES,
    SCOPE_FILING_END,
    SCOPE_FILING_START,
    filter_patents_to_scope,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Three patents:
#   P1 — in scope (EUV CPC, valid filing date)
#   P2 — out of scope by CPC (wrong technology family)
#   P3 — out of scope by filing date (too early)

_PATENTS = pl.DataFrame(
    {
        "patent_id": ["P1", "P2", "P3"],
        "patent_title": ["EUV Scanner", "Ski Boot Binding", "Old Lithography"],
        "patent_date": ["2022-01-04", "2022-01-04", "2016-05-10"],
        "patent_type": ["utility", "utility", "utility"],
    }
)

_APPLICATIONS = pl.DataFrame(
    {
        "patent_id": ["P1", "P2", "P3"],
        "filing_date": ["2020-03-15", "2020-03-15", "2012-11-01"],
    }
)

_CPC = pl.DataFrame(
    {
        "patent_id": ["P1", "P1", "P2", "P3"],
        # P1 has two CPC codes, one in scope (G03F7/2004 → prefix G03F7/20)
        "cpc_group": ["G03F7/2004", "G03F7/2023", "A63C9/001", "G03F7/20"],
    }
)


@pytest.fixture
def fixture_parquets(tmp_path: Path) -> tuple[str, str, str]:
    """Write fixture DataFrames to temp Parquet files; return (patents, apps, cpc) paths."""
    patents_path = str(tmp_path / "patents.parquet")
    apps_path = str(tmp_path / "applications.parquet")
    cpc_path = str(tmp_path / "cpc.parquet")
    _PATENTS.write_parquet(patents_path)
    _APPLICATIONS.write_parquet(apps_path)
    _CPC.write_parquet(cpc_path)
    return patents_path, apps_path, cpc_path


# ---------------------------------------------------------------------------
# filter_patents_to_scope — correctness
# ---------------------------------------------------------------------------


def test_scope_cpc_keeps_in_scope_patent(fixture_parquets: tuple[str, str, str]) -> None:
    """P1 (EUV CPC, valid date) must appear in the output."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    assert "P1" in df["patent_id"].to_list()


def test_scope_cpc_excludes_wrong_cpc(fixture_parquets: tuple[str, str, str]) -> None:
    """P2 (non-scope CPC A63C) must be excluded."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    assert "P2" not in df["patent_id"].to_list()


def test_scope_filing_date_excludes_too_early(fixture_parquets: tuple[str, str, str]) -> None:
    """P3 (scope CPC but filing_date < 2014) must be excluded."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    assert "P3" not in df["patent_id"].to_list()


def test_scope_output_row_count(fixture_parquets: tuple[str, str, str]) -> None:
    """Exactly one patent survives the filter in this fixture."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    assert df.shape[0] == 1


def test_scope_output_schema(fixture_parquets: tuple[str, str, str]) -> None:
    """Output has all expected columns."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    expected = {"patent_id", "patent_title", "patent_date", "patent_type", "filing_date"}
    assert set(df.columns) == expected


def test_scope_filing_date_is_preserved(fixture_parquets: tuple[str, str, str]) -> None:
    """The filing_date on the surviving patent comes from g_application, not g_patent."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    ids = df["patent_id"].to_list()
    dates = df["filing_date"].to_list()
    assert dates[ids.index("P1")] == "2020-03-15"


def test_scope_deduplicates_multiple_cpc_rows(fixture_parquets: tuple[str, str, str]) -> None:
    """P1 has two scope CPC rows; the output must still have only one P1 row."""
    patents_path, apps_path, cpc_path = fixture_parquets
    con = duckdb.connect()
    df = filter_patents_to_scope(patents_path, apps_path, cpc_path, con)
    assert df["patent_id"].to_list().count("P1") == 1


# ---------------------------------------------------------------------------
# Scope constants sanity checks
# ---------------------------------------------------------------------------


def test_scope_cpc_prefixes_non_empty() -> None:
    assert len(SCOPE_CPC_PREFIXES) > 0


def test_scope_date_window_ordering() -> None:
    assert SCOPE_FILING_START < SCOPE_FILING_END
