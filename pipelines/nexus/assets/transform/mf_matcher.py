"""Marx & Fuegi ("Reliance on Science") NPL link source.

Marx & Fuegi is a peer-reviewed, published dataset of patent-to-paper
citations (CC-BY-4.0, Zenodo record 7996195). It was originally used in this
project only as a quality benchmark for our own DOI + fuzzy-title matcher
(see npl_matcher.py, ref_npl_gold_eval). A measured comparison
(docs/data_source_manifest.md) showed it dominates our matcher on coverage
and link quality for the patents it covers, so it is now also a *source* of
fact_npl_link edges, not just a grading rubric.

Coverage ceiling: the dataset's vintage caps out around patents granted
~early 2023 (max granted-patent number ~11.6M in the raw file) -- patents
granted after that have zero M&F coverage. fact_npl_link.sql implements the
hybrid seam: for any patent M&F covers at all, ALL of that patent's edges
come from M&F; the custom npl_matcher only fills patents M&F has zero
coverage of (see fact_npl_link.sql for the seam and
assert_fact_npl_link_single_source.sql for the invariant that guards it).

Output: r2://p2p-lake/intermediate/mf_npl/v{date}/mf_npl_links.parquet
Schema: patent_id, work_id, match_method, confidence, wherefound, confscore, self
"""

import datetime
import os
import pathlib
import tempfile
from typing import Any

import polars as pl
from dagster import AssetKey, OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource
from nexus.resources.warehouse import connect_warehouse

_MF_CSV = pathlib.Path("data") / "reference" / "marx_fuegi_pcs.csv"


# ---------------------------------------------------------------------------
# Pure helpers -- independently testable
# ---------------------------------------------------------------------------


def mf_confidence(wherefound: str) -> str:
    """Map Marx & Fuegi's citation-location flag to this project's confidence tier.

    front/both: the citation appears on the patent's printed front page --
    the citation an examiner or applicant explicitly listed. high confidence.
    body: found only via Marx & Fuegi's separate in-text full-text extraction
    method, which their own methodology documents as lower-precision than the
    front-page route. medium confidence.
    """
    return "high" if wherefound in ("front", "both") else "medium"


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="transform",
    deps=[
        AssetKey(["staging", "stg_patents_scoped"]),
        AssetKey(["staging", "stg_openalex_works"]),
    ],
    description=(
        "Marx & Fuegi 'Reliance on Science' NPL links, filtered to scope patents "
        "and our OpenAlex corpus. Primary NPL source for patents it covers "
        "(vintage caps ~early-2023 grants); fact_npl_link.sql falls back to "
        "npl_links_raw's matcher output for patents outside that coverage. "
        "Output: r2://p2p-lake/intermediate/mf_npl/v{date}/mf_npl_links.parquet. "
        "Depends on dbt staging models (stg_patents_scoped, stg_openalex_works) "
        "in dev.duckdb."
    ),
)
def mf_npl_links(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    r2_path = f"r2://{bucket}/intermediate/mf_npl/v{snapshot_date}/mf_npl_links.parquet"

    # Idempotency: skip if snapshot already written today
    with duckdb.get_connection() as con:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{r2_path}')").fetchone()
            existing = n[0] if n else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info("Snapshot %s exists (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    dev_con = connect_warehouse(read_only=True)
    try:
        mf_path = str(_MF_CSV.resolve())
        context.log.info("Scoping Marx & Fuegi CSV (%s)…", mf_path)
        rows = dev_con.execute(f"""
            with mf as (
                select
                    regexp_extract(patent, '^us-([0-9]+)-', 1) as patent_id,
                    'W' || cast(oaid as varchar)                as work_id,
                    wherefound,
                    confscore::integer                          as confscore,
                    self
                from read_csv('{mf_path}', header = true)
            ),
            scoped as (
                select distinct patent_id, work_id, wherefound, confscore, self
                from mf
                where patent_id != ''
                  and patent_id in (select patent_id from main_staging.stg_patents_scoped)
                  and work_id    in (select work_id    from main_staging.stg_openalex_works)
            ),
            ranked as (
                select *,
                    row_number() over (
                        partition by patent_id, work_id
                        order by
                            case wherefound when 'both' then 0 when 'front' then 1 else 2 end,
                            confscore desc
                    ) as rnk
                from scoped
            )
            select patent_id, work_id, wherefound, confscore, self
            from ranked
            where rnk = 1
        """).fetchall()
    finally:
        dev_con.close()

    context.log.info("Marx & Fuegi links in scope ∩ corpus: %s.", f"{len(rows):,}")

    records: list[dict[str, Any]] = [
        {
            "patent_id": patent_id,
            "work_id": work_id,
            "match_method": "npl_citation",
            "confidence": mf_confidence(wherefound),
            "wherefound": wherefound,
            "confscore": confscore,
            "self": self_flag,
        }
        for patent_id, work_id, wherefound, confscore, self_flag in rows
    ]
    final_df = pl.DataFrame(
        records,
        schema={
            "patent_id": pl.String,
            "work_id": pl.String,
            "match_method": pl.String,
            "confidence": pl.String,
            "wherefound": pl.String,
            "confscore": pl.Int64,
            "self": pl.String,
        },
    )

    # Write to R2 via stage-then-promote
    staging_r2 = f"{r2_path}.staging"
    staging_key = staging_r2.removeprefix(f"r2://{bucket}/")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        final_df.write_parquet(tmp)
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

    context.log.info("Written %s links → %s", f"{len(final_df):,}", r2_path)
    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "total_links": len(final_df),
            "distinct_patents": final_df["patent_id"].n_unique() if len(final_df) else 0,
            "r2_path": r2_path,
        }
    )
