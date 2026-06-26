"""Gold-layer export asset.

Reads all dbt mart tables from dev.duckdb (main_marts schema) and writes
versioned Parquet snapshots to r2://p2p-lake/gold/{dims|facts}/{model}/v{date}/.

Uses DuckDB ATTACH so the COPY is done entirely within DuckDB (no Python-side
row materialisation, no PyArrow). Run after paper_to_patent_dbt_assets.

The Streamlit app (Part 7) reads from this gold layer via in-process DuckDB + httpfs.

Output: r2://p2p-lake/gold/dims/{dim}/v{date}/{dim}.parquet
        r2://p2p-lake/gold/facts/{fact}/v{date}/{fact}.parquet
"""

import datetime
import os
import pathlib

from dagster import OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

# ---------------------------------------------------------------------------
# Models to export: maps mart name → R2 subdir (dims or facts)
# ---------------------------------------------------------------------------

_GOLD_MODELS: dict[str, str] = {
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
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _gold_r2_path(bucket: str, model: str, subdir: str, snapshot_date: str) -> str:
    """Build the canonical R2 path for one gold mart snapshot."""
    return f"r2://{bucket}/gold/{subdir}/{model}/v{snapshot_date}/{model}.parquet"


def _r2_path_exists(con: object, path: str) -> bool:  # type: ignore[reportUnknownParameterType]
    """Return True if the R2 path contains at least one row."""
    import duckdb as _duckdb_lib  # noqa: PLC0415

    assert isinstance(con, _duckdb_lib.DuckDBPyConnection)
    try:
        n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()
        return bool(n and n[0] > 0)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Write helper: ATTACH dev.duckdb → COPY to R2 staging → promote
# No PyArrow, no Python-side row materialisation.
# ---------------------------------------------------------------------------


def _write_table_to_r2(
    model: str,
    dev_db_path: pathlib.Path,
    r2_path: str,
    bucket: str,
    duckdb_resource: DuckDBR2Resource,
    r2_resource: R2Resource,
) -> int:
    """Copy one mart table from dev.duckdb to R2. Returns row count."""
    staging_r2 = f"{r2_path}.staging"
    staging_key = staging_r2.removeprefix(f"r2://{bucket}/")
    dev_path_str = str(dev_db_path).replace("\\", "/")

    with duckdb_resource.get_connection() as con:
        con.execute(f"ATTACH '{dev_path_str}' AS dev_db (READ_ONLY)")
        result = con.execute(
            f"SELECT COUNT(*) FROM dev_db.main_marts.{model}"
        ).fetchone()
        n: int = result[0] if result else 0  # type: ignore[reportUnknownVariableType]
        con.execute(
            f"COPY (SELECT * FROM dev_db.main_marts.{model}) "
            f"TO '{staging_r2}' (FORMAT PARQUET)"
        )

    with duckdb_resource.get_connection() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{staging_r2}')) "
            f"TO '{r2_path}' (FORMAT PARQUET)"
        )

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if api_token:
        delete_r2_object(r2_resource.account_id, api_token, bucket, staging_key)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set; staging file left: %s", staging_key)

    return n


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="transform",
    description=(
        "Exports all dbt gold marts from dev.duckdb (main_marts schema) to R2. "
        "Run after paper_to_patent_dbt_assets to refresh the gold snapshot. "
        "Dims: dim_cpc, dim_organization, dim_paper, dim_patent, dim_technology_cluster. "
        "Facts: fact_document_cluster, fact_npl_link, fact_patent_citation, "
        "fact_patent_filing, fact_publication. "
        "Output: r2://p2p-lake/gold/{dims|facts}/{model}/v{date}/{model}.parquet"
    ),
)
def gold_export(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    """Export all dbt marts to the R2 gold layer via DuckDB ATTACH + COPY.

    Produces: r2://p2p-lake/gold/{dims,facts}/{model}/v{date}/{model}.parquet
    Depends on: dev.duckdb main_marts schema (paper_to_patent_dbt_assets must have run first).
    Output: see above.
    """
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket

    r2_paths = {
        model: _gold_r2_path(bucket, model, subdir, snapshot_date)
        for model, subdir in _GOLD_MODELS.items()
    }

    # Idempotency: skip only if all outputs already exist for today
    with duckdb.get_connection() as con:
        all_exist = all(_r2_path_exists(con, path) for path in r2_paths.values())
    if all_exist:
        context.log.info(
            "All %s gold snapshots for %s already exist. Skipping.",
            len(_GOLD_MODELS), snapshot_date,
        )
        return

    dev_db_path = pathlib.Path(os.environ.get("DBT_DUCKDB_PATH", "dev.duckdb"))
    if not dev_db_path.exists():
        raise FileNotFoundError(
            f"dev.duckdb not found at {dev_db_path}. Run 'dbt build' first."
        )

    row_counts: dict[str, int] = {}
    for model, r2_path in r2_paths.items():
        context.log.info("Exporting %s → %s", model, r2_path)
        n = _write_table_to_r2(model, dev_db_path, r2_path, bucket, duckdb, r2)
        row_counts[model] = n
        context.log.info("  %s rows written.", f"{n:,}")

    context.log.info(
        "gold_export complete. Snapshot: %s. %s models exported.",
        snapshot_date, len(_GOLD_MODELS),
    )
    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "models_exported": len(_GOLD_MODELS),
            "row_counts": row_counts,
        }
    )
