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


def test_compute_grant_lag_cutoff_year_rounds_and_subtracts() -> None:
    # neuromorphic's real avg_grant_lag_years (3.37) rounds to 3.
    assert data_module.compute_grant_lag_cutoff_year(2024, 3.37) == 2021
    # in_memory's (1.84) rounds to 2.
    assert data_module.compute_grant_lag_cutoff_year(2024, 1.84) == 2022


def test_compute_grant_lag_cutoff_year_floors_at_one_year() -> None:
    # Even a near-zero lag still shades at least the most recent year.
    assert data_module.compute_grant_lag_cutoff_year(2024, 0.1) == 2023


def test_compute_grant_lag_cutoff_year_falls_back_when_no_sample() -> None:
    assert data_module.compute_grant_lag_cutoff_year(2024, None) == 2022


def test_load_family_scorecard_orders_by_sort_order(fixture_db: None) -> None:
    df = data_module.load_family_scorecard()
    assert df.columns == [
        "family_id", "family_name", "family_sort_order", "n_papers", "n_patents",
        "patent_share", "n_research_orgs_sum", "n_assignees_sum",
        "median_lag_years_weighted", "total_npl_links",
    ]
    assert df["family_id"].to_list() == [
        "euv", "lasers", "si_photonics", "neuromorphic", "in_memory",
    ]


def test_load_unattributed_counts_counts_distinct_null_family_docs(fixture_db: None) -> None:
    # p3, p4, p6 have NULL family_id (p6 is also unclustered -- the two gaps
    # are independent and can co-occur); w2, w3, w4 likewise on the paper side.
    counts = data_module.load_unattributed_counts()
    assert counts == {"unattributed_patents": 3, "unattributed_papers": 3}


def test_load_unclustered_counts_counts_distinct_c_noise_docs(fixture_db: None) -> None:
    counts = data_module.load_unclustered_counts()
    assert counts == {"unclustered_patents": 1, "unclustered_papers": 1}  # p6; w4


def test_load_dataset_totals_sums_all_families(fixture_db: None) -> None:
    totals = data_module.load_dataset_totals()
    # 100+50+80+60+70 papers; 40+10+20+15+18 patents -- mart_family is now 5-way
    # with no 'mixed' row to exclude (see mart_family rebuild).
    assert totals == {"total_papers": 360, "total_patents": 103}


def test_load_dataset_totals_scoped_by_family(fixture_db: None) -> None:
    # Scoped branch now queries fact_patent_filing/fact_publication directly by
    # their own family_id (COALESCE'd to 'unattributed') -- mart_gap has no family
    # dimension and can't be filtered by a 5-way family_id. euv: p1, p2 patents
    # (p3 is NULL family, excluded); w1 paper (w2 is NULL family, excluded).
    totals = data_module.load_dataset_totals(family_ids=("euv",))
    assert totals == {"total_papers": 1, "total_patents": 2}


def test_load_dataset_totals_scoped_by_unattributed(fixture_db: None) -> None:
    totals = data_module.load_dataset_totals(family_ids=("unattributed",))
    assert totals == {"total_papers": 3, "total_patents": 3}  # w2/w3/w4; p3/p4/p6


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
    # npl_n_links backs the hover tooltip's link-count disclosure (evidence weight
    # behind the lag figure) -- must survive the query alongside the lag itself.
    assert rows["c1"]["npl_n_links"] == 34


def test_load_cluster_card_returns_terms_and_family_totals(fixture_db: None) -> None:
    df = data_module.load_cluster_card("c1")
    row = df.row(0, named=True)
    assert row["tagline"] == "EUV Sources"
    # top_terms grounds the Map cluster card's AI-written tagline/summary in the
    # c-TF-IDF evidence they were generated from -- must survive the query.
    assert row["top_terms"] == ["euv", "lithography", "photoresist"]
    assert row["n_papers"] == 60
    assert row["n_patents"] == 25
    assert row["family_id"] == "euv"
    assert row["total_patents"] == 45   # c1(25) + c2(15) + c3(5), c_noise excluded
    assert row["family_patents"] == 25  # only c1 maps to the euv cluster-label family


def test_load_family_clusters_includes_top_terms(fixture_db: None) -> None:
    df = data_module.load_family_clusters("euv")
    rows = {r["cluster_id"]: r for r in df.to_dicts()}
    # Backs the Family Deepdive cluster table's "Top Terms" column.
    assert rows["c1"]["top_terms"] == ["euv", "lithography", "photoresist"]


def test_load_org_output_by_family_discloses_unattributed_bucket(fixture_db: None) -> None:
    df = data_module.load_org_output_by_family("org_a")
    rows = {r["family_id"]: r["n_patents"] for r in df.to_dicts()}
    assert rows["euv"] == 100          # Org A's euv-family patents in c1
    assert rows["unattributed"] == 15  # Org A's NULL-family patents in c1 -- disclosed, not dropped


def test_load_org_top_patent_clusters_reaggregates_family_slices_before_ranking(
    fixture_db: None,
) -> None:
    # Org A has two mart_competitive rows in c1 (euv=100, unattributed=15) -- the
    # widened grain must sum them into ONE cluster row (115) before ranking, not
    # rank the two slices separately or double-count the cluster.
    df = data_module.load_org_top_patent_clusters("org_a")
    rows = df.to_dicts()
    assert len(rows) == 1
    assert rows[0]["cluster_id"] == "c1"
    assert rows[0]["doc_count"] == 115
    assert rows[0]["family_id"] == "euv"  # cluster's own 3-way label (seed_cluster_family)


def test_load_family_metrics_matches_manual_counts_and_applies_lag_floor(
    fixture_db: None,
) -> None:
    m = data_module.load_family_metrics("euv").row(0, named=True)
    assert m["n_patents"] == 2            # p1, p2 -- p3 is NULL family_id, excluded
    assert m["n_papers"] == 1             # w1 -- w2 is NULL family_id, excluded
    assert m["n_assignees_sum"] == 2      # org_a, org_b (patent side)
    assert m["n_research_orgs_sum"] == 1  # org_a (paper side)
    assert m["total_npl_links"] == 2
    assert m["median_lag_years_weighted"] is None  # 2 links < the 20-link floor
    # patent_share = family n_patents / total n_patents across all families.
    # p1, p2 are euv; p5 is lasers; p3, p4 are NULL family_id (excluded from the
    # denominator) -- so the denominator is 3 (p1, p2, p5) and euv holds 2/3.
    assert m["patent_share"] == 0.667
    assert m["avg_grant_lag_years"] == 2.35  # pulled straight from mart_family.euv


def test_load_family_metrics_scopes_to_cluster_filter(fixture_db: None) -> None:
    m_c1 = data_module.load_family_metrics("euv", cluster_ids=("c1",)).row(0, named=True)
    assert m_c1["n_patents"] == 2  # both euv patents are in c1
    # Numerator narrows to the cluster filter, but the denominator (total
    # patents across all families) stays unscoped -- still 2/3.
    assert m_c1["patent_share"] == 0.667
    # avg_grant_lag_years is family-level only, never narrowed by cluster_ids.
    assert m_c1["avg_grant_lag_years"] == 2.35

    m_c2 = data_module.load_family_metrics("euv", cluster_ids=("c2",)).row(0, named=True)
    assert m_c2["n_patents"] == 0  # c2 has no euv-family patents
    assert m_c2["n_papers"] == 0
    # Numerator is 0, but the denominator is still the unscoped total (3) --
    # 0/3 = 0.0, not NULL.
    assert m_c2["patent_share"] == 0.0


def test_load_family_top_orgs_ranks_top_three_and_excludes_unresolved(fixture_db: None) -> None:
    df = data_module.load_family_top_orgs()
    euv_patent_rows = [
        r for r in df.to_dicts() if r["family_id"] == "euv" and r["side"] == "patent"
    ]
    names = {r["canonical_name"] for r in euv_patent_rows}
    assert names == {"Org A", "Org B", "Org C"}  # Org D is rnk 4, dropped
    assert "Unresolved" not in names
    assert "Noise Org" not in names  # c_noise cluster excluded
    # Org A's euv-attributed doc_count (100) must not be inflated by its separate
    # NULL-family_id row (15) -- that's a different, excluded ("unattributed") bucket.
    org_a_count = next(r["doc_count"] for r in euv_patent_rows if r["canonical_name"] == "Org A")
    assert org_a_count == 100


def test_load_org_profile_returns_match_method_and_confidence(fixture_db: None) -> None:
    row = data_module.load_org_profile("org_a").row(0, named=True)
    assert row["primary_match_method"] == "fuzzy_high"
    assert row["primary_confidence"] == "high"

    row_medium = data_module.load_org_profile("org_noise_only").row(0, named=True)
    assert row_medium["primary_confidence"] == "medium"


def test_load_trace_links_returns_confidence_and_link_source_per_link(fixture_db: None) -> None:
    df = data_module.load_trace_links("w1")
    rows = {r["patent_id"]: r for r in df.to_dicts()}
    assert set(rows) == {"p1", "p5"}
    # p1: gold Marx & Fuegi citation, high confidence.
    assert rows["p1"]["confidence"] == "high"
    assert rows["p1"]["link_source"] == "marx_fuegi"
    # p5: our own fuzzy-title matcher, medium confidence.
    assert rows["p5"]["confidence"] == "medium"
    assert rows["p5"]["link_source"] == "fuzzy_title"
    # Ordered by citation_lag_years ascending: p5 (1.2yr) before p1 (2.0yr).
    assert df["patent_id"].to_list() == ["p5", "p1"]


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
