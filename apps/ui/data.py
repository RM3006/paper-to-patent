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
            org_id,
            canonical_name,
            SUM(doc_count) AS doc_count
        FROM main_marts.mart_competitive
        WHERE cluster_id IN ({ids_sql})
          AND side = '{side}'
          AND canonical_name != 'Unresolved'
        GROUP BY org_id, canonical_name
        ORDER BY doc_count DESC
        LIMIT {top_n}
    """)


# ── Org profile (Surface 3) ──────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def search_orgs(query: str, top_n: int = 8) -> pl.DataFrame:
    """Fuzzy + substring search against dim_organization.canonical_name."""
    if len(query) < 2:
        return pl.DataFrame(
            schema={
                "org_id": pl.Utf8,
                "canonical_name": pl.Utf8,
                "primary_match_method": pl.Utf8,
                "primary_confidence": pl.Utf8,
            }
        )
    pattern = f"%{query}%"
    return _query(
        f"""
        WITH scored AS (
            SELECT org_id, canonical_name, primary_match_method, primary_confidence,
                   jaro_winkler_similarity(LOWER(canonical_name), LOWER(?)) AS score
            FROM main_marts.dim_organization
        )
        SELECT org_id, canonical_name, primary_match_method, primary_confidence, score
        FROM scored
        WHERE score > 0.6 OR canonical_name ILIKE ?
        ORDER BY
            CASE WHEN canonical_name ILIKE ? THEN 1 ELSE 0 END DESC,
            score DESC
        LIMIT {top_n}
        """,
        [query, pattern, pattern],
    )


@st.cache_data(ttl=3600)
def load_org_profile(org_id: str) -> pl.DataFrame:
    """Single-row org card data from dim_organization."""
    return _query(
        """
        SELECT org_id, canonical_name, primary_match_method, primary_confidence
        FROM main_marts.dim_organization
        WHERE org_id = ?
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_output_by_family(org_id: str) -> pl.DataFrame:
    """Patent count per technology family for a given org (patenter perspective)."""
    return _query(
        """
        SELECT scf.family_id, scf.family_name, SUM(mc.doc_count) AS n_patents
        FROM main_marts.mart_competitive mc
        JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.side = 'patent'
        GROUP BY scf.family_id, scf.family_name
        ORDER BY n_patents DESC
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_top_patent_clusters(org_id: str) -> pl.DataFrame:
    """Top 5 patent clusters (excluding c_noise) for a given patenter org."""
    return _query(
        """
        SELECT mc.cluster_id, mc.tagline, mc.doc_count, mc.share
        FROM main_marts.mart_competitive mc
        WHERE mc.org_id = ? AND mc.side = 'patent' AND mc.cluster_id != 'c_noise'
        ORDER BY mc.doc_count DESC
        LIMIT 5
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_filing_years(org_id: str) -> pl.DataFrame:
    """Patent filing count per year for a given org (from fact_patent_filing)."""
    return _query(
        """
        SELECT YEAR(filing_date) AS year, COUNT(DISTINCT patent_id) AS n_patents
        FROM main_marts.fact_patent_filing
        WHERE org_id = ?
        GROUP BY year
        ORDER BY year
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_intake(org_id: str) -> pl.DataFrame:
    """Research orgs whose papers are cited by this org's patents (via NPL links)."""
    return _query(
        """
        SELECT
            fp.org_id AS paper_org_id,
            do2.canonical_name AS paper_org_name,
            COUNT(DISTINCT fnl.work_id) AS n_papers_cited
        FROM main_marts.fact_patent_filing fpf
        JOIN main_marts.fact_npl_link fnl ON fnl.patent_id = fpf.patent_id
        JOIN main_marts.fact_publication fp ON fp.work_id = fnl.work_id
        JOIN main_marts.dim_organization do2 ON do2.org_id = fp.org_id
        WHERE fpf.org_id = ?
        GROUP BY fp.org_id, do2.canonical_name
        ORDER BY n_papers_cited DESC
        LIMIT 10
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_influence(org_id: str) -> pl.DataFrame:
    """Patenters whose filed patents cite this org's research papers (via NPL links)."""
    return _query(
        """
        SELECT
            fpf.org_id AS patenter_org_id,
            do2.canonical_name AS patenter_name,
            COUNT(DISTINCT fnl.patent_id) AS n_patents
        FROM main_marts.fact_publication fp
        JOIN main_marts.fact_npl_link fnl ON fnl.work_id = fp.work_id
        JOIN main_marts.fact_patent_filing fpf ON fpf.patent_id = fnl.patent_id
        JOIN main_marts.dim_organization do2 ON do2.org_id = fpf.org_id
        WHERE fp.org_id = ?
          AND fpf.org_id != ?
        GROUP BY fpf.org_id, do2.canonical_name
        ORDER BY n_patents DESC
        LIMIT 10
        """,
        [org_id, org_id],
    )


@st.cache_data(ttl=3600)
def load_org_flagship_paper(org_id: str) -> pl.DataFrame:
    """Single most-cited paper (by patents) for a given research org."""
    return _query(
        """
        SELECT
            fp.work_id,
            dp.title,
            dp.publication_date,
            dp.abstract,
            COUNT(DISTINCT fnl.patent_id) AS n_citing_patents
        FROM main_marts.fact_publication fp
        JOIN main_marts.fact_npl_link fnl ON fnl.work_id = fp.work_id
        JOIN main_marts.dim_paper dp ON dp.work_id = fp.work_id
        WHERE fp.org_id = ?
        GROUP BY fp.work_id, dp.title, dp.publication_date, dp.abstract
        ORDER BY n_citing_patents DESC
        LIMIT 1
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_flagship_patent(org_id: str) -> pl.DataFrame:
    """Single patent with most NPL paper citations for a given patenter org."""
    return _query(
        """
        SELECT
            fpf.patent_id,
            dp.title,
            fpf.filing_date,
            COUNT(DISTINCT fnl.work_id) AS n_papers_cited
        FROM main_marts.fact_patent_filing fpf
        JOIN main_marts.dim_patent dp ON dp.patent_id = fpf.patent_id
        JOIN main_marts.fact_npl_link fnl ON fnl.patent_id = fpf.patent_id
        WHERE fpf.org_id = ?
        GROUP BY fpf.patent_id, dp.title, fpf.filing_date
        ORDER BY n_papers_cited DESC
        LIMIT 1
        """,
        [org_id],
    )
