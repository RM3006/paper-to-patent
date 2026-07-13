# pyright: basic
"""Shared fixtures for apps/ui data-layer tests.

Builds a small main_marts-schema DuckDB file standing in for the real
warehouse, and points data.py's local-mode connection (_LOCAL_DB) at it.
"""

from __future__ import annotations

import pathlib

import duckdb
import pytest
import streamlit as st

import data as data_module


@pytest.fixture(autouse=True)
def _clear_streamlit_cache() -> None:
    """st.cache_data is keyed on function name + args, not on the DB behind it.

    Without clearing it, a function called with the same args in an earlier
    test would return that test's fixture data instead of hitting the DB again.
    """
    st.cache_data.clear()


@pytest.fixture
def fixture_db(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a minimal main_marts warehouse covering the functions under test."""
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    db_path = tmp_path / "fixture.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA main_marts")

    con.execute("""
        CREATE TABLE main_marts.mart_family (
            family_id VARCHAR, family_name VARCHAR, family_sort_order INTEGER,
            n_papers BIGINT, n_patents BIGINT,
            patent_share DOUBLE, n_research_orgs_sum BIGINT, n_assignees_sum BIGINT,
            median_lag_years_weighted DOUBLE, total_npl_links BIGINT,
            avg_grant_lag_years DOUBLE
        )
    """)
    con.execute("""
        INSERT INTO main_marts.mart_family VALUES
            ('euv', 'EUV Lithography', 1, 100, 40, 0.40, 20, 10, 3.5, 60, 2.35),
            ('lasers', 'Lasers', 2, 50, 10, 0.17, 8, 4, 4.5, 25, 2.32),
            ('si_photonics', 'Silicon Photonics', 3, 80, 20, 0.25, 15, 8, 4.1, 30, 2.13),
            ('neuromorphic', 'Neuromorphic Computing', 4, 60, 15, 0.20, 12, 6, 3.0, 22, 3.37),
            ('in_memory', 'In-Memory Compute', 5, 70, 18, 0.20, 14, 7, 2.8, 28, 1.84)
    """)

    con.execute("""
        CREATE TABLE main_marts.seed_cluster_family (
            cluster_id VARCHAR, family_id VARCHAR, family_name VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.seed_cluster_family VALUES
            ('c1', 'euv', 'EUV Lithography'),
            ('c2', 'silicon_photonics', 'Silicon Photonics')
    """)

    con.execute("""
        CREATE TABLE main_marts.mart_gap (
            cluster_id VARCHAR, n_papers BIGINT, n_patents BIGINT,
            npl_median_lag_years DOUBLE, npl_reportable BOOLEAN, npl_n_links BIGINT,
            cohort_lag_years DOUBLE, hhi DOUBLE, hhi_reportable BOOLEAN,
            n_research_orgs BIGINT, n_assignees BIGINT
        )
    """)
    con.execute("""
        INSERT INTO main_marts.mart_gap VALUES
            ('c1', 60, 25, 3.2, true, 34, 2.8, 0.35, true, 20, 10),
            ('c2', 40, 15, 4.0, true, 22, 3.5, 0.20, true, 15, 8),
            ('c3', 10, 5, 5.0, true, 21, 4.5, NULL, false, 5, 2),
            ('c_noise', 500, 500, NULL, false, 0, NULL, NULL, false, 200, 150)
    """)

    con.execute("""
        CREATE TABLE main_marts.dim_technology_cluster (
            cluster_id VARCHAR, tagline VARCHAR, summary_friendly VARCHAR,
            top_terms VARCHAR[]
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_technology_cluster VALUES
            ('c1', 'EUV Sources', 'EUV light sources for next-gen lithography.',
             ['euv', 'lithography', 'photoresist']),
            ('c2', 'Photonic Waveguides', 'Silicon waveguides routing light on-chip.',
             ['waveguide', 'silicon photonics', 'modulator']),
            ('c3', 'Unmapped Cluster', 'A small cluster of laser-related work.',
             ['laser', 'diode']),
            ('c_noise', 'Unclustered', '', [])
    """)

    con.execute("""
        CREATE TABLE main_marts.mart_competitive (
            cluster_id VARCHAR, tagline VARCHAR, side VARCHAR, canonical_name VARCHAR,
            doc_count BIGINT, org_id VARCHAR, family_id VARCHAR, family_id_key VARCHAR,
            cluster_total BIGINT, share DOUBLE
        )
    """)
    con.execute("""
        INSERT INTO main_marts.mart_competitive VALUES
            ('c1', 'Test Cluster One', 'patent', 'Org A', 100, 'org_a', 'euv', 'euv', 500, 0.2),
            ('c1', 'Test Cluster One', 'patent', 'Org B', 80, 'org_b', 'euv', 'euv', 500, 0.16),
            ('c1', 'Test Cluster One', 'patent', 'Org C', 60, 'org_c', 'euv', 'euv', 500, 0.12),
            ('c1', 'Test Cluster One', 'patent', 'Org D', 40, 'org_d', 'euv', 'euv', 500, 0.08),
            ('c1', 'Test Cluster One', 'patent', 'Unresolved', 200, 'org_unresolved',
             'euv', 'euv', 500, 0.4),
            ('c1', 'Test Cluster One', 'patent', 'US83920184', 5, 'org_native_frag',
             'euv', 'euv', 500, 0.01),
            ('c1', 'Test Cluster One', 'patent', 'Org A', 15, 'org_a', NULL,
             'unattributed', 500, 0.03),
            ('c_noise', 'Unclustered', 'patent', 'Noise Org', 500, 'org_noise_only',
             'euv', 'euv', 500, 1.0)
    """)

    con.execute("""
        CREATE TABLE main_marts.fact_patent_filing (
            patent_id VARCHAR, org_id VARCHAR, family_id VARCHAR, cluster_id VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.fact_patent_filing VALUES
            ('p1', 'org_a', 'euv', 'c1'),
            ('p2', 'org_b', 'euv', 'c1'),
            ('p3', 'org_a', NULL, 'c1'),
            ('p4', 'org_b', NULL, 'c2'),
            ('p5', 'org_a', 'lasers', 'c3'),
            ('p6', 'org_a', NULL, 'c_noise')
    """)

    con.execute("""
        CREATE TABLE main_marts.fact_publication (
            work_id VARCHAR, org_id VARCHAR, family_id VARCHAR, cluster_id VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.fact_publication VALUES
            ('w1', 'org_a', 'euv', 'c1'),
            ('w2', 'org_a', NULL, 'c1'),
            ('w3', 'org_b', NULL, 'c2'),
            ('w4', 'org_a', NULL, 'c_noise')
    """)

    con.execute("""
        CREATE TABLE main_marts.fact_npl_link (
            patent_id VARCHAR, work_id VARCHAR, citation_lag_years DOUBLE,
            confidence VARCHAR, link_source VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.fact_npl_link VALUES
            ('p1', 'w1', 2.0, 'high',   'marx_fuegi'),
            ('p1', 'w2', 3.0, 'medium', 'fuzzy_title'),
            ('p5', 'w1', 1.2, 'medium', 'fuzzy_title')
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
            ('org_b', 'Org B', 'fuzzy_high', 'high'),
            ('org_native_frag', 'US83920184', 'native_id', 'high'),
            ('org_noise_only', 'Noise Org', 'fuzzy_high', 'medium')
    """)

    con.execute("""
        CREATE TABLE main_marts.dim_paper (
            work_id VARCHAR, title VARCHAR, publication_date DATE,
            abstract VARCHAR, primary_topic_name VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_paper VALUES
            ('w1', 'Test Paper One', DATE '2015-01-01', 'An abstract.', 'Test Topic')
    """)

    con.execute("""
        CREATE TABLE main_marts.dim_patent (
            patent_id VARCHAR, title VARCHAR, filing_date DATE
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_patent VALUES
            ('p1', 'Patent One', DATE '2017-01-01'),
            ('p5', 'Patent Five', DATE '2016-06-01')
    """)

    con.close()
    monkeypatch.setattr(data_module, "_LOCAL_DB", db_path)
