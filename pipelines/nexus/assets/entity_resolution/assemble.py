"""Entity resolution — final assembly: int_organization_crosswalk.

Combines all ER layers into a single long-format crosswalk table. Each row
maps one (source, source_id) pair to an org_id with provenance metadata.

Layers (applied in priority order):
  1. seed_crosswalk_matched  — PatentsView assignee → known org_id
  2. fuzzy_org_bridge        — OpenAlex institution → org_id via PV fuzzy match
  3. Native fallback         — remaining PV assignees get org_id from assignee_id slug
  4. OA-only fallback        — unmatched OA institutions get org_id from institution slug

Output schema:
  org_id         — canonical identifier (slug: "org_tsmc", "org_pv_…", "org_oa_…")
  source         — "patentsview" | "openalex"
  source_id      — assignee_id (PV) | institution_id (OA)
  canonical_name — human-readable org name
  match_method   — native_id | seed_crosswalk | fuzzy_high | ror
  confidence     — high | medium | low

Output: r2://p2p-lake/intermediate/er/org_crosswalk/v{date}/org_crosswalk.parquet
"""

import datetime
import os
import pathlib
import re
import tempfile

import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_tokens: int = 4) -> str:
    tokens = text.lower().split()[:max_tokens]
    return _SLUG_RE.sub("_", "_".join(tokens)).strip("_")


# ---------------------------------------------------------------------------
# Pure function — testable without R2
# ---------------------------------------------------------------------------


def build_org_crosswalk(
    seed_matched: pl.DataFrame,
    seed_oa_matched: pl.DataFrame,
    ror_bridge: pl.DataFrame,
    fuzzy_bridge: pl.DataFrame,
    pv_staging: pl.DataFrame,
    oa_staging: pl.DataFrame,
) -> pl.DataFrame:
    """Assemble int_organization_crosswalk from all ER layers.

    Priority:
      1. seed_crosswalk_matched    → PV rows with known org_ids
      2. seed_crosswalk_oa_matched → OA rows with explicit institution IDs in the seed CSV
      3. ror_bridge                → OA rows found via OpenAlex API (acronym/full-name gap)
      4. fuzzy_org_bridge          → OA rows matched to a PV org via name similarity
      5. PV fallback               → remaining PV assignees, org_id from normalized name slug
      6. OA fallback               → remaining OA institutions, org_id from normalized name slug

    Input schemas:
      seed_matched    : org_id, canonical_name, assignee_id, display_name, match_method, confidence
      seed_oa_matched : org_id, canonical_name, institution_id, display_name,
                        match_method, confidence
      ror_bridge      : org_id, institution_id, display_name, match_method, confidence
      fuzzy_bridge    : institution_id, assignee_id, similarity, match_method, confidence
      pv_staging      : assignee_id, display_name, normalized_name, match_method, confidence
      oa_staging      : institution_id, display_name, normalized_name, match_method, confidence
    """
    _SCHEMA = {
        "org_id": pl.String,
        "source": pl.String,
        "source_id": pl.String,
        "canonical_name": pl.String,
        "match_method": pl.String,
        "confidence": pl.String,
    }

    rows: list[tuple[str, str, str, str, str, str]] = []

    # ── Layer 1: seed crosswalk PatentsView rows ──────────────────────────
    # Build lookup: assignee_id → (org_id, canonical_name)
    seed_pv_lookup: dict[str, tuple[str, str]] = {}
    for r in seed_matched.iter_rows(named=True):
        seed_pv_lookup[r["assignee_id"]] = (r["org_id"], r["canonical_name"])
        rows.append((
            r["org_id"], "patentsview", r["assignee_id"],
            r["canonical_name"], r["match_method"], r["confidence"],
        ))

    seeded_pv_ids = set(seed_pv_lookup)

    # ── Layer 2a: seed OA matches (explicit institution_id in seed CSV) ───
    matched_oa_ids: set[str] = set()
    for r in seed_oa_matched.iter_rows(named=True):
        inst_id: str = r["institution_id"]
        rows.append((
            r["org_id"], "openalex", inst_id,
            r["display_name"], r["match_method"], r["confidence"],
        ))
        matched_oa_ids.add(inst_id)

    # ── Layer 2b: ROR bridge → OA institutions found via OpenAlex API ────
    for r in ror_bridge.iter_rows(named=True):
        inst_id: str = r["institution_id"]
        if inst_id in matched_oa_ids:
            continue
        rows.append((
            r["org_id"], "openalex", inst_id,
            r["display_name"], r["match_method"], r["confidence"],
        ))
        matched_oa_ids.add(inst_id)

    # ── Layer 2c: fuzzy bridge → OA institutions matched to PV orgs ──────
    # If the matched PV assignee is in seed, inherit the org_id.
    # If not, generate one from the PV assignee's normalized name.
    pv_norm_lookup: dict[str, str] = {
        r["assignee_id"]: r["normalized_name"]
        for r in pv_staging.iter_rows(named=True)
    }
    pv_display_lookup: dict[str, str] = {
        r["assignee_id"]: r["display_name"]
        for r in pv_staging.iter_rows(named=True)
    }
    oa_display_lookup: dict[str, str] = {
        r["institution_id"]: r["display_name"]
        for r in oa_staging.iter_rows(named=True)
    }

    fuzzy_generated_pv: dict[str, str] = {}  # assignee_id → generated org_id

    for r in fuzzy_bridge.iter_rows(named=True):
        inst_id: str = r["institution_id"]
        if inst_id in matched_oa_ids:
            continue  # already claimed by seed OA match
        asgn_id: str = r["assignee_id"]
        method: str = r["match_method"]
        conf: str = r["confidence"]

        if asgn_id in seed_pv_lookup:
            org_id, _ = seed_pv_lookup[asgn_id]
        else:
            # Generate a stable org_id for this PV assignee (not in seed)
            if asgn_id not in fuzzy_generated_pv:
                norm = pv_norm_lookup.get(asgn_id, asgn_id)
                fuzzy_generated_pv[asgn_id] = f"org_pv_{_slugify(norm)}"
                # Emit the PV row for this assignee too (not emitted by seed)
                rows.append((
                    fuzzy_generated_pv[asgn_id],
                    "patentsview",
                    asgn_id,
                    pv_display_lookup.get(asgn_id, asgn_id),
                    method,
                    conf,
                ))
            org_id = fuzzy_generated_pv[asgn_id]

        rows.append((
            org_id, "openalex", inst_id,
            oa_display_lookup.get(inst_id, inst_id), method, conf,
        ))
        matched_oa_ids.add(inst_id)

    fuzzy_matched_pv = set(fuzzy_generated_pv)

    # ── Layer 3: PV fallback — assignees not in seed or fuzzy-generated ──
    for r in pv_staging.iter_rows(named=True):
        asgn_id = r["assignee_id"]
        if asgn_id in seeded_pv_ids or asgn_id in fuzzy_matched_pv:
            continue
        org_id = f"org_pv_{_slugify(r['normalized_name'])}"
        rows.append((
            org_id, "patentsview", asgn_id,
            r["display_name"], "native_id", "high",
        ))

    # ── Layer 4: OA fallback — institutions not matched by fuzzy bridge ──
    for r in oa_staging.iter_rows(named=True):
        inst_id = r["institution_id"]
        if inst_id in matched_oa_ids:
            continue
        slug = _slugify(r["normalized_name"]) or _slugify(inst_id.split("/")[-1])
        org_id = f"org_oa_{slug}"
        rows.append((
            org_id, "openalex", inst_id,
            r["display_name"], "ror", "high",
        ))

    if not rows:
        return pl.DataFrame(schema=_SCHEMA)

    df = pl.DataFrame(rows, schema=list(_SCHEMA.keys()), orient="row")
    # Deduplicate: same (source, source_id) should only appear once (seed wins over fuzzy)
    return df.unique(subset=["source", "source_id"], keep="first")  # type: ignore[reportUnknownMemberType]


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=[
        "seed_crosswalk_matched",
        "seed_crosswalk_oa_matched",
        "ror_bridge",
        "fuzzy_org_bridge",
        "patentsview_orgs_staging",
        "openalex_institutions_staging",
    ],
    description=(
        "Final ER assembly: int_organization_crosswalk. Unions seed crosswalk (PV+OA), "
        "ROR bridge (API-matched OA rows), fuzzy bridge (name-similarity OA rows), "
        "and fallback rows for unmatched entities. "
        "Long format: one row per (source, source_id) with org_id, canonical_name, "
        "match_method, confidence. "
        "Output: r2://p2p-lake/intermediate/er/org_crosswalk/v{date}/org_crosswalk.parquet"
    ),
)
def org_crosswalk(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"org_crosswalk/v{snapshot_date}/org_crosswalk.parquet"
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

    def _read(glob: str) -> pl.DataFrame:
        with duckdb.get_connection() as con:
            rows = con.execute(f"SELECT * FROM read_parquet('{glob}')").fetchall()
            cols = [d[0] for d in con.description or []]
        return pl.DataFrame(rows, schema=cols, orient="row") if rows else pl.DataFrame()

    seed_df = _read(
        f"r2://{bucket}/intermediate/er/seed_crosswalk_matched/*/*.parquet"
    )
    seed_oa_df = _read(
        f"r2://{bucket}/intermediate/er/seed_crosswalk_oa_matched/*/*.parquet"
    )
    ror_df = _read(
        f"r2://{bucket}/intermediate/er/ror_bridge/*/*.parquet"
    )
    fuzzy_df = _read(
        f"r2://{bucket}/intermediate/er/fuzzy_org_bridge/*/*.parquet"
    )
    pv_df = _read(
        f"r2://{bucket}/intermediate/er/patentsview_orgs_staging/*/*.parquet"
    )
    oa_df = _read(
        f"r2://{bucket}/intermediate/er/openalex_institutions_staging/*/*.parquet"
    )

    _review_series = fuzzy_df["match_method"] == "fuzzy_review"  # type: ignore[reportUnknownMemberType]
    review_count = int(_review_series.sum()) if not fuzzy_df.is_empty() else 0
    if review_count > 0:
        context.log.warning(
            "%s fuzzy_review rows present — resolve these before using the crosswalk for "
            "analytical queries. They are included but flagged with confidence='medium'.",
            f"{review_count:,}",
        )

    df = build_org_crosswalk(seed_df, seed_oa_df, ror_df, fuzzy_df, pv_df, oa_df)
    context.log.info(
        "Crosswalk: %s rows, %s distinct org_ids.",
        f"{len(df):,}",
        f"{df['org_id'].n_unique():,}",
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
            "org_id_count": df["org_id"].n_unique(),
            "review_count": review_count,
            "r2_path": r2_path,
        }
    )
