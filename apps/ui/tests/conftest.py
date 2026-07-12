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
            n_papers BIGINT, n_patents BIGINT, n_clusters BIGINT,
            patent_share DOUBLE, n_research_orgs_sum BIGINT, n_assignees_sum BIGINT,
            median_lag_years_weighted DOUBLE, total_npl_links BIGINT,
            top_assignee_name VARCHAR, top_researcher_name VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.mart_family VALUES
            ('mixed', 'Mixed', 4, 999, 999, 3, 0.99, 5, 5, 1.0, 10, 'ZZZ', 'ZZZ'),
            ('silicon_photonics', 'Silicon Photonics', 2, 80, 20, 4, 0.25,
                15, 8, 4.1, 30, 'Intel', 'Stanford'),
            ('euv', 'EUV Lithography', 1, 100, 40, 5, 0.40, 20, 10, 3.5, 60, 'ASML', 'MIT')
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
            npl_median_lag_years DOUBLE, npl_reportable BOOLEAN, cohort_lag_years DOUBLE
        )
    """)
    con.execute("""
        INSERT INTO main_marts.mart_gap VALUES
            ('c1', 60, 25, 3.2, true, 2.8),
            ('c2', 40, 15, 4.0, true, 3.5),
            ('c3', 10, 5, 5.0, true, 4.5),
            ('c_noise', 500, 500, NULL, false, NULL)
    """)

    con.execute("""
        CREATE TABLE main_marts.dim_technology_cluster (cluster_id VARCHAR, tagline VARCHAR)
    """)
    con.execute("""
        INSERT INTO main_marts.dim_technology_cluster VALUES
            ('c1', 'EUV Sources'),
            ('c2', 'Photonic Waveguides'),
            ('c3', 'Unmapped Cluster'),
            ('c_noise', 'Unclustered')
    """)

    con.execute("""
        CREATE TABLE main_marts.mart_competitive (
            cluster_id VARCHAR, side VARCHAR, canonical_name VARCHAR,
            doc_count BIGINT, org_id VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.mart_competitive VALUES
            ('c1', 'patent', 'Org A', 100, 'org_a'),
            ('c1', 'patent', 'Org B', 80, 'org_b'),
            ('c1', 'patent', 'Org C', 60, 'org_c'),
            ('c1', 'patent', 'Org D', 40, 'org_d'),
            ('c1', 'patent', 'Unresolved', 200, 'org_unresolved'),
            ('c1', 'patent', 'US83920184', 5, 'org_native_frag'),
            ('c_noise', 'patent', 'Noise Org', 500, 'org_noise_only')
    """)

    con.execute("""
        CREATE TABLE main_marts.dim_organization (
            org_id VARCHAR, canonical_name VARCHAR, primary_match_method VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO main_marts.dim_organization VALUES
            ('org_a', 'Org A', 'fuzzy_high'),
            ('org_b', 'Org B', 'fuzzy_high'),
            ('org_native_frag', 'US83920184', 'native_id'),
            ('org_noise_only', 'Noise Org', 'fuzzy_high')
    """)

    con.close()
    monkeypatch.setattr(data_module, "_LOCAL_DB", db_path)
