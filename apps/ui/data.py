# pyright: basic
"""Data loading layer for the Streamlit UI.

Dev:  reads from the local dev.duckdb warehouse.
Prod: reads from the MotherDuck warehouse (md:<MOTHERDUCK_DATABASE>).
      Activated by setting MOTHERDUCK_TOKEN in the environment.
"""

from __future__ import annotations

import os
import pathlib

import duckdb
import polars as pl
import streamlit as st

_LOCAL_DB = pathlib.Path(__file__).parent.parent.parent / "models" / "dev.duckdb"


def _md_mode() -> bool:
    return bool(os.environ.get("MOTHERDUCK_TOKEN"))


def _make_md_conn() -> duckdb.DuckDBPyConnection:
    """MotherDuck connection; the marts live in the main_marts schema.

    MOTHERDUCK_TOKEN is read automatically by DuckDB's motherduck extension on
    connect. Use a read-only (read-scaling) token here — never the read-write
    build token that the pipeline uses.
    """
    db = os.environ.get("MOTHERDUCK_DATABASE", "paper_to_patent")
    return duckdb.connect(f"md:{db}")


def _query(sql: str, params: list[object] | None = None) -> pl.DataFrame:
    if _md_mode():
        conn = _make_md_conn()
        try:
            return conn.execute(sql, params or []).pl()
        finally:
            conn.close()
    if not _LOCAL_DB.exists():
        raise FileNotFoundError(
            f"Local DuckDB warehouse not found at {_LOCAL_DB}.\n"
            "Run 'dbt build' from models/ to build it, "
            "or set MOTHERDUCK_TOKEN for production deployment."
        )
    with duckdb.connect(str(_LOCAL_DB), read_only=True) as conn:
        return conn.execute(sql, params or []).pl()


def _scope_clause(
    family_col: str,
    cluster_col: str,
    family_ids: tuple[str, ...] | None,
    cluster_ids: tuple[str, ...] | None,
) -> str:
    """A ' AND ...' SQL fragment restricting family_col/cluster_col to the given ID sets.

    Both are optional; an empty/None set means "no restriction" on that dimension.
    Shared by the Organisation Profile page's family + cluster filters, which apply
    to nearly every query on that page.
    """
    clauses = []
    if family_ids:
        ids_sql = ", ".join(f"'{f}'" for f in family_ids)
        clauses.append(f"{family_col} IN ({ids_sql})")
    if cluster_ids:
        ids_sql = ", ".join(f"'{c}'" for c in cluster_ids)
        clauses.append(f"{cluster_col} IN ({ids_sql})")
    return (" AND " + " AND ".join(clauses)) if clauses else ""


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
def load_family_velocity(
    family_id: str, cluster_ids: tuple[str, ...] | None = None
) -> pl.DataFrame:
    """Annual paper and patent counts for a family (mart_velocity rolled up).

    One row per year; paper_count and patent_count summed across the family's
    non-noise clusters. Patents are counted by FILING year and undercount the most
    recent years because PatentsView holds granted patents only and recent filings
    are still in the grant pipeline — the UI fades those trailing years.
    cluster_ids, if given, restricts the rollup to that subset of the family's
    clusters (the Family Deepdive page's cluster filter).
    Source: mart_velocity + seed_cluster_family. Output: R2 gold / dev.duckdb.
    """
    cluster_filter = ""
    if cluster_ids:
        ids_sql = ", ".join(f"'{c}'" for c in cluster_ids)
        cluster_filter = f"AND mv.cluster_id IN ({ids_sql})"
    return _query(
        f"""
        SELECT mv.year,
               SUM(mv.paper_count)  AS paper_count,
               SUM(mv.patent_count) AS patent_count
        FROM main_marts.mart_velocity mv
        JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mv.cluster_id
        WHERE scf.family_id = ? AND mv.cluster_id != 'c_noise' {cluster_filter}
        GROUP BY mv.year
        ORDER BY mv.year
        """,
        [family_id],
    )


@st.cache_data(ttl=3600)
def load_family_org_leaderboard(
    family_id: str, side: str, top_n: int = 50, cluster_ids: tuple[str, ...] | None = None
) -> pl.DataFrame:
    """Top orgs for a family by side ('paper'|'patent'), with total distinct org count.

    Returns top_n rows ordered by doc_count DESC.
    Each row carries total_orgs = count of all distinct orgs for this family+side.
    cluster_ids, if given, restricts the aggregation to that subset of the family's
    clusters (the Family Deepdive page's cluster filter).
    Source: mart_competitive joined to seed_cluster_family; excludes 'Unresolved' and c_noise.
    Output: R2 gold Parquet or local dev.duckdb.
    """
    cluster_filter = ""
    if cluster_ids:
        ids_sql = ", ".join(f"'{c}'" for c in cluster_ids)
        cluster_filter = f"AND mc.cluster_id IN ({ids_sql})"
    return _query(
        f"""
        WITH agg AS (
            SELECT mc.org_id, mc.canonical_name, SUM(mc.doc_count) AS doc_count
            FROM main_marts.mart_competitive mc
            JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
            WHERE scf.family_id = ? AND mc.side = ? AND mc.canonical_name != 'Unresolved'
              AND mc.cluster_id != 'c_noise' {cluster_filter}
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
def _load_seed_orgs_for_searchbox() -> list[tuple[str, str]]:
    """All active resolved orgs as (name, id) tuples for the searchbox's empty-query default."""
    df = _query("""
        SELECT org_id, canonical_name
        FROM main_marts.dim_organization
        WHERE primary_match_method != 'native_id'
          AND org_id IN (
              SELECT org_id FROM main_marts.mart_competitive
              WHERE cluster_id != 'c_noise'
          )
        ORDER BY canonical_name ASC
        LIMIT 100
    """)
    return [(row["canonical_name"], row["org_id"]) for row in df.to_dicts()]


def search_orgs_ilike(query: str) -> list[tuple[str, str]]:
    """Server-side ILIKE search for the org-profile searchbox (called on each keystroke).

    Returns (label, value) tuples where value is org_id. Short/empty queries return all
    active resolved orgs so the dropdown is useful before the user types.
    Excludes native_id atoms (unresolved PatentsView fragments) and orgs with no activity.
    """
    if not query or len(query) < 2:
        return _load_seed_orgs_for_searchbox()
    df = _query(
        """
        SELECT org_id, canonical_name
        FROM main_marts.dim_organization
        WHERE canonical_name ILIKE ?
          AND primary_match_method != 'native_id'
          AND org_id IN (
              SELECT org_id FROM main_marts.mart_competitive
              WHERE cluster_id != 'c_noise'
          )
        ORDER BY canonical_name ASC
        LIMIT 50
        """,
        [f"%{query}%"],
    )
    return [(row["canonical_name"], row["org_id"]) for row in df.to_dicts()]


def search_papers_ilike(query: str) -> list[tuple[str, str]]:
    """ILIKE search for the trace-page paper searchbox (called on each keystroke).

    Returns (label, work_id) tuples. Empty/short queries return the top 30 most-cited
    papers so the dropdown is useful before the user types.
    Only includes papers with at least one NPL citation link.
    """
    if not query or len(query) < 2:
        df = _query("""
            SELECT dp.work_id, dp.title, dp.publication_year,
                   COUNT(DISTINCT fnl.patent_id) AS n_citing
            FROM main_marts.dim_paper dp
            JOIN main_marts.fact_npl_link fnl ON fnl.work_id = dp.work_id
            GROUP BY dp.work_id, dp.title, dp.publication_year
            ORDER BY n_citing DESC
            LIMIT 30
        """)
    else:
        df = _query(
            """
            SELECT dp.work_id, dp.title, dp.publication_year,
                   COUNT(DISTINCT fnl.patent_id) AS n_citing
            FROM main_marts.dim_paper dp
            JOIN main_marts.fact_npl_link fnl ON fnl.work_id = dp.work_id
            WHERE dp.title ILIKE ?
            GROUP BY dp.work_id, dp.title, dp.publication_year
            ORDER BY n_citing DESC
            LIMIT 50
            """,
            [f"%{query}%"],
        )
    results = []
    for row in df.to_dicts():
        title = row["title"] or ""
        yr = row["publication_year"] or "?"
        n = row["n_citing"]
        label = f"{title[:75]}{'…' if len(title) > 75 else ''} ({yr} · {n} patents)"
        results.append((label, row["work_id"]))
    return results


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
def load_org_output_by_family(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Patent count per technology family for a given org (patenter perspective).

    family_ids/cluster_ids, if given, restrict this to the Organisation Profile
    page's active filter scope.
    """
    scope = _scope_clause("scf.family_id", "mc.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT scf.family_id, scf.family_name, SUM(mc.doc_count) AS n_patents
        FROM main_marts.mart_competitive mc
        JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.side = 'patent' {scope}
        GROUP BY scf.family_id, scf.family_name
        ORDER BY n_patents DESC
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_dataset_totals(
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """Total paper and patent counts across all in-scope technology families.

    family_ids/cluster_ids, if given, narrow this to the Organisation Profile
    page's active filter scope (via mart_gap, which is cluster-grained) instead
    of the whole dataset (via mart_family) -- this is the denominator behind
    the "% of all patents/papers" metric cards, so it must match the same scope
    those cards' numerators are computed over.
    """
    if not family_ids and not cluster_ids:
        df = _query("""
            SELECT SUM(n_papers) AS total_papers, SUM(n_patents) AS total_patents
            FROM main_marts.mart_family
            WHERE family_id != 'mixed'
        """)
    else:
        scope = _scope_clause("scf.family_id", "mg.cluster_id", family_ids, cluster_ids)
        df = _query(f"""
            SELECT SUM(mg.n_papers) AS total_papers, SUM(mg.n_patents) AS total_patents
            FROM main_marts.mart_gap mg
            JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mg.cluster_id
            WHERE mg.cluster_id != 'c_noise' {scope}
        """)
    row = df.row(0, named=True)
    return {
        "total_papers":  int(row["total_papers"]  or 0),
        "total_patents": int(row["total_patents"] or 0),
    }


@st.cache_data(ttl=3600)
def load_org_active_scope(org_id: str) -> pl.DataFrame:
    """Every cluster (with its family) this org has any patent or paper activity in.

    Used only to populate the Organisation Profile sidebar's family/cluster filter
    options -- independent of whatever filter is currently applied.
    """
    return _query(
        """
        SELECT DISTINCT mc.cluster_id, mc.tagline, scf.family_id, scf.family_name
        FROM main_marts.mart_competitive mc
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.cluster_id != 'c_noise'
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_top_patent_clusters(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Top 5 patent clusters (excluding c_noise) for a given patenter org, with family_id."""
    scope = _scope_clause("scf.family_id", "mc.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT mc.cluster_id, mc.tagline, mc.doc_count, mc.share,
               scf.family_id
        FROM main_marts.mart_competitive mc
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.side = 'patent' AND mc.cluster_id != 'c_noise' {scope}
        ORDER BY mc.doc_count DESC
        LIMIT 5
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_filing_years(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Patent filing count per year for a given org (from fact_patent_filing).

    fact_patent_filing carries cluster_id directly, so family_ids/cluster_ids are
    applied via a join to seed_cluster_family with no intermediate table needed.
    """
    scope = _scope_clause("scf.family_id", "fpf.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT YEAR(fpf.filing_date) AS year, COUNT(DISTINCT fpf.patent_id) AS n_patents
        FROM main_marts.fact_patent_filing fpf
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fpf.cluster_id
        WHERE fpf.org_id = ? {scope}
        GROUP BY year
        ORDER BY year
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_intake(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Research orgs whose papers are cited by this org's patents (via NPL links).

    family_ids/cluster_ids restrict which of this org's own patents are considered
    (the patent side of the NPL link), scoping the Organisation Profile filter.
    """
    scope = _scope_clause("scf.family_id", "fpf.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT
            fp.org_id AS paper_org_id,
            do2.canonical_name AS paper_org_name,
            COUNT(DISTINCT fnl.work_id) AS n_papers_cited
        FROM main_marts.fact_patent_filing fpf
        JOIN main_marts.fact_npl_link fnl ON fnl.patent_id = fpf.patent_id
        JOIN main_marts.fact_publication fp ON fp.work_id = fnl.work_id
        JOIN main_marts.dim_organization do2 ON do2.org_id = fp.org_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fpf.cluster_id
        WHERE fpf.org_id = ? {scope}
        GROUP BY fp.org_id, do2.canonical_name
        ORDER BY n_papers_cited DESC
        LIMIT 10
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_influence(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Patenters whose filed patents cite this org's research papers (via NPL links).

    family_ids/cluster_ids restrict which of this org's own papers are considered
    (the paper side of the NPL link), scoping the Organisation Profile filter.
    """
    scope = _scope_clause("scf.family_id", "fp.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT
            fpf.org_id AS patenter_org_id,
            do2.canonical_name AS patenter_name,
            COUNT(DISTINCT fnl.patent_id) AS n_patents
        FROM main_marts.fact_publication fp
        JOIN main_marts.fact_npl_link fnl ON fnl.work_id = fp.work_id
        JOIN main_marts.fact_patent_filing fpf ON fpf.patent_id = fnl.patent_id
        JOIN main_marts.dim_organization do2 ON do2.org_id = fpf.org_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fp.cluster_id
        WHERE fp.org_id = ?
          AND fpf.org_id != ? {scope}
        GROUP BY fpf.org_id, do2.canonical_name
        ORDER BY n_patents DESC
        LIMIT 10
        """,
        [org_id, org_id],
    )


@st.cache_data(ttl=3600)
def load_org_flagship_paper(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Single most-cited paper (by patents) for a given research org."""
    scope = _scope_clause("scf.family_id", "fp.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT
            fp.work_id,
            dp.title,
            dp.publication_date,
            dp.abstract,
            COUNT(DISTINCT fnl.patent_id) AS n_citing_patents
        FROM main_marts.fact_publication fp
        JOIN main_marts.fact_npl_link fnl ON fnl.work_id = fp.work_id
        JOIN main_marts.dim_paper dp ON dp.work_id = fp.work_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fp.cluster_id
        WHERE fp.org_id = ? {scope}
        GROUP BY fp.work_id, dp.title, dp.publication_date, dp.abstract
        ORDER BY n_citing_patents DESC
        LIMIT 1
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_flagship_patent(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Single patent with most NPL paper citations for a given patenter org."""
    scope = _scope_clause("scf.family_id", "fpf.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT
            fpf.patent_id,
            dp.title,
            fpf.filing_date,
            COUNT(DISTINCT fnl.work_id) AS n_papers_cited
        FROM main_marts.fact_patent_filing fpf
        JOIN main_marts.dim_patent dp ON dp.patent_id = fpf.patent_id
        JOIN main_marts.fact_npl_link fnl ON fnl.patent_id = fpf.patent_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fpf.cluster_id
        WHERE fpf.org_id = ? {scope}
        GROUP BY fpf.patent_id, dp.title, fpf.filing_date
        ORDER BY n_papers_cited DESC
        LIMIT 1
        """,
        [org_id],
    )


# ── Trace one idea (Surface 5) ───────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_trace_paper(work_id: str) -> pl.DataFrame:
    """Paper card for trace-one-idea: title, abstract, pub_date, topic, primary org, family."""
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
            dorg.canonical_name AS org_name,
            scf.family_id
        FROM main_marts.dim_paper dp
        LEFT JOIN primary_org po ON po.work_id = dp.work_id
        LEFT JOIN main_marts.dim_organization dorg ON dorg.org_id = po.org_id
        LEFT JOIN main_marts.fact_document_cluster fdc
            ON fdc.doc_id = dp.work_id AND fdc.doc_type = 'paper'
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fdc.cluster_id
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
        """,
        [work_id],
    )


@st.cache_data(ttl=3600)
def load_org_paper_output_by_family(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Paper count per technology family for a given org (researcher perspective)."""
    scope = _scope_clause("scf.family_id", "mc.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT scf.family_id, scf.family_name, SUM(mc.doc_count) AS n_papers
        FROM main_marts.mart_competitive mc
        JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.side = 'paper' {scope}
        GROUP BY scf.family_id, scf.family_name
        ORDER BY n_papers DESC
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_top_research_clusters(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Top 5 research clusters (excluding c_noise) for an org — researcher side, with family_id."""
    scope = _scope_clause("scf.family_id", "mc.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT mc.cluster_id, mc.tagline, mc.doc_count, mc.share,
               scf.family_id
        FROM main_marts.mart_competitive mc
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = mc.cluster_id
        WHERE mc.org_id = ? AND mc.side = 'paper' AND mc.cluster_id != 'c_noise' {scope}
        ORDER BY mc.doc_count DESC
        LIMIT 5
        """,
        [org_id],
    )


@st.cache_data(ttl=3600)
def load_org_paper_years(
    org_id: str,
    family_ids: tuple[str, ...] | None = None,
    cluster_ids: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Research paper count per publication year for a given org.

    fact_publication carries cluster_id directly, so family_ids/cluster_ids are
    applied via a join to seed_cluster_family with no intermediate table needed.
    """
    scope = _scope_clause("scf.family_id", "fp.cluster_id", family_ids, cluster_ids)
    return _query(
        f"""
        SELECT YEAR(dp.publication_date) AS year, COUNT(DISTINCT fp.work_id) AS n_papers
        FROM main_marts.fact_publication fp
        JOIN main_marts.dim_paper dp ON dp.work_id = fp.work_id
        LEFT JOIN main_marts.seed_cluster_family scf ON scf.cluster_id = fp.cluster_id
        WHERE fp.org_id = ?
          AND dp.publication_date IS NOT NULL {scope}
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
