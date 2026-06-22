"""Entity resolution — Layer 2: seed crosswalk.

Two assets:

seed_crosswalk_matched (PatentsView side):
  Joins seed_crosswalk.csv to patentsview_orgs_staging on normalized_patentsview.
  Output: r2://p2p-lake/intermediate/er/seed_crosswalk_matched/v{date}/

seed_crosswalk_oa_matched (OpenAlex side):
  Joins seed_crosswalk.csv to openalex_institutions_staging on openalex_institution_id.
  Only rows where openalex_institution_id is non-blank in the CSV are emitted.
  Covers orgs whose PV legal name and OA display name are too different to fuzzy_high
  (e.g. Stanford: "The Board of Trustees..." vs "Stanford University").
  Output: r2://p2p-lake/intermediate/er/seed_crosswalk_oa_matched/v{date}/
"""

import datetime
import os
import pathlib
import tempfile

import duckdb
import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

SEED_CSV = pathlib.Path(__file__).parent / "seed_crosswalk.csv"


# ---------------------------------------------------------------------------
# Pure function — testable without R2
# ---------------------------------------------------------------------------


def build_seed_crosswalk_matches(
    seed_csv_path: str,
    pv_staging_path: str,
    con: duckdb.DuckDBPyConnection,
) -> pl.DataFrame:
    """Join seed CSV to PatentsView orgs staging via normalized_name.

    Returns one row per matched (org_id, assignee_id) pair. Output columns:
      org_id, canonical_name, assignee_id, display_name,
      openalex_institution_id, match_method, confidence.

    Seed entries whose normalized_patentsview has no match in the staging
    table are silently excluded (inner join). That is expected — it means
    the PatentsView bulk data has no scoped patent for that org, or the
    normalized form drifted. These gaps should be reviewed when updating the
    seed CSV after a new PatentsView snapshot.

    Works with any DuckDB-readable path (local files for tests, r2:// for prod).
    """
    sql = f"""
        SELECT
            seed.org_id,
            seed.canonical_name,
            pv.assignee_id,
            pv.display_name,
            seed.openalex_institution_id,
            'seed_crosswalk'  AS match_method,
            'high'            AS confidence
        FROM read_csv('{seed_csv_path}', header = true, all_varchar = true) seed
        JOIN read_parquet('{pv_staging_path}') pv
          ON pv.normalized_name = seed.normalized_patentsview
        ORDER BY seed.org_id, pv.assignee_id
    """
    rows = con.execute(sql).fetchall()
    columns = [
        "org_id",
        "canonical_name",
        "assignee_id",
        "display_name",
        "openalex_institution_id",
        "match_method",
        "confidence",
    ]
    if not rows:
        return pl.DataFrame(schema={c: pl.String for c in columns})
    return pl.DataFrame(rows, schema=columns, orient="row")


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=["patentsview_orgs_staging"],
    description=(
        "Layer 2 ER: joins seed_crosswalk.csv to patentsview_orgs_staging on "
        "normalized_name. Emits one row per (org_id, assignee_id) with "
        "match_method='seed_crosswalk', confidence='high'. "
        "openalex_institution_id is blank until the OpenAlex institutions staging "
        "is implemented. "
        "Output: r2://p2p-lake/intermediate/er/seed_crosswalk_matched/v{date}/"
        "seed_crosswalk_matched.parquet"
    ),
)
def seed_crosswalk_matched(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"seed_crosswalk_matched/v{snapshot_date}/seed_crosswalk_matched.parquet"
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
    pv_glob = f"r2://{bucket}/intermediate/er/patentsview_orgs_staging/*/*.parquet"
    seed_path = str(SEED_CSV)

    context.log.info("Building seed crosswalk matches from %s.", seed_path)
    with duckdb.get_connection() as con:
        df = build_seed_crosswalk_matches(seed_path, pv_glob, con)
    context.log.info(
        "Seed crosswalk matched %s (org_id, assignee_id) pairs covering %s org_ids.",
        f"{len(df):,}",
        f"{df['org_id'].n_unique():,}",
    )

    unmatched = _find_unmatched_seed_entries(seed_path, pv_glob, duckdb)
    if unmatched:
        context.log.warning(
            "Seed entries with no PatentsView match (%d): %s",
            len(unmatched),
            unmatched,
        )

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
        {
            "snapshot_date": snapshot_date,
            "row_count": len(df),
            "org_id_count": df["org_id"].n_unique(),
            "r2_path": r2_path,
        }
    )


def _find_unmatched_seed_entries(
    seed_path: str,
    pv_path: str,
    duckdb_resource: DuckDBR2Resource,
) -> list[str]:
    """Return normalized_patentsview entries from the seed CSV that had no PV match."""
    sql = f"""
        SELECT seed.normalized_patentsview
        FROM read_csv('{seed_path}', header = true, all_varchar = true) seed
        LEFT JOIN read_parquet('{pv_path}') pv
          ON pv.normalized_name = seed.normalized_patentsview
        WHERE pv.assignee_id IS NULL
        ORDER BY 1
    """
    with duckdb_resource.get_connection() as con:
        rows = con.execute(sql).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# OpenAlex side — pure function
# ---------------------------------------------------------------------------


def build_seed_crosswalk_oa_matches(
    seed_csv_path: str,
    oa_staging_path: str,
    con: duckdb.DuckDBPyConnection,
) -> pl.DataFrame:
    """Join seed CSV to OpenAlex institutions staging via openalex_institution_id.

    Only seed rows where openalex_institution_id is non-blank are considered.
    Returns one row per matched (org_id, institution_id) pair. Output columns:
      org_id, canonical_name, institution_id, display_name, match_method, confidence.

    This covers orgs whose PV legal name and OA display name are too different
    for the fuzzy bridge to match (e.g. Stanford, MIT).
    """
    columns = ["org_id", "canonical_name", "institution_id", "display_name",
               "match_method", "confidence"]
    _EMPTY = {c: pl.String for c in columns}

    sql = f"""
        SELECT
            seed.org_id,
            seed.canonical_name,
            oa.institution_id,
            oa.display_name,
            'seed_crosswalk' AS match_method,
            'high'           AS confidence
        FROM read_csv('{seed_csv_path}', header = true, all_varchar = true) seed
        JOIN read_parquet('{oa_staging_path}') oa
          ON oa.institution_id = seed.openalex_institution_id
        WHERE seed.openalex_institution_id IS NOT NULL
          AND TRIM(seed.openalex_institution_id) <> ''
        ORDER BY seed.org_id, oa.institution_id
    """
    rows = con.execute(sql).fetchall()
    if not rows:
        return pl.DataFrame(schema=_EMPTY)
    return pl.DataFrame(rows, schema=columns, orient="row")


# ---------------------------------------------------------------------------
# OpenAlex side — Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=["openalex_institutions_staging"],
    description=(
        "Layer 2 ER (OpenAlex side): joins seed_crosswalk.csv to "
        "openalex_institutions_staging on openalex_institution_id. Emits one row per "
        "(org_id, institution_id) for seed entries that have an explicit OA institution ID. "
        "match_method='seed_crosswalk', confidence='high'. "
        "Output: r2://p2p-lake/intermediate/er/seed_crosswalk_oa_matched/v{date}/"
        "seed_crosswalk_oa_matched.parquet"
    ),
)
def seed_crosswalk_oa_matched(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"seed_crosswalk_oa_matched/v{snapshot_date}/seed_crosswalk_oa_matched.parquet"
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
    oa_glob = f"r2://{bucket}/intermediate/er/openalex_institutions_staging/*/*.parquet"
    seed_path = str(SEED_CSV)

    context.log.info("Building seed crosswalk OA matches from %s.", seed_path)
    with duckdb.get_connection() as con:
        df = build_seed_crosswalk_oa_matches(seed_path, oa_glob, con)
    context.log.info(
        "Seed crosswalk OA matched %s (org_id, institution_id) pairs.",
        f"{len(df):,}",
    )

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
        {
            "snapshot_date": snapshot_date,
            "row_count": len(df),
            "org_id_count": df["org_id"].n_unique() if not df.is_empty() else 0,
            "r2_path": r2_path,
        }
    )
