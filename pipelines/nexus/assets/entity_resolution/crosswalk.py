"""Entity resolution — Layer 1: within-source organisation staging.

Two assets produce per-source staging tables of distinct organisations
(one row per disambiguated entity). These feed Layer 2 (seed crosswalk)
and Layer 3 (fuzzy bridge) in subsequent ER assets.

PatentsView side (patentsview_orgs_staging):
  Source   : g_assignee_disambiguated joined to patents_scoped
  Identity : assignee_id  (PatentsView's own disambiguated UUID)
  Tag      : match_method="native_id", confidence="high"
  Output   : r2://p2p-lake/intermediate/er/patentsview_orgs_staging/v{date}/

OpenAlex side (openalex_institutions_staging):
  Source   : works Parquet (institution_ids + institution_display_names arrays)
  Identity : institution_id  (OpenAlex canonical URI, e.g. https://openalex.org/I…)
  Tag      : match_method="ror", confidence="high"
  Output   : r2://p2p-lake/intermediate/er/openalex_institutions_staging/v{date}/
"""

import datetime
import os
import pathlib
import tempfile

import duckdb
import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.entity_resolution.normalize import normalize_org_name
from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

# AssigneeType codes that represent organisations (not individuals).
# 2=US company · 3=foreign company · 6=US government · 7=foreign government
# 4=US individual · 5=foreign individual — excluded.
_ORG_ASSIGNEE_TYPES: tuple[str, ...] = ("2", "3", "6", "7")


# ---------------------------------------------------------------------------
# Pure function — testable without R2
# ---------------------------------------------------------------------------


def build_patentsview_orgs_staging(
    assignees_path: str,
    scoped_path: str,
    con: duckdb.DuckDBPyConnection,
) -> pl.DataFrame:
    """Return distinct org-type assignees from scoped patents with normalised names.

    Produces one row per unique assignee_id. Output columns:
      assignee_id, display_name, normalized_name, match_method, confidence.

    Filters applied:
      - Only patents that appear in scoped_path (CPC + filing-date scope corpus).
      - Only assignee_type in ('2','3','6','7') — organisations, not individuals.
      - Null or blank disambig_assignee_organization excluded.
      - Rows where normalize_org_name() returns '' excluded (name was all suffixes).

    Works with any DuckDB-readable path (local Parquet for tests, r2:// for prod).
    """
    type_list = ", ".join(f"'{t}'" for t in _ORG_ASSIGNEE_TYPES)
    sql = f"""
        SELECT
            a.assignee_id,
            MIN(a.disambig_assignee_organization) AS display_name
        FROM read_parquet('{assignees_path}') a
        JOIN read_parquet('{scoped_path}') s ON a.patent_id = s.patent_id
        WHERE a.disambig_assignee_organization IS NOT NULL
          AND TRIM(a.disambig_assignee_organization) <> ''
          AND a.assignee_type IN ({type_list})
        GROUP BY a.assignee_id
        ORDER BY a.assignee_id
    """
    rows = con.execute(sql).fetchall()
    if not rows:
        return pl.DataFrame(
            schema={
                "assignee_id": pl.String,
                "display_name": pl.String,
                "normalized_name": pl.String,
                "match_method": pl.String,
                "confidence": pl.String,
            }
        )

    df = pl.DataFrame(rows, schema=["assignee_id", "display_name"], orient="row")
    df = df.with_columns(  # type: ignore[reportUnknownMemberType]
        pl.col("display_name")
        .map_elements(normalize_org_name, return_dtype=pl.String)
        .alias("normalized_name"),
        pl.lit("native_id").alias("match_method"),
        pl.lit("high").alias("confidence"),
    )
    return df.filter(pl.col("normalized_name").str.len_chars() > 0)  # type: ignore[reportUnknownMemberType]


# ---------------------------------------------------------------------------
# PatentsView Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=["patentsview_assignees_raw", "patents_scoped"],
    description=(
        "Layer 1 ER (PatentsView side): reads g_assignee_disambiguated from R2, "
        "joins to the scope corpus (patents_scoped), filters to org-type assignees "
        "(types 2/3/6/7), deduplicates to one row per assignee_id, and applies "
        "name normalisation. match_method='native_id', confidence='high'. "
        "Output: r2://p2p-lake/intermediate/er/patentsview_orgs_staging/v{date}/"
        "patentsview_orgs_staging.parquet"
    ),
)
def patentsview_orgs_staging(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"patentsview_orgs_staging/v{snapshot_date}/patentsview_orgs_staging.parquet"
    )

    with duckdb.get_connection() as con:
        try:
            result = con.execute(f"SELECT COUNT(*) FROM read_parquet('{r2_path}')").fetchone()
            existing: int | None = result[0] if result else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    bucket = r2.bucket
    assignees_glob = f"r2://{bucket}/raw/patentsview/assignees/*/*.parquet"
    scoped_glob = f"r2://{bucket}/raw/patentsview/patents_scoped/*/*.parquet"

    context.log.info("Building PatentsView orgs staging from R2.")
    with duckdb.get_connection() as con:
        df = build_patentsview_orgs_staging(assignees_glob, scoped_glob, con)
    context.log.info("Distinct org assignees in scope: %s", f"{len(df):,}")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        df.write_parquet(tmp)
        staging_r2 = f"{r2_path}.staging"
        staging_key = staging_r2.removeprefix(f"r2://{bucket}/")
        with duckdb.get_connection() as con:
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{tmp.as_posix()}')) "
                f"TO '{staging_r2}' (FORMAT PARQUET)"
            )
    finally:
        tmp.unlink(missing_ok=True)

    context.log.info("Staging complete. Promoting to final path.")
    with duckdb.get_connection() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{staging_r2}')) "
            f"TO '{r2_path}' (FORMAT PARQUET)"
        )

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if api_token:
        delete_r2_object(r2.account_id, api_token, bucket, staging_key)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set; staging file left: %s", staging_key)

    context.log.info("Written %s rows → %s", f"{len(df):,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": len(df), "r2_path": r2_path}
    )


# ---------------------------------------------------------------------------
# OpenAlex pure function — testable without R2
# ---------------------------------------------------------------------------


def build_openalex_institutions_staging(
    works_path: str,
    con: duckdb.DuckDBPyConnection,
) -> pl.DataFrame:
    """Return distinct OpenAlex institutions with normalised names.

    Unnests institution_ids and institution_display_names from the works Parquet
    using DuckDB's parallel UNNEST (positional — arrays built by the same loop
    in parse_work(), so they are co-indexed). Deduplicates to one row per
    institution_id. Applies normalize_org_name; drops rows where result is empty.

    Output columns: institution_id, display_name, normalized_name, match_method, confidence.
    Works with any DuckDB-readable path (local Parquet for tests, r2:// glob for prod).
    """
    _EMPTY_SCHEMA = {
        "institution_id": pl.String,
        "display_name": pl.String,
        "normalized_name": pl.String,
        "match_method": pl.String,
        "confidence": pl.String,
    }

    sql = f"""
        WITH src AS (
            SELECT
                UNNEST(institution_ids)           AS institution_id,
                UNNEST(institution_display_names) AS display_name
            FROM read_parquet('{works_path}')
        )
        SELECT institution_id, MIN(display_name) AS display_name
        FROM src
        WHERE institution_id IS NOT NULL
          AND institution_id <> ''
        GROUP BY institution_id
        ORDER BY institution_id
    """
    rows = con.execute(sql).fetchall()
    if not rows:
        return pl.DataFrame(schema=_EMPTY_SCHEMA)

    df = pl.DataFrame(rows, schema=["institution_id", "display_name"], orient="row")
    df = df.with_columns(  # type: ignore[reportUnknownMemberType]
        pl.col("display_name")
        .map_elements(
            lambda n: normalize_org_name(n) if n else "",
            return_dtype=pl.String,
        )
        .alias("normalized_name"),
        pl.lit("ror").alias("match_method"),
        pl.lit("high").alias("confidence"),
    )
    return df.filter(pl.col("normalized_name").str.len_chars() > 0)  # type: ignore[reportUnknownMemberType]


# ---------------------------------------------------------------------------
# OpenAlex Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=["openalex_works_raw"],
    description=(
        "Layer 1 ER (OpenAlex side): unnests institution_ids and institution_display_names "
        "from the works Parquet, deduplicates to one row per institution_id, normalises "
        "display names. match_method='ror', confidence='high'. "
        "Output: r2://p2p-lake/intermediate/er/openalex_institutions_staging/v{date}/"
        "openalex_institutions_staging.parquet"
    ),
)
def openalex_institutions_staging(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"openalex_institutions_staging/v{snapshot_date}/openalex_institutions_staging.parquet"
    )

    with duckdb.get_connection() as con:
        try:
            result = con.execute(f"SELECT COUNT(*) FROM read_parquet('{r2_path}')").fetchone()
            existing: int | None = result[0] if result else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    bucket = r2.bucket
    works_glob = f"r2://{bucket}/raw/openalex/*/*.parquet"

    context.log.info("Building OpenAlex institutions staging from %s.", works_glob)
    with duckdb.get_connection() as con:
        df = build_openalex_institutions_staging(works_glob, con)
    context.log.info("Distinct institutions: %s", f"{len(df):,}")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        df.write_parquet(tmp)
        staging_r2 = f"{r2_path}.staging"
        staging_key = staging_r2.removeprefix(f"r2://{bucket}/")
        with duckdb.get_connection() as con:
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{tmp.as_posix()}')) "
                f"TO '{staging_r2}' (FORMAT PARQUET)"
            )
    finally:
        tmp.unlink(missing_ok=True)

    context.log.info("Staging complete. Promoting to final path.")
    with duckdb.get_connection() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{staging_r2}')) "
            f"TO '{r2_path}' (FORMAT PARQUET)"
        )

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if api_token:
        delete_r2_object(r2.account_id, api_token, bucket, staging_key)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set; staging file left: %s", staging_key)

    context.log.info("Written %s rows → %s", f"{len(df):,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": len(df), "r2_path": r2_path}
    )
