"""Data loading layer for the Streamlit UI. Reads from the local dev DuckDB warehouse."""
from __future__ import annotations

import pathlib

import duckdb
import polars as pl
import streamlit as st

_LOCAL_DB = pathlib.Path(__file__).parent.parent.parent / "models" / "dev.duckdb"


def _query(sql: str, params: list[object] | None = None) -> pl.DataFrame:
    if not _LOCAL_DB.exists():
        raise FileNotFoundError(
            f"Local DuckDB warehouse not found at {_LOCAL_DB}.\n"
            "Run 'dbt run' from models/ to build it, "
            "or configure R2 credentials for production deployment."
        )
    with duckdb.connect(str(_LOCAL_DB), read_only=True) as conn:
        return conn.execute(sql, params or []).pl()


@st.cache_data(ttl=3600)
def load_family_scorecard() -> pl.DataFrame:
    """One row per technology family from mart_family, ordered by family_sort_order."""
    return _query("""
        SELECT
            family_id,
            family_name,
            family_sort_order,
            n_papers,
            n_patents,
            n_clusters,
            patent_share,
            n_research_orgs_sum,
            n_assignees_sum,
            median_lag_years_weighted,
            total_npl_links,
            top_assignee_name,
            top_researcher_name
        FROM main_marts.mart_family
        ORDER BY family_sort_order
    """)


@st.cache_data(ttl=3600)
def load_umap_points() -> pl.DataFrame:
    """All ~196k papers+patents with UMAP coords, cluster tagline, and family mapping."""
    return _query("""
        SELECT
            fdc.doc_type,
            fdc.umap_x,
            fdc.umap_y,
            fdc.cluster_id,
            dtc.tagline,
            COALESCE(scf.family_id,   'noise')                    AS family_id,
            COALESCE(scf.family_name, 'Frontier / Unclustered')   AS family_name
        FROM main_marts.fact_document_cluster   fdc
        JOIN  main_marts.dim_technology_cluster dtc ON dtc.cluster_id = fdc.cluster_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fdc.cluster_id
    """)


@st.cache_data(ttl=3600)
def load_family_clusters(family_id: str) -> pl.DataFrame:
    """Clusters belonging to one family, with gap metrics, for the family-detail page."""
    return _query(
        """
        SELECT
            mg.cluster_id,
            dtc.tagline,
            mg.n_papers,
            mg.n_patents,
            mg.hhi,
            mg.hhi_reportable,
            mg.n_research_orgs,
            mg.n_assignees,
            mg.npl_median_lag_years,
            mg.npl_n_links,
            mg.npl_reportable
        FROM main_marts.mart_gap mg
        JOIN main_marts.dim_technology_cluster dtc ON dtc.cluster_id = mg.cluster_id
        JOIN main_marts.seed_cluster_family scf    ON scf.cluster_id = mg.cluster_id
        WHERE scf.family_id = ?
          AND mg.cluster_id != 'c_noise'
        ORDER BY mg.n_papers + mg.n_patents DESC
        """,
        [family_id],
    )


@st.cache_data(ttl=3600)
def load_top_orgs(cluster_ids: tuple[str, ...], side: str, top_n: int = 10) -> pl.DataFrame:
    """Top orgs by doc_count for the given cluster set and side ('paper'|'patent')."""
    ids_sql = ", ".join(f"'{c}'" for c in cluster_ids)
    return _query(f"""
        SELECT
            canonical_name,
            SUM(doc_count) AS doc_count
        FROM main_marts.mart_competitive
        WHERE cluster_id IN ({ids_sql})
          AND side = '{side}'
          AND canonical_name != 'Unresolved'
        GROUP BY canonical_name
        ORDER BY doc_count DESC
        LIMIT {top_n}
    """)
