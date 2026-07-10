# pyright: basic
"""Tests for the apps/ui data-loading layer (data.py) against a fixture warehouse.

Not exhaustive over every query function -- a thin layer covering the main
query shapes (plain select+order, aggregation with an exclusion invariant,
join+coalesce+filter, window ranking, ilike search) plus the shared
_query()/_scope_clause() plumbing every function goes through.
"""

from __future__ import annotations

import pathlib

import pytest

import data as data_module


def test_scope_clause_no_restriction() -> None:
    assert data_module._scope_clause("scf.family_id", "mc.cluster_id", None, None) == ""
    assert data_module._scope_clause("scf.family_id", "mc.cluster_id", (), ()) == ""


def test_scope_clause_family_only() -> None:
    clause = data_module._scope_clause("scf.family_id", "mc.cluster_id", ("euv", "sp"), None)
    assert clause == " AND scf.family_id IN ('euv', 'sp')"


def test_scope_clause_family_and_cluster() -> None:
    clause = data_module._scope_clause("scf.family_id", "mc.cluster_id", ("euv",), ("c1",))
    assert clause == " AND scf.family_id IN ('euv') AND mc.cluster_id IN ('c1')"


def test_load_family_scorecard_orders_by_sort_order(fixture_db: None) -> None:
    df = data_module.load_family_scorecard()
    assert df.columns == [
        "family_id", "family_name", "family_sort_order", "n_papers", "n_patents",
        "n_clusters", "patent_share", "n_research_orgs_sum", "n_assignees_sum",
        "median_lag_years_weighted", "total_npl_links", "top_assignee_name",
        "top_researcher_name",
    ]
    assert df["family_id"].to_list() == ["euv", "silicon_photonics", "mixed"]


def test_load_dataset_totals_excludes_mixed_family(fixture_db: None) -> None:
    totals = data_module.load_dataset_totals()
    assert totals == {"total_papers": 180, "total_patents": 60}  # 100+80; mixed's 999 excluded


def test_load_dataset_totals_scoped_by_family(fixture_db: None) -> None:
    totals = data_module.load_dataset_totals(family_ids=("euv",))
    assert totals == {"total_papers": 60, "total_patents": 25}  # only c1: c2/c_noise excluded


def test_load_cluster_bubble_excludes_noise_and_coalesces_unmapped_cluster(
    fixture_db: None,
) -> None:
    df = data_module.load_cluster_bubble()
    rows = {r["cluster_id"]: r for r in df.to_dicts()}
    assert set(rows) == {"c1", "c2", "c3"}  # c_noise excluded
    assert df["cluster_id"].to_list() == ["c1", "c2", "c3"]  # ORDER BY n_papers DESC: 60>40>10
    assert rows["c1"]["family_id"] == "euv"
    assert rows["c2"]["family_id"] == "silicon_photonics"
    assert rows["c3"]["family_id"] == "noise"  # no seed_cluster_family row -> COALESCE fallback
    assert rows["c3"]["family_name"] == "Frontier / Unclustered"


def test_load_family_top_orgs_ranks_top_three_and_excludes_unresolved(fixture_db: None) -> None:
    df = data_module.load_family_top_orgs()
    names = df["canonical_name"].to_list()
    assert set(names) == {"Org A", "Org B", "Org C"}  # Org D is rnk 4, dropped
    assert "Unresolved" not in names
    assert "Noise Org" not in names  # c_noise cluster has no seed_cluster_family row


def test_search_orgs_ilike_short_query_returns_default_active_list(fixture_db: None) -> None:
    results = data_module.search_orgs_ilike("")
    assert results == [("Org A", "org_a"), ("Org B", "org_b")]
    # excluded: org_native_frag (native_id match method), org_noise_only (only active on c_noise)


def test_search_orgs_ilike_filters_by_substring(fixture_db: None) -> None:
    results = data_module.search_orgs_ilike("Org A")
    assert results == [("Org A", "org_a")]


def test_query_missing_local_db_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.setattr(data_module, "_LOCAL_DB", tmp_path / "missing.duckdb")
    with pytest.raises(FileNotFoundError):
        data_module.load_family_scorecard()
