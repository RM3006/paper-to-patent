"""Data loading layer for the Streamlit UI.

Dev:  reads from the local dev.duckdb warehouse.
Prod: reads from the R2 gold Parquet layer via DuckDB in-memory + httpfs.
      Activated by setting R2_READ_KEY_ID in the environment.
"""

from __future__ import annotations

import os
import pathlib

import duckdb
import polars as pl
import streamlit as st

_LOCAL_DB = pathlib.Path(__file__).parent.parent.parent / "models" / "dev.duckdb"

# Mirrors gold_export._GOLD_MODELS — must stay in sync when new models are added.
_R2_SUBDIRS: dict[str, str] = {
    "dim_cpc": "dims",
    "dim_organization": "dims",
    "dim_paper": "dims",
    "dim_patent": "dims",
    "dim_technology_cluster": "dims",
    "fact_document_cluster": "facts",
    "fact_npl_link": "facts",
    "fact_patent_citation": "facts",
    "fact_patent_filing": "facts",
    "fact_publication": "facts",
    "mart_competitive": "marts",
    "mart_family": "marts",
    "mart_gap": "marts",
    "mart_velocity": "marts",
    "seed_cluster_family": "seeds",
}


def _r2_mode() -> bool:
    return bool(os.environ.get("R2_READ_KEY_ID"))


def _make_r2_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with main_marts.* views pointing at the R2 gold snapshot."""
    account = os.environ["R2_ACCOUNT_ID"]
    key = os.environ["R2_READ_KEY_ID"]
    secret = os.environ["R2_READ_SECRET"]
    bucket = os.environ.get("R2_BUCKET", "p2p-lake")
    snap = os.environ["R2_SNAPSHOT_DATE"]  # e.g. "2026-06-27"

    conn = duckdb.connect()
    conn.execute(f"""
        CREATE OR REPLACE SECRET r2_read (
            TYPE r2,
            ACCOUNT_ID '{account}',
            KEY_ID '{key}',
            SECRET '{secret}'
        )
    """)
    conn.execute("CREATE SCHEMA IF NOT EXISTS main_marts")
    for table, subdir in _R2_SUBDIRS.items():
        path = f"r2://{bucket}/gold/{subdir}/{table}/v{snap}/{table}.parquet"
        conn.execute(f"CREATE VIEW main_marts.{table} AS SELECT * FROM read_parquet('{path}')")
    return conn


def _query(sql: str, params: list[object] | None = None) -> pl.DataFrame:
    if _r2_mode():
        conn = _make_r2_conn()
        try:
            return conn.execute(sql, params or []).pl()
        finally:
            conn.close()
    if not _LOCAL_DB.exists():
        raise FileNotFoundError(
            f"Local DuckDB warehouse not found at {_LOCAL_DB}.\n"
            "Run 'dbt run' from models/ to build it, "
            "or set R2_READ_KEY_ID for production deployment."
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
def load_family_top_orgs() -> pl.DataFrame:
    """Top 3 patenters and top 3 researchers per family (one row per org, ranked).

    Columns: family_id, side ('paper'|'patent'), canonical_name, doc_count, rnk.
    Aggregated from mart_competitive joined to seed_cluster_family; excludes
    'Unresolved' orgs and the c_noise cluster.
    """
    return _query("""
        WITH ranked AS (
            SELECT
                scf.family_id,
                mc.side,
                mc.canonical_name,
                SUM(mc.doc_count) AS doc_count,
                ROW_NUMBER() OVER (
                    PARTITION BY scf.family_id, mc.side
                    ORDER BY SUM(mc.doc_count) DESC
                ) AS rnk
            FROM main_marts.mart_competitive mc
            JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
            WHERE mc.canonical_name != 'Unresolved'
              AND mc.cluster_id != 'c_noise'
              AND mc.side IN ('paper', 'patent')
            GROUP BY scf.family_id, mc.side, mc.canonical_name
        )
        SELECT family_id, side, canonical_name, doc_count, rnk
        FROM ranked
        WHERE rnk <= 3
        ORDER BY family_id, side, rnk
    """)


@st.cache_data(ttl=3600)
def load_cluster_bubble() -> pl.DataFrame:
    """All non-noise clusters with paper/patent counts and citation lag, for the bubble chart."""
    return _query("""
        SELECT
            mg.cluster_id,
            dtc.tagline,
            COALESCE(scf.family_id,   'noise') AS family_id,
            COALESCE(scf.family_name, 'Frontier / Unclustered') AS family_name,
            mg.n_papers,
            mg.n_patents,
            mg.npl_median_lag_years,
            mg.npl_reportable,
            mg.cohort_lag_years
        FROM main_marts.mart_gap mg
        JOIN  main_marts.dim_technology_cluster dtc ON dtc.cluster_id = mg.cluster_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mg.cluster_id
        WHERE mg.cluster_id != 'c_noise'
        ORDER BY mg.n_papers DESC
    """)


@st.cache_data(ttl=3600)
def load_umap_points() -> pl.DataFrame:
    """All ~196k papers+patents with UMAP coords, cluster, family, and year."""
    return _query("""
        SELECT
            fdc.doc_id,
            fdc.doc_type,
            fdc.umap_x,
            fdc.umap_y,
            fdc.cluster_id,
            dtc.tagline,
            COALESCE(scf.family_id,   'noise')                   AS family_id,
            COALESCE(scf.family_name, 'Frontier / Unclustered')  AS family_name,
            COALESCE(
                dp.publication_year,
                YEAR(dp2.filing_date)
            )::INTEGER                                            AS year
        FROM main_marts.fact_document_cluster   fdc
        JOIN  main_marts.dim_technology_cluster dtc  ON dtc.cluster_id  = fdc.cluster_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id  = fdc.cluster_id
        LEFT JOIN main_marts.dim_paper  dp           ON dp.work_id      = fdc.doc_id
                                                     AND fdc.doc_type   = 'paper'
        LEFT JOIN main_marts.dim_patent dp2          ON dp2.patent_id   = fdc.doc_id
                                                     AND fdc.doc_type   = 'patent'
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
def load_cluster_card(cluster_id: str) -> pl.DataFrame:
    """Mini-card data for a single cluster: tagline, summary, terms, gap metrics, family, totals."""
    return _query(
        """
        WITH totals AS (
            SELECT SUM(n_patents) AS total_patents, SUM(n_papers) AS total_papers
            FROM main_marts.mart_gap
            WHERE cluster_id != 'c_noise'
        ),
        family_totals AS (
            SELECT scf.family_id, SUM(mg.n_patents) AS family_patents
            FROM main_marts.mart_gap mg
            JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mg.cluster_id
            WHERE mg.cluster_id != 'c_noise'
            GROUP BY scf.family_id
        )
        SELECT
            dtc.cluster_id,
            dtc.tagline,
            dtc.summary_friendly,
            dtc.top_terms,
            mg.n_papers,
            mg.n_patents,
            mg.npl_median_lag_years,
            mg.npl_reportable,
            mg.cohort_lag_years,
            scf.family_id,
            scf.family_name,
            t.total_patents,
            t.total_papers,
            ft.family_patents
        FROM main_marts.dim_technology_cluster dtc
        LEFT JOIN main_marts.mart_gap            mg  ON mg.cluster_id  = dtc.cluster_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = dtc.cluster_id
        CROSS JOIN totals t
        LEFT JOIN family_totals ft ON ft.family_id = scf.family_id
        WHERE dtc.cluster_id = ?
        """,
        [cluster_id],
    )


@st.cache_data(ttl=3600)
def load_family_velocity(family_id: str) -> pl.DataFrame:
    """Annual paper and patent counts for a family (mart_velocity rolled up).

    One row per year; paper_count and patent_count summed across the family's
    non-noise clusters. Patents are counted by FILING year and undercount the most
    recent years because PatentsView holds granted patents only and recent filings
    are still in the grant pipeline — the UI fades those trailing years.
    Source: mart_velocity + seed_cluster_family. Output: R2 gold / dev.duckdb.
    """
    return _query(
        """
        SELECT mv.year,
               SUM(mv.paper_count)  AS paper_count,
               SUM(mv.patent_count) AS patent_count
        FROM main_marts.mart_velocity mv
        JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mv.cluster_id
        WHERE scf.family_id = ? AND mv.cluster_id != 'c_noise'
        GROUP BY mv.year
        ORDER BY mv.year
        """,
        [family_id],
    )


@st.cache_data(ttl=3600)
def load_family_org_leaderboard(family_id: str, side: str, top_n: int = 50) -> pl.DataFrame:
    """Top orgs for a family by side ('paper'|'patent'), with total distinct org count.

    Returns top_n rows ordered by doc_count DESC.
    Each row carries total_orgs = count of all distinct orgs for this family+side.
    Source: mart_competitive joined to seed_cluster_family; excludes 'Unresolved' and c_noise.
    Output: R2 gold Parquet or local dev.duckdb.
    """
    return _query(
        f"""
        WITH agg AS (
            SELECT mc.org_id, mc.canonical_name, SUM(mc.doc_count) AS doc_count
            FROM main_marts.mart_competitive mc
            JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
            WHERE scf.family_id = ? AND mc.side = ? AND mc.canonical_name != 'Unresolved'
              AND mc.cluster_id != 'c_noise'
            GROUP BY mc.org_id, mc.canonical_name
        ),
        total AS (SELECT COUNT(*) AS total_orgs FROM agg)
        SELECT agg.org_id, agg.canonical_name, agg.doc_count, total.total_orgs
        FROM agg CROSS JOIN total
        ORDER BY agg.doc_count DESC
        LIMIT {top_n}
        """,
        [family_id, side],
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


# ── Trace one idea (Surface 5) ───────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_trace_paper(work_id: str) -> pl.DataFrame:
    """Paper card for trace-one-idea: title, abstract, pub_date, topic, primary org."""
    return _query(
        """
        WITH primary_org AS (
            SELECT DISTINCT ON (fp.work_id) fp.work_id, fp.org_id
            FROM main_marts.fact_publication fp
            WHERE fp.work_id = ?
            ORDER BY fp.work_id, fp.org_id
        )
        SELECT
            dp.title,
            dp.publication_date,
            dp.abstract,
            dp.primary_topic_name,
            dorg.canonical_name AS org_name
        FROM main_marts.dim_paper dp
        LEFT JOIN primary_org po ON po.work_id = dp.work_id
        LEFT JOIN main_marts.dim_organization dorg ON dorg.org_id = po.org_id
        WHERE dp.work_id = ?
        """,
        [work_id, work_id],
    )


@st.cache_data(ttl=3600)
def load_trace_links(work_id: str) -> pl.DataFrame:
    """Citing patents for a paper — one row per patent with primary assignee and lag."""
    return _query(
        """
        WITH npl AS (
            SELECT DISTINCT ON (patent_id)
                patent_id, confidence, citation_lag_years
            FROM main_marts.fact_npl_link
            WHERE work_id = ?
            ORDER BY patent_id,
                CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                citation_lag_years ASC NULLS LAST
        ),
        assignee AS (
            SELECT DISTINCT ON (fpf.patent_id)
                fpf.patent_id, dorg.canonical_name AS assignee
            FROM main_marts.fact_patent_filing fpf
            JOIN main_marts.dim_organization dorg ON dorg.org_id = fpf.org_id
            ORDER BY fpf.patent_id
        )
        SELECT
            n.patent_id,
            n.confidence,
            n.citation_lag_years,
            dp.title AS patent_title,
            dp.filing_date,
            a.assignee
        FROM npl n
        JOIN main_marts.dim_patent dp ON dp.patent_id = n.patent_id
        LEFT JOIN assignee a ON a.patent_id = n.patent_id
        ORDER BY n.citation_lag_years ASC NULLS LAST
        LIMIT 12
        """,
        [work_id],
    )


@st.cache_data(ttl=3600)
def load_org_paper_output_by_family(org_id: str) -> pl.DataFrame:
    """Paper count per technology family for a given org (researcher perspective)."""
    return _query(
        """
        SELECT scf.family_id, scf.family_name, SUM(mc.doc_count) AS n_papers
        FROM main_marts.mart_competitive mc
        JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.side = 'paper'
        GROUP BY scf.family_id, scf.family_name
        ORDER BY n_papers DESC
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_top_research_clusters(org_id: str) -> pl.DataFrame:
    """Top 5 research clusters (excluding c_noise) for a given org — researcher side."""
    return _query(
        """
        SELECT mc.cluster_id, mc.tagline, mc.doc_count, mc.share
        FROM main_marts.mart_competitive mc
        WHERE mc.org_id = ? AND mc.side = 'paper' AND mc.cluster_id != 'c_noise'
        ORDER BY mc.doc_count DESC
        LIMIT 5
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_paper_years(org_id: str) -> pl.DataFrame:
    """Research paper count per publication year for a given org."""
    return _query(
        """
        SELECT YEAR(dp.publication_date) AS year, COUNT(DISTINCT fp.work_id) AS n_papers
        FROM main_marts.fact_publication fp
        JOIN main_marts.dim_paper dp ON dp.work_id = fp.work_id
        WHERE fp.org_id = ?
          AND dp.publication_date IS NOT NULL
        GROUP BY year
        ORDER BY year
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_trace_family_stat(family_id: str) -> pl.DataFrame:
    """Family row for the closing citation-lag stat on the trace page."""
    return _query(
        """
        SELECT family_name, median_lag_years_weighted, n_papers, n_patents, total_npl_links
        FROM main_marts.mart_family
        WHERE family_id = ?
        """,
        [family_id],
    )
