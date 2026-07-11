"""Document-exclusion asset for Part 5 — the pre-staging quality gate.

Decides which scope documents are screened out of the corpus ENTIRELY (a
version-style title, or a paper whose title+abstract are both non-English, or a
patent with no usable title) and writes that list to R2 as excluded_documents.

Why this is a separate, upstream asset (not part of document_embeddings):
    The gate reads only title/abstract text — it does not need embeddings. By
    computing it here, over the RAW corpus, the exclusion list is produced
    BEFORE staging, which applies it (stg_openalex_works / stg_patents_scoped
    NOT-IN excluded_documents). That breaks the old cycle where staging depended
    on the embedding asset's output while the embedding asset read staging's
    dims. The decision is identical to the old in-embedding gate because staging
    does not transform title/abstract — it selects them from the same raw fields
    this asset reads (the work_id is extracted with the same regexp staging
    uses), so the gate sees byte-for-byte the same text.

Input:   R2 raw/openalex/v{date}/works.parquet,
         R2 raw/patentsview/patents_scoped/v{date}/patents_scoped.parquet
Output:  r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet
Schema:  doc_id, doc_type, exclusion_reason, model_version
"""

import datetime
import os
import pathlib
import tempfile

import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.assets.ml.embeddings import is_version_style_title, resolve_paper_text
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

# Version tag for the screening logic (langdetect + title heuristics), stamped on
# every excluded_documents row. Not an ML model — the column name is historical.
_GATE_VERSION = "quality-gate-v1"


# ---------------------------------------------------------------------------
# Pure helper — independently testable without R2
# ---------------------------------------------------------------------------


def compute_exclusions(
    paper_rows: list[tuple[str, str, str]],
    patent_rows: list[tuple[str, str]],
) -> list[dict[str, str]]:
    """Return the list of documents to exclude from the corpus entirely.

    paper_rows  : (work_id, title, abstract) over the raw scope papers.
    patent_rows : (patent_id, title) over the raw scope patents.

    A paper is excluded when resolve_paper_text() returns None — a version-style
    title (reason 'version_style_title') or no trustworthy English text in either
    field (reason 'non_english_content'). A patent is excluded when it has no
    usable title ('no_usable_text') or a version-style title
    ('version_style_title'). Everything else is kept (embedded downstream).
    """
    excluded: list[dict[str, str]] = []
    for work_id, title, abstract in paper_rows:
        if resolve_paper_text(title, abstract) is not None:
            continue
        reason = (
            "version_style_title"
            if is_version_style_title(title)
            else "non_english_content"
        )
        excluded.append({"doc_id": work_id, "doc_type": "paper", "exclusion_reason": reason})
    for patent_id, title in patent_rows:
        if not title:
            excluded.append(
                {"doc_id": patent_id, "doc_type": "patent", "exclusion_reason": "no_usable_text"}
            )
        elif is_version_style_title(title):
            excluded.append(
                {"doc_id": patent_id, "doc_type": "patent",
                 "exclusion_reason": "version_style_title"}
            )
    return excluded


# ---------------------------------------------------------------------------
# Private write helper (stage-then-promote, same pattern as the other ML assets)
# ---------------------------------------------------------------------------


def _write_df_to_r2(
    df: pl.DataFrame,
    r2_path: str,
    bucket: str,
    duckdb_resource: DuckDBR2Resource,
    r2_resource: R2Resource,
) -> None:
    staging_r2 = f"{r2_path}.staging"
    staging_key = staging_r2.removeprefix(f"r2://{bucket}/")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        df.write_parquet(tmp)
        with duckdb_resource.get_connection() as con:
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{tmp.as_posix()}')) "
                f"TO '{staging_r2}' (FORMAT PARQUET)"
            )
    finally:
        tmp.unlink(missing_ok=True)

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


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="ml",
    deps=["openalex_works_raw", "patents_scoped"],
    description=(
        "The pre-staging quality gate: screens out documents entirely (version-style "
        "title, non-English paper, or patent with no usable title) by reading the RAW "
        "scope corpus and running the same gate the embedding step used to. Runs BEFORE "
        "staging, which applies the list (stg_* NOT IN excluded_documents) — this is what "
        "breaks the old staging↔ML cycle. "
        "Depends on: R2 raw/openalex/works.parquet, raw/patentsview/patents_scoped. "
        "Output: r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet"
    ),
)
def document_exclusions(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    """Compute and write the excluded-documents list from the raw scope corpus.

    Depends on: R2 raw openalex works + patentsview patents_scoped parquet.
    Output: r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet
    """
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    r2_path = (
        f"r2://{bucket}/intermediate/excluded_documents/v{snapshot_date}/excluded_documents.parquet"
    )

    # Idempotency: skip if today's snapshot already exists.
    with duckdb.get_connection() as con:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{r2_path}')").fetchone()
            existing: int | None = n[0] if n else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info("Snapshot %s exists (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    # Locate the latest raw snapshots (the corpus the gate screens).
    with duckdb.get_connection() as con:
        oa_rows = con.execute(
            f"SELECT file FROM glob('r2://{bucket}/raw/openalex/*/works.parquet') "
            "ORDER BY file DESC LIMIT 1"
        ).fetchall()
        pv_rows = con.execute(
            f"SELECT file FROM glob('r2://{bucket}/raw/patentsview/patents_scoped/*/"
            "patents_scoped.parquet') ORDER BY file DESC LIMIT 1"
        ).fetchall()
        if not oa_rows:
            raise RuntimeError(f"No raw openalex works found at r2://{bucket}/raw/openalex/.")
        if not pv_rows:
            raise RuntimeError(
                f"No raw patents_scoped found at r2://{bucket}/raw/patentsview/patents_scoped/."
            )
        oa_path, pv_path = oa_rows[0][0], pv_rows[0][0]
        context.log.info("Raw openalex: %s", oa_path)
        context.log.info("Raw patents_scoped: %s", pv_path)

        # work_id is extracted with the SAME regexp staging uses, so exclusion
        # doc_ids match the doc_ids staging filters on.
        paper_rows: list[tuple[str, str, str]] = con.execute(
            "SELECT regexp_extract(openalex_id, 'W([0-9]+)', 0), "
            "COALESCE(title, ''), COALESCE(abstract, '') "
            f"FROM read_parquet('{oa_path}') WHERE openalex_id IS NOT NULL"
        ).fetchall()
        patent_rows: list[tuple[str, str]] = con.execute(
            "SELECT patent_id, COALESCE(patent_title, '') "
            f"FROM read_parquet('{pv_path}') WHERE patent_id IS NOT NULL"
        ).fetchall()

    context.log.info(
        "Screening %s papers + %s patents…", f"{len(paper_rows):,}", f"{len(patent_rows):,}"
    )
    excluded = compute_exclusions(paper_rows, patent_rows)
    n_paper_excl = sum(1 for d in excluded if d["doc_type"] == "paper")
    n_patent_excl = sum(1 for d in excluded if d["doc_type"] == "patent")
    context.log.info(
        "Excluded %s docs (%s papers, %s patents).",
        f"{len(excluded):,}", f"{n_paper_excl:,}", f"{n_patent_excl:,}",
    )

    df = pl.DataFrame(
        {
            "doc_id": [d["doc_id"] for d in excluded],
            "doc_type": [d["doc_type"] for d in excluded],
            "exclusion_reason": [d["exclusion_reason"] for d in excluded],
            "model_version": [_GATE_VERSION] * len(excluded),
        },
        schema={
            "doc_id": pl.String,
            "doc_type": pl.String,
            "exclusion_reason": pl.String,
            "model_version": pl.String,
        },
    )
    _write_df_to_r2(df, r2_path, bucket, duckdb, r2)
    context.log.info("Written %s rows → %s", f"{len(df):,}", r2_path)

    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "total_excluded": len(df),
            "n_papers_excluded": n_paper_excl,
            "n_patents_excluded": n_patent_excl,
            "r2_path": r2_path,
        }
    )
