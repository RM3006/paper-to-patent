"""Entity resolution — Layer 3b: ROR bridge via OpenAlex Institutions API.

Targets orgs that have a PatentsView seed entry but no OpenAlex crosswalk entry.
The fuzzy bridge (Layer 3) cannot close this gap because PatentsView uses full
legal names ("International Business Machines Corporation") while OpenAlex uses
brand names ("IBM Research - Almaden") — different first-token blocks, never
compared.

For each PV-only org_id, queries the OpenAlex Institutions API and accepts all
returned institutions where every token in the org's canonical_name appears in
the institution's normalized display_name:

    {"ibm"} ⊆ {"ibm", "research", "almaden"}      → accept
    {"samsung", "display"} ⊆ {"samsung"}            → reject (parent ≠ child)
    {"samsung", "display"} ⊆ {"samsung", "display", "america"} → accept

Orgs are processed most-specific-first (descending token count) so that a
child org (Samsung Display, 2 tokens) claims its institutions before a parent
org (Samsung, 1 token) can absorb them.

match_method = 'ror_bridge', confidence = 'high'

Output: r2://p2p-lake/intermediate/er/ror_bridge/v{date}/ror_bridge.parquet
"""

import datetime
import json
import os
import pathlib
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.entity_resolution.normalize import normalize_org_name
from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

_OPENALEX_INSTITUTIONS_URL = "https://api.openalex.org/institutions"
_REQUEST_DELAY_S = 0.12  # stay comfortably within polite-pool rate limits

QueryFn = Callable[[str, str], list[dict[str, str]]]


# ---------------------------------------------------------------------------
# API call — isolated so tests can inject a mock
# ---------------------------------------------------------------------------


def query_openalex_institutions(name: str, mailto: str) -> list[dict[str, str]]:
    """Return up to 25 OpenAlex institution hits for name.

    Each hit is {"id": <openalex_url>, "display_name": <str>}.
    Returns [] on any network or parse error (logged, not raised).
    """
    params = urllib.parse.urlencode({"search": name, "per_page": "25", "mailto": mailto})
    url = f"{_OPENALEX_INSTITUTIONS_URL}?{params}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"paper-to-patent/1.0 mailto:{mailto}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data: dict[str, Any] = json.loads(resp.read())
        results = data.get("results", [])
        if not isinstance(results, list):
            return []
        out: list[dict[str, str]] = []
        for item in results:  # type: ignore[reportUnknownVariableType]
            if isinstance(item, dict) and "id" in item and "display_name" in item:
                out.append({"id": str(item["id"]), "display_name": str(item["display_name"])})  # type: ignore[reportUnknownArgumentType]
        return out
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("OpenAlex institutions query failed for %r: %s", name, exc)
        return []


# ---------------------------------------------------------------------------
# Pure helpers — testable without network or R2
# ---------------------------------------------------------------------------


def _tokens_match(canonical: str, display: str) -> bool:
    """True if every normalized token in canonical appears in display.

    {"ibm"} ⊆ {"ibm", "research", "almaden"} → True
    {"samsung", "display"} ⊆ {"samsung"} → False
    """
    c_tokens = set(normalize_org_name(canonical).split())
    d_tokens = set(normalize_org_name(display).split())
    return bool(c_tokens) and c_tokens.issubset(d_tokens)


def get_pv_only_orgs(
    seed_matched: pl.DataFrame,
    seed_oa_matched: pl.DataFrame,
    fuzzy_bridge: pl.DataFrame,
) -> list[dict[str, str]]:
    """Return seeded PV orgs that have no OpenAlex crosswalk entry yet.

    An org is 'covered' if it appears in seed_oa_matched (explicit OA seed)
    or if any of its assignee_ids appear in fuzzy_bridge (fuzzy-matched OA rows).
    Returns distinct {org_id, canonical_name} dicts.
    """
    covered: set[str] = set()

    if not seed_oa_matched.is_empty() and "org_id" in seed_oa_matched.columns:
        covered.update(seed_oa_matched["org_id"].to_list())

    if not fuzzy_bridge.is_empty() and not seed_matched.is_empty():
        asgn_to_org: dict[str, str] = {
            r["assignee_id"]: r["org_id"]
            for r in seed_matched.iter_rows(named=True)
        }
        for r in fuzzy_bridge.iter_rows(named=True):
            org = asgn_to_org.get(r["assignee_id"])
            if org:
                covered.add(org)

    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for r in seed_matched.iter_rows(named=True):
        org_id: str = r["org_id"]
        if org_id in covered or org_id in seen:
            continue
        seen.add(org_id)
        result.append({"org_id": org_id, "canonical_name": r["canonical_name"]})
    return result


def build_ror_bridge(
    pv_only_orgs: list[dict[str, str]],
    mailto: str,
    query_fn: QueryFn = query_openalex_institutions,
    request_delay_s: float = _REQUEST_DELAY_S,
) -> pl.DataFrame:
    """Query OpenAlex for each PV-only org and return matched institution rows.

    Processes orgs most-specific-first (descending canonical token count) so
    that child orgs claim their institutions before parent orgs can absorb them.

    Output schema: org_id, institution_id, display_name, match_method, confidence
    """
    _SCHEMA = {
        "org_id": pl.String,
        "institution_id": pl.String,
        "display_name": pl.String,
        "match_method": pl.String,
        "confidence": pl.String,
    }

    if not pv_only_orgs:
        return pl.DataFrame(schema=_SCHEMA)

    # Most-specific first: longer canonical names get priority
    ordered = sorted(
        pv_only_orgs,
        key=lambda r: len(normalize_org_name(r["canonical_name"]).split()),
        reverse=True,
    )

    claimed: set[str] = set()
    records: list[tuple[str, str, str, str, str]] = []

    for org in ordered:
        org_id = org["org_id"]
        canonical = org["canonical_name"]
        hits = query_fn(canonical, mailto)
        time.sleep(request_delay_s)

        for hit in hits:
            inst_id = hit["id"]
            if inst_id in claimed:
                continue
            if _tokens_match(canonical, hit["display_name"]):
                records.append((org_id, inst_id, hit["display_name"], "ror_bridge", "high"))
                claimed.add(inst_id)

    if not records:
        return pl.DataFrame(schema=_SCHEMA)

    return pl.DataFrame(
        records,
        schema=["org_id", "institution_id", "display_name", "match_method", "confidence"],
        orient="row",
    )


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="entity_resolution",
    deps=["seed_crosswalk_matched", "seed_crosswalk_oa_matched", "fuzzy_org_bridge"],
    description=(
        "Layer 3b ER: ROR bridge via OpenAlex Institutions API. For each seeded org "
        "that has a PatentsView entry but no OpenAlex entry, queries the OpenAlex "
        "Institutions API and accepts institutions whose display_name tokens are a "
        "superset of the org's canonical_name tokens (subset match, not fuzzy). "
        "Closes the acronym/full-name blocking gap (e.g. 'International Business "
        "Machines Corporation' vs 'IBM Research - Almaden'). "
        "match_method='ror_bridge', confidence='high'. "
        "Output: r2://p2p-lake/intermediate/er/ror_bridge/v{date}/ror_bridge.parquet"
    ),
)
def ror_bridge(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = (
        f"r2://{r2.bucket}/intermediate/er/"
        f"ror_bridge/v{snapshot_date}/ror_bridge.parquet"
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

    seed_df = _read(f"r2://{bucket}/intermediate/er/seed_crosswalk_matched/*/*.parquet")
    seed_oa_df = _read(f"r2://{bucket}/intermediate/er/seed_crosswalk_oa_matched/*/*.parquet")
    fuzzy_df = _read(f"r2://{bucket}/intermediate/er/fuzzy_org_bridge/*/*.parquet")

    pv_only = get_pv_only_orgs(seed_df, seed_oa_df, fuzzy_df)
    context.log.info(
        "%s PV-only orgs to query against OpenAlex Institutions API.", len(pv_only)
    )

    mailto = os.environ.get("OPENALEX_MAILTO", "romain.menant7@gmail.com")
    df = build_ror_bridge(pv_only, mailto)

    context.log.info(
        "ROR bridge: %s institution rows across %s org_ids.",
        f"{len(df):,}",
        f"{df['org_id'].n_unique():,}" if not df.is_empty() else "0",
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
            "pv_only_orgs_queried": len(pv_only),
            "org_ids_resolved": int(df["org_id"].n_unique()) if not df.is_empty() else 0,
            "r2_path": r2_path,
        }
    )
