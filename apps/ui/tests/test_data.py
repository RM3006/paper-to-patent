# pyright: basic
"""Tests for the apps/ui data-loading layer (data.py) against a fixture warehouse.

Not exhaustive over every query function -- a thin layer covering the main
query shapes (plain select+order, aggregation with an exclusion invariant,
join+coalesce+filter, window ranking, ilike search) plus the shared
_query()/_scope_clause() plumbing every function goes through.
"""

from __future__ import annotations

import pathlib

import duckdb
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
    # Unfiltered now counts every distinct patent/paper in fact_patent_filing/
    # fact_publication directly (not mart_family, which excludes 'unattributed'
    # documents) -- p1..p9 (9 patents) and w1..w4 (4 papers), including NULL-family
    # and c_noise rows, so this always matches the numerator basis (mart_competitive
    # incl. 'unattributed') used by the Organisation Profile page's metric cards.
    totals = data_module.load_dataset_totals()
    assert totals == {"total_papers": 4, "total_patents": 9}


def test_load_dataset_totals_scoped_by_family(fixture_db: None) -> None:
    # Scoped branch now queries fact_patent_filing/fact_publication directly by
    # their own family_id (COALESCE'd to 'unattributed') -- mart_gap has no family
    # dimension and can't be filtered by a 5-way family_id. euv: p1, p2, p9 patents
    # (p3 is NULL family, excluded); w1 paper (w2 is NULL family, excluded).
    totals = data_module.load_dataset_totals(family_ids=("euv",))
    assert totals == {"total_papers": 1, "total_patents": 3}


def test_load_dataset_totals_scoped_by_unattributed(fixture_db: None) -> None:
    totals = data_module.load_dataset_totals(family_ids=("unattributed",))
    assert totals == {"total_papers": 3, "total_patents": 3}  # w2/w3/w4; p3/p4/p6


def test_load_cluster_bubble_excludes_noise_and_coalesces_unmapped_cluster(
    fixture_db: None,
) -> None:
    df = data_module.load_cluster_bubble()
    rows = {r["cluster_id"]: r for r in df.to_dicts()}
    assert set(rows) == {"c1", "c2", "c3", "c4"}  # c_noise excluded
    # ORDER BY n_papers DESC: 60>40>10>5
    assert df["cluster_id"].to_list() == ["c1", "c2", "c3", "c4"]
    assert rows["c1"]["family_id"] == "euv"
    assert rows["c2"]["family_id"] == "silicon_photonics"
    assert rows["c3"]["family_id"] == "noise"  # no seed_cluster_family row -> COALESCE fallback
    assert rows["c3"]["family_name"] == "Frontier / Unclustered"
    assert rows["c4"]["family_id"] == "noise"  # likewise, c4 has no seed_cluster_family row
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
    assert row["total_patents"] == 48   # c1(25) + c2(15) + c3(5) + c4(3), c_noise excluded
    assert row["family_patents"] == 25  # only c1 maps to the euv cluster-label family


def test_load_family_clusters_includes_top_terms(fixture_db: None) -> None:
    df = data_module.load_family_clusters("euv")
    rows = {r["cluster_id"]: r for r in df.to_dicts()}
    # Backs the Family Deepdive cluster table's "Top Terms" column.
    assert rows["c1"]["top_terms"] == ["euv", "lithography", "photoresist"]


def test_load_family_clusters_is_existence_based_and_family_scoped(
    fixture_db: None,
) -> None:
    # c4 has a lasers majority (p7, p8) but also carries one euv patent (p9) --
    # existence-based membership means c4 shows up under BOTH pills, each time
    # with only that family's own slice, not the cluster's overall total.
    euv = {r["cluster_id"]: r for r in data_module.load_family_clusters("euv").to_dicts()}
    lasers = {r["cluster_id"]: r for r in data_module.load_family_clusters("lasers").to_dicts()}
    assert set(euv) == {"c1", "c4"}
    assert set(lasers) == {"c3", "c4"}
    # c4 under euv: only p9 counts, not p7/p8 (lasers).
    assert euv["c4"]["n_patents"] == 1
    # c4 under lasers: only p7, p8 count, not p9 (euv).
    assert lasers["c4"]["n_patents"] == 2
    # c1 is untouched by the c4 additions -- still exactly its own euv patents.
    assert euv["c1"]["n_patents"] == 2


def test_load_family_clusters_lists_spillover_families(fixture_db: None) -> None:
    euv = {r["cluster_id"]: r for r in data_module.load_family_clusters("euv").to_dicts()}
    lasers = {r["cluster_id"]: r for r in data_module.load_family_clusters("lasers").to_dicts()}
    # c1 is purely euv (p1, p2; p3 is NULL family_id) -- no other family present.
    assert euv["c1"]["spillover_family_ids"] is None
    # c4 has both lasers (p7, p8) and euv (p9) documents -- each pill's row for
    # c4 must list the OTHER family, not itself.
    assert euv["c4"]["spillover_family_ids"] == ["lasers"]
    assert lasers["c4"]["spillover_family_ids"] == ["euv"]


def test_load_family_clusters_matches_load_family_metrics_when_cluster_selected(
    fixture_db: None,
) -> None:
    # Family Deepdive's contract: selecting a cluster in the sidebar filter must
    # make the top metric cards (load_family_metrics, family+cluster intersection)
    # agree exactly with that cluster's row in the bottom table.
    cluster_row = {
        r["cluster_id"]: r for r in data_module.load_family_clusters("euv").to_dicts()
    }["c4"]
    metrics_row = data_module.load_family_metrics("euv", cluster_ids=("c4",)).row(0, named=True)
    assert cluster_row["n_patents"] == metrics_row["n_patents"]
    assert cluster_row["n_papers"] == metrics_row["n_papers"]


def test_load_org_output_by_family_discloses_unattributed_bucket(fixture_db: None) -> None:
    df = data_module.load_org_output_by_family("org_a")
    rows = {r["family_id"]: r["n_patents"] for r in df.to_dicts()}
    assert rows["euv"] == 100          # Org A's euv-family patents in c1
    assert rows["unattributed"] == 15  # Org A's NULL-family patents in c1 -- disclosed, not dropped


def test_load_org_intake_includes_self_citation(fixture_db: None) -> None:
    # p1 and p5 (org_a's patents) NPL-cite w1 and w2 -- both also org_a's own
    # papers. Self-citation is a real, disclosed signal, not filtered out.
    df = data_module.load_org_intake("org_a")
    rows = df.to_dicts()
    assert len(rows) == 1
    assert rows[0]["paper_org_id"] == "org_a"
    assert rows[0]["n_papers_cited"] == 2  # distinct w1, w2


def test_load_org_influence_includes_self_citation(fixture_db: None) -> None:
    # w1 and w2 (org_a's papers) are NPL-cited by p1 and p5 -- both also org_a's
    # own patents. Symmetric with load_org_intake: self-citation is not excluded.
    df = data_module.load_org_influence("org_a")
    rows = df.to_dicts()
    assert len(rows) == 1
    assert rows[0]["patenter_org_id"] == "org_a"
    assert rows[0]["n_patents"] == 2  # distinct p1, p5


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
    assert m["n_patents"] == 3            # p1, p2, p9 -- p3 is NULL family_id, excluded
    assert m["n_papers"] == 1             # w1 -- w2 is NULL family_id, excluded
    assert m["n_assignees_sum"] == 2      # org_a, org_b (patent side)
    assert m["n_research_orgs_sum"] == 1  # org_a (paper side)
    assert m["total_npl_links"] == 2
    assert m["median_lag_years_weighted"] is None  # 2 links < the 20-link floor
    # patent_share = family n_patents / total n_patents across all families.
    # p1, p2, p9 are euv; p5, p7, p8 are lasers; p3, p4 are NULL family_id
    # (excluded from the denominator) -- so the denominator is 6 and euv holds 3/6.
    assert m["patent_share"] == 0.5
    assert m["avg_grant_lag_years"] == 2.35  # pulled straight from mart_family.euv


def test_load_family_metrics_scopes_to_cluster_filter(fixture_db: None) -> None:
    m_c1 = data_module.load_family_metrics("euv", cluster_ids=("c1",)).row(0, named=True)
    assert m_c1["n_patents"] == 2  # both of c1's euv patents (p1, p2) -- p9 is in c4
    # Numerator narrows to the cluster filter, but the denominator (total
    # patents across all families) stays unscoped -- still 6, so 2/6.
    assert m_c1["patent_share"] == 0.333
    # avg_grant_lag_years is family-level only, never narrowed by cluster_ids.
    assert m_c1["avg_grant_lag_years"] == 2.35

    m_c2 = data_module.load_family_metrics("euv", cluster_ids=("c2",)).row(0, named=True)
    assert m_c2["n_patents"] == 0  # c2 has no euv-family patents
    assert m_c2["n_papers"] == 0
    # Numerator is 0, but the denominator is still the unscoped total (6) --
    # 0/6 = 0.0, not NULL.
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


def test_load_trace_links_concatenates_all_assignees(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """A multi-assignee patent shows every co-assignee (sequence-ordered), not
    just one arbitrarily picked -- kept isolated from fixture_db since it would
    otherwise change patent counts relied on by other tests (e.g. dataset totals).
    """
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    db_path = tmp_path / "fixture.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA main_marts")
    con.execute("""
        CREATE TABLE main_marts.dim_paper (
            work_id VARCHAR, title VARCHAR, publication_date DATE,
            abstract VARCHAR, primary_topic_name VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_paper VALUES
            ('w1', 'Test Paper', DATE '2015-01-01', 'An abstract.', 'Test Topic')
    """)
    con.execute("""
        CREATE TABLE main_marts.dim_patent (
            patent_id VARCHAR, title VARCHAR, filing_date DATE
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_patent VALUES ('p1', 'Patent One', DATE '2017-01-01')
    """)
    con.execute("""
        CREATE TABLE main_marts.fact_patent_filing (
            patent_id VARCHAR, org_id VARCHAR, family_id VARCHAR, cluster_id VARCHAR,
            assignee_sequence INTEGER
        )
    """)
    # Inserted out of sequence order -- STRING_AGG must sort by assignee_sequence,
    # not insertion order.
    con.execute("""
        INSERT INTO main_marts.fact_patent_filing VALUES
            ('p1', 'org_b', 'euv', 'c1', 1),
            ('p1', 'org_a', 'euv', 'c1', 0)
    """)
    con.execute("""
        CREATE TABLE main_marts.dim_organization (
            org_id VARCHAR, canonical_name VARCHAR, primary_match_method VARCHAR,
            primary_confidence VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_organization VALUES
            ('org_a', 'Org A', 'fuzzy_high', 'high'),
            ('org_b', 'Org B', 'fuzzy_high', 'high')
    """)
    con.execute("""
        CREATE TABLE main_marts.fact_npl_link (
            patent_id VARCHAR, work_id VARCHAR, citation_lag_years DOUBLE,
            confidence VARCHAR, link_source VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.fact_npl_link VALUES ('p1', 'w1', 2.0, 'high', 'marx_fuegi')
    """)
    con.close()
    monkeypatch.setattr(data_module, "_LOCAL_DB", db_path)

    row = data_module.load_trace_links("w1").row(0, named=True)
    assert row["assignee"] == "Org A, Org B"


def test_load_trace_paper_org_name_reflects_true_affiliation_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """org_name is NULL (not a fabricated 'Multiple institutions') when a paper has
    zero resolved organisations, and lists every org (comma-joined) when it has several
    -- kept isolated from fixture_db, which only models the single-org case.
    """
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    db_path = tmp_path / "fixture.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA main_marts")
    con.execute("""
        CREATE TABLE main_marts.dim_paper (
            work_id VARCHAR, title VARCHAR, publication_date DATE,
            abstract VARCHAR, primary_topic_name VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_paper VALUES
            ('w_none', 'No-Org Paper', DATE '2015-01-01', 'An abstract.', 'Test Topic'),
            ('w_multi', 'Multi-Org Paper', DATE '2016-01-01', 'An abstract.', 'Test Topic')
    """)
    con.execute("""
        CREATE TABLE main_marts.dim_organization (
            org_id VARCHAR, canonical_name VARCHAR, primary_match_method VARCHAR,
            primary_confidence VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_organization VALUES
            ('org_a', 'Org A', 'fuzzy_high', 'high'),
            ('org_b', 'Org B', 'fuzzy_high', 'high')
    """)
    con.execute("""
        CREATE TABLE main_marts.fact_publication (
            work_id VARCHAR, org_id VARCHAR, family_id VARCHAR, cluster_id VARCHAR
        )
    """)
    # Inserted out of order -- STRING_AGG must sort by canonical_name, not insertion order.
    con.execute("""
        INSERT INTO main_marts.fact_publication VALUES
            ('w_multi', 'org_b', 'euv', 'c1'),
            ('w_multi', 'org_a', 'euv', 'c1')
    """)
    con.close()
    monkeypatch.setattr(data_module, "_LOCAL_DB", db_path)

    no_org = data_module.load_trace_paper("w_none").row(0, named=True)
    assert no_org["org_name"] is None

    multi_org = data_module.load_trace_paper("w_multi").row(0, named=True)
    assert multi_org["org_name"] == "Org A, Org B"


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
