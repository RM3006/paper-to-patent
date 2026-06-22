"""Entity resolution — Layer 3: fuzzy cross-source bridge.

Matches unmatched OpenAlex institutions against PatentsView assignees by
normalized-name similarity (rapidfuzz token_set_ratio). Blocks on the first
token of the normalized name to keep comparisons tractable.

Threshold: score must equal 100 to be accepted. token_set_ratio = 100 means
one string's token set is a strict subset of the other's — the only safe form
of matching for institution names that share structural tokens ("University of X"
vs "University of Y" would score ~89 and is correctly excluded).

Output: one row per (institution_id, assignee_id) pair that scored 100.
  match_method="fuzzy_high", confidence="high" (no fuzzy_review band).

Output: r2://p2p-lake/intermediate/er/fuzzy_org_bridge/v{date}/fuzzy_org_bridge.parquet
"""

import datetime
import os
import pathlib
import tempfile

import polars as pl
from dagster import OpExecutionContext, asset
from rapidfuzz import fuzz

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

HIGH_THRESHOLD = 100
REVIEW_THRESHOLD = 100


# ---------------------------------------------------------------------------
# Pure function — testable without R2
# ---------------------------------------------------------------------------


def build_fuzzy_bridge(
    pv_staging: pl.DataFrame,
    oa_staging: pl.DataFrame,
    high_threshold: int = HIGH_THRESHOLD,
    review_threshold: int = REVIEW_THRESHOLD,
) -> pl.DataFrame:
    """Cross-source fuzzy match: OpenAlex institutions → PatentsView assignees.

    For each OA institution, finds the best-scoring PV assignee in the same
    first-token block. Emits one row per (institution_id, assignee_id) pair
    that scores ≥ review_threshold. If multiple PV orgs tie at the top score,
    the one with the lexicographically smallest assignee_id wins (deterministic).

    Input DataFrames must have columns:
      pv_staging  : assignee_id, normalized_name
      oa_staging  : institution_id, normalized_name

    Output columns:
      institution_id, assignee_id, similarity, match_method, confidence
    """
    _EMPTY_SCHEMA = {
        "institution_id": pl.String,
        "assignee_id": pl.String,
        "similarity": pl.Float64,
        "match_method": pl.String,
        "confidence": pl.String,
    }

    if pv_staging.is_empty() or oa_staging.is_empty():
        return pl.DataFrame(schema=_EMPTY_SCHEMA)

    # Build blocking index: first_token → [(normalized_name, assignee_id), ...]
    pv_index: dict[str, list[tuple[str, str]]] = {}
    for row in pv_staging.iter_rows(named=True):
        norm: str = row["normalized_name"] or ""
        if not norm:
            continue
        first = norm.split()[0]
        pv_index.setdefault(first, []).append((norm, row["assignee_id"]))

    records: list[tuple[str, str, float, str, str]] = []
    for row in oa_staging.iter_rows(named=True):
        norm = row["normalized_name"] or ""
        if not norm:
            continue
        first = norm.split()[0]
        candidates = pv_index.get(first, [])
        if not candidates:
            continue

        best_score = 0.0
        best_assignee = ""
        for pv_norm, pv_id in candidates:
            score = float(fuzz.token_set_ratio(norm, pv_norm))
            if score > best_score or (score == best_score and pv_id < best_assignee):
                best_score = score
                best_assignee = pv_id

        if best_score >= high_threshold:
            method, conf = "fuzzy_high", "high"
        elif best_score >= review_threshold:
            method, conf = "fuzzy_review", "medium"
        else:
            continue

        records.append((row["institution_id"], best_assignee, best_score, method, conf))

    if not records:
        return pl.DataFrame(schema=_EMPTY_SCHEMA)

    return pl.DataFrame(
        records,
        schema=["institution_id", "assignee_id", "similarity", "match_method", "confidence"],
        orient="row",
    )


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=["patentsview_orgs_staging", "openalex_institutions_staging"],
    description=(
        "Layer 3 ER: fuzzy cross-source bridge. Matches OpenAlex institutions against "
        "PatentsView assignees via rapidfuzz token_set_ratio, blocking on the first "
        "token of normalized_name. Only score=100 (exact/subset token match) accepted "
        "→ fuzzy_high/high. Scores below 100 are excluded to avoid false positives from "
        "shared structural tokens (e.g. 'University of X' vs 'University of Y'). "
        "Output: r2://p2p-lake/intermediate/er/fuzzy_org_bridge/v{date}/fuzzy_org_bridge.parquet"
    ),
)
def fuzzy_org_bridge(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"fuzzy_org_bridge/v{snapshot_date}/fuzzy_org_bridge.parquet"
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
    oa_glob = f"r2://{bucket}/intermediate/er/openalex_institutions_staging/*/*.parquet"

    with duckdb.get_connection() as con:
        pv_rows = con.execute(
            f"SELECT assignee_id, normalized_name FROM read_parquet('{pv_glob}')"
        ).fetchall()
        oa_rows = con.execute(
            f"SELECT institution_id, normalized_name FROM read_parquet('{oa_glob}')"
        ).fetchall()

    pv_df = pl.DataFrame(pv_rows, schema=["assignee_id", "normalized_name"], orient="row")
    oa_df = pl.DataFrame(oa_rows, schema=["institution_id", "normalized_name"], orient="row")

    context.log.info(
        "Running fuzzy bridge: %s PV orgs × %s OA institutions (blocked).",
        f"{len(pv_df):,}",
        f"{len(oa_df):,}",
    )
    df = build_fuzzy_bridge(pv_df, oa_df)
    high = (df["match_method"] == "fuzzy_high").sum()
    review = (df["match_method"] == "fuzzy_review").sum()
    context.log.info(
        "Fuzzy bridge: %s fuzzy_high, %s fuzzy_review.", f"{high:,}", f"{review:,}"
    )
    if review > 0:
        context.log.warning(
            "%s fuzzy_review rows need manual resolution before assembly.", f"{review:,}"
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
            "total_rows": len(df),
            "fuzzy_high_count": int(high),
            "fuzzy_review_count": int(review),
            "r2_path": r2_path,
        }
    )
