"""PatentsView bulk ingest helpers and Dagster assets.

Provides load_bulk_tsv() — the shared download/extract/validate helper —
and one Dagster asset per PatentsView bulk file. Each asset writes a Parquet
snapshot to R2 using the stage-then-promote pattern so a failed run never
destroys an existing good snapshot.

Output paths: r2://p2p-lake/raw/patentsview/{entity}/v{snapshot_date}/{entity}.parquet
"""

import datetime
import os
import pathlib
import tempfile
import zipfile
from collections.abc import Mapping
from urllib.parse import urlparse

import duckdb
import httpx
import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

# ---------------------------------------------------------------------------
# Bulk-download URLs
# PatentsView migrated to data.uspto.gov (March 2026). Both sites are JS SPAs
# that cannot be scraped programmatically — direct URL download does not work.
# All files must be placed in data/raw/ manually (see SETUP.md D1).
# These URL strings are documentation only; the helper checks local files first.
# ---------------------------------------------------------------------------

_BASE_URL = "https://data.uspto.gov/datasets/patentsview/grant"

_URLS: dict[str, str] = {
    "g_patent.tsv.zip": f"{_BASE_URL}/g_patent.tsv.zip",
    "g_application.tsv.zip": f"{_BASE_URL}/g_application.tsv.zip",
    "g_assignee_disambiguated.tsv.zip": f"{_BASE_URL}/g_assignee_disambiguated.tsv.zip",
    "g_cpc_current.tsv.zip": f"{_BASE_URL}/g_cpc_current.tsv.zip",
    "g_other_reference.tsv.zip": f"{_BASE_URL}/g_other_reference.tsv.zip",
    "g_us_patent_citation.tsv.zip": f"{_BASE_URL}/g_us_patent_citation.tsv.zip",
    "g_inventor_disambiguated.tsv.zip": f"{_BASE_URL}/g_inventor_disambiguated.tsv.zip",
}

# Resolved relative to this file: pipelines/nexus/assets/ingest/ → project root
_DATA_RAW_DIR = pathlib.Path(__file__).parents[4] / "data" / "raw"

# ---------------------------------------------------------------------------
# load_bulk_tsv — shared download/extract/validate helper
# ---------------------------------------------------------------------------


def _filename_from_url(url: str) -> str:
    return pathlib.Path(urlparse(url).path).name


def _tsv_name(zip_filename: str) -> str:
    """'g_patent.tsv.zip' → 'g_patent.tsv'"""
    return zip_filename.removesuffix(".zip")


def load_bulk_tsv(
    url: str,
    required_columns: list[str],
    *,
    data_dir: pathlib.Path | None = None,
    schema_overrides: Mapping[str, type[pl.DataType] | pl.DataType] | None = None,
) -> pl.LazyFrame:
    """Return a LazyFrame over a PatentsView bulk TSV file.

    Resolution order (stops at first hit):
    1. <data_dir>/<stem>.tsv already exists → scan directly.
    2. <data_dir>/<stem>.tsv.zip exists → extract → scan.
    3. Download zip from url → extract → scan.

    schema_overrides forces specific column dtypes (e.g. patent_id as String to
    handle non-numeric IDs like design patents "D1035263" or reissues "RE12345").
    Raises ValueError if any required_columns are absent from the file header.
    """
    raw = data_dir if data_dir is not None else _DATA_RAW_DIR
    zip_filename = _filename_from_url(url)
    tsv_filename = _tsv_name(zip_filename)

    tsv_path = raw / tsv_filename
    zip_path = raw / zip_filename

    if not tsv_path.exists():
        if not zip_path.exists():
            logger.info("Attempting download %s → %s", url, zip_path)
            raw.mkdir(parents=True, exist_ok=True)
            try:
                with httpx.stream("GET", url, follow_redirects=True, timeout=3600) as resp:
                    resp.raise_for_status()
                    with zip_path.open("wb") as fh:
                        for chunk in resp.iter_bytes(chunk_size=8 * 1024 * 1024):
                            fh.write(chunk)
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                raise RuntimeError(
                    f"Cannot download {zip_filename}: {exc}\n"
                    "PatentsView bulk files must be downloaded manually from "
                    "data.uspto.gov (Datasets → PatentsView → Grant Data) "
                    f"and saved to {raw}/."
                ) from exc

        logger.info("Extracting %s", zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            target = (
                tsv_filename
                if tsv_filename in members
                else next((m for m in members if m.endswith(".tsv")), None)
            )
            if target is None:
                raise RuntimeError(f"No .tsv entry found inside {zip_path}")
            zf.extract(target, path=raw)
            extracted = raw / target
            if extracted != tsv_path:
                extracted.rename(tsv_path)

    lf = pl.scan_csv(
        tsv_path,
        separator="\t",
        infer_schema_length=10_000,
        schema_overrides=schema_overrides or {},
    )
    missing = set(required_columns) - set(lf.collect_schema().names())
    if missing:
        raise ValueError(
            f"Missing required columns in {tsv_filename}: {sorted(missing)}"
        )
    return lf


# ---------------------------------------------------------------------------
# Shared R2 write helper (stage-then-promote)
# ---------------------------------------------------------------------------


def _write_lazy_to_r2(
    context: OpExecutionContext,
    lf: pl.LazyFrame,
    r2_path: str,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> int:
    """Stream lf → local temp parquet → R2 staging → R2 final. Returns row count."""
    staging_path = f"{r2_path}.staging"
    staging_key = staging_path.removeprefix(f"r2://{r2.bucket}/")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        lf.sink_parquet(tmp)
        with duckdb.get_connection() as con:
            result = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{tmp.as_posix()}')"
            ).fetchone()
            count: int = result[0] if result else 0
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{tmp.as_posix()}')) "
                f"TO '{staging_path}' (FORMAT PARQUET)"
            )
    finally:
        tmp.unlink(missing_ok=True)

    context.log.info("Staging complete. Promoting to final path.")
    with duckdb.get_connection() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{staging_path}')) "
            f"TO '{r2_path}' (FORMAT PARQUET)"
        )

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if api_token:
        delete_r2_object(r2.account_id, api_token, r2.bucket, staging_key)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set; staging file left: %s", staging_key)

    return count


def _snapshot_exists(r2_path: str, duckdb: DuckDBR2Resource) -> int | None:
    """Return row count if a Parquet snapshot already exists at r2_path, else None."""
    with duckdb.get_connection() as con:
        try:
            result = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{r2_path}')"
            ).fetchone()
            return result[0] if result else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Dagster assets — one per bulk file
# ---------------------------------------------------------------------------


@asset(
    group_name="ingest",
    description=(
        "Downloads g_patent.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/patents/v{snapshot_date}/patents.parquet. "
        "Contains core patent metadata: filing date, grant date, title, abstract."
    ),
)
def patentsview_patents_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = f"r2://{r2.bucket}/raw/patentsview/patents/v{snapshot_date}/patents.parquet"

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_patent.tsv.zip"],
        required_columns=["patent_id", "patent_date", "patent_title"],
        schema_overrides={"patent_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


@asset(
    group_name="ingest",
    description=(
        "Downloads g_application.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/applications/v{snapshot_date}/applications.parquet."
        " Provides filing_date — required for the filing-date filter in patents_scoped."
    ),
)
def patentsview_applications_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/raw/patentsview/applications/v{snapshot_date}/applications.parquet"
    )

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_application.tsv.zip"],
        required_columns=["patent_id", "filing_date"],
        schema_overrides={"patent_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


@asset(
    group_name="ingest",
    description=(
        "Downloads g_assignee_disambiguated.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/assignees/v{snapshot_date}/assignees.parquet. "
        "Contains disambiguated assignees with assignee_id — the patent-side identity for ER."
    ),
)
def patentsview_assignees_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/raw/patentsview/assignees/v{snapshot_date}/assignees.parquet"
    )

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_assignee_disambiguated.tsv.zip"],
        required_columns=["patent_id", "assignee_id"],
        schema_overrides={"patent_id": pl.String, "assignee_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


@asset(
    group_name="ingest",
    description=(
        "Downloads g_cpc_current.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/cpc/v{snapshot_date}/cpc.parquet. "
        "CPC subclass assignments — used to filter patents to the scope technology families."
    ),
)
def patentsview_cpc_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = f"r2://{r2.bucket}/raw/patentsview/cpc/v{snapshot_date}/cpc.parquet"

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_cpc_current.tsv.zip"],
        required_columns=["patent_id", "cpc_group"],
        schema_overrides={"patent_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


@asset(
    group_name="ingest",
    description=(
        "Downloads g_other_reference.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/npl/v{snapshot_date}/npl.parquet. "
        "Non-patent literature citations — the raw input for the paper↔patent NPL linkage."
    ),
)
def patentsview_npl_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = f"r2://{r2.bucket}/raw/patentsview/npl/v{snapshot_date}/npl.parquet"

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_other_reference.tsv.zip"],
        required_columns=["patent_id", "other_reference_text"],
        schema_overrides={"patent_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


@asset(
    group_name="ingest",
    description=(
        "Downloads g_us_patent_citation.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/citations/v{snapshot_date}/citations.parquet. "
        "Patent-to-patent citation edges — used for citation network analytics in Part 6."
    ),
)
def patentsview_citations_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/raw/patentsview/citations/v{snapshot_date}/citations.parquet"
    )

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_us_patent_citation.tsv.zip"],
        required_columns=["patent_id", "citation_patent_id"],
        schema_overrides={"patent_id": pl.String, "citation_patent_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


@asset(
    group_name="ingest",
    description=(
        "Downloads g_inventor_disambiguated.tsv.zip from PatentsView, converts to Parquet, "
        "writes to r2://p2p-lake/raw/patentsview/inventors/v{snapshot_date}/inventors.parquet. "
        "Inventor metadata only — person-level ER is out of scope for v1."
    ),
)
def patentsview_inventors_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/raw/patentsview/inventors/v{snapshot_date}/inventors.parquet"
    )

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    lf = load_bulk_tsv(
        _URLS["g_inventor_disambiguated.tsv.zip"],
        required_columns=["patent_id"],
        schema_overrides={"patent_id": pl.String, "inventor_id": pl.String},
    )
    count = _write_lazy_to_r2(context, lf, r2_path, r2, duckdb)
    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )


# ---------------------------------------------------------------------------
# Scope filter constants — mirror of ROADMAP Part 0 scope contract
# ---------------------------------------------------------------------------

# CPC group prefix match: any cpc_group starting with one of these codes is in scope.
SCOPE_CPC_PREFIXES: list[str] = [
    # EUV Lithography
    "G03F7/20",
    "G03F7/70",
    # Silicon Photonics
    "G02B6/12",
    "G02B6/122",
    "H01S5/0224",
    "H01S5/10",
    # Neuromorphic & In-Memory Compute
    "G06N3/049",
    "G11C11/54",
    "G11C13/00",
    "H10N70/00",
]

SCOPE_FILING_START = "2014-01-01"
SCOPE_FILING_END = "2025-12-31"

# ---------------------------------------------------------------------------
# Scope filter — extractable for testing
# ---------------------------------------------------------------------------


def filter_patents_to_scope(
    patents_path: str,
    apps_path: str,
    cpc_path: str,
    con: duckdb.DuckDBPyConnection,
) -> pl.DataFrame:
    """Return patents matching scope CPC codes and filing-date window.

    Works with any DuckDB-readable path (local Parquet for tests, r2:// for prod).
    Returns columns: patent_id, patent_title, patent_date, patent_type, filing_date.
    """
    cpc_conditions = " OR ".join(
        f"cpc.cpc_group LIKE '{prefix}%'" for prefix in SCOPE_CPC_PREFIXES
    )
    sql = f"""
        WITH scoped_ids AS (
            SELECT DISTINCT patent_id
            FROM read_parquet('{cpc_path}') cpc
            WHERE {cpc_conditions}
        )
        SELECT
            p.patent_id,
            p.patent_title,
            p.patent_date,
            p.patent_type,
            a.filing_date
        FROM read_parquet('{patents_path}') p
        JOIN read_parquet('{apps_path}') a ON p.patent_id = a.patent_id
        JOIN scoped_ids s ON p.patent_id = s.patent_id
        WHERE a.filing_date >= '{SCOPE_FILING_START}'
          AND a.filing_date <= '{SCOPE_FILING_END}'
    """
    result = con.execute(sql).fetchall()
    columns = ["patent_id", "patent_title", "patent_date", "patent_type", "filing_date"]
    return pl.DataFrame(result, schema=columns, orient="row")


# ---------------------------------------------------------------------------
# patents_scoped asset
# ---------------------------------------------------------------------------


@asset(
    group_name="ingest",
    deps=["patentsview_patents_raw", "patentsview_applications_raw", "patentsview_cpc_raw"],
    description=(
        "Joins g_patent + g_application + g_cpc_current to produce the scope corpus: "
        "patents matching the technology-family CPC codes and filing_date 2014-2025. "
        "All downstream assets join against this filtered set. "
        "Output: r2://p2p-lake/raw/patentsview/patents_scoped/v{snapshot_date}/patents_scoped.parquet"
    ),
)
def patents_scoped(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/raw/patentsview/"
        f"patents_scoped/v{snapshot_date}/patents_scoped.parquet"
    )

    existing = _snapshot_exists(r2_path, duckdb)
    if existing is not None:
        context.log.info("Snapshot already at %s (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    bucket = r2.bucket
    patents_glob = f"r2://{bucket}/raw/patentsview/patents/*/*.parquet"
    apps_glob = f"r2://{bucket}/raw/patentsview/applications/*/*.parquet"
    cpc_glob = f"r2://{bucket}/raw/patentsview/cpc/*/*.parquet"
    staging_path = f"{r2_path}.staging"
    staging_key = staging_path.removeprefix(f"r2://{bucket}/")

    cpc_conditions = " OR ".join(
        f"cpc.cpc_group LIKE '{prefix}%'" for prefix in SCOPE_CPC_PREFIXES
    )
    sql = f"""
        WITH scoped_ids AS (
            SELECT DISTINCT patent_id
            FROM read_parquet('{cpc_glob}') cpc
            WHERE {cpc_conditions}
        )
        SELECT
            p.patent_id,
            p.patent_title,
            p.patent_date,
            p.patent_type,
            a.filing_date
        FROM read_parquet('{patents_glob}') p
        JOIN read_parquet('{apps_glob}') a ON p.patent_id = a.patent_id
        JOIN scoped_ids s ON p.patent_id = s.patent_id
        WHERE a.filing_date >= '{SCOPE_FILING_START}'
          AND a.filing_date <= '{SCOPE_FILING_END}'
    """

    context.log.info("Running scope filter query.")
    with duckdb.get_connection() as con:
        count_result = con.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()
        count: int = count_result[0] if count_result else 0
        context.log.info("Scope filter: %s patents. Writing staging.", f"{count:,}")
        con.execute(f"COPY ({sql}) TO '{staging_path}' (FORMAT PARQUET)")

    context.log.info("Staging complete. Promoting to final path.")
    with duckdb.get_connection() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{staging_path}')) "
            f"TO '{r2_path}' (FORMAT PARQUET)"
        )

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if api_token:
        delete_r2_object(r2.account_id, api_token, r2.bucket, staging_key)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set; staging file left: %s", staging_key)

    context.log.info("Written %s rows → %s", f"{count:,}", r2_path)
    context.add_output_metadata(
        {"snapshot_date": snapshot_date, "row_count": count, "r2_path": r2_path}
    )
