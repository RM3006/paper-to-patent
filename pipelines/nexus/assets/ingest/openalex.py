"""OpenAlex ingestion asset.

Paginates the OpenAlex /works endpoint filtered to scope topic IDs and the
2012-2025 year window. Reconstructs abstracts from the inverted index.
Writes a single Parquet snapshot to R2 using a stage-then-promote pattern
so a failed run never destroys an existing good snapshot.

Output: r2://p2p-lake/raw/openalex/v{snapshot_date}/works.parquet
"""

import datetime
import os
import pathlib
import tempfile
import time
from collections.abc import Iterator
from typing import Any, cast

import httpx
import polars as pl
from dagster import OpExecutionContext, asset

from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

# ---------------------------------------------------------------------------
# Scope constants — mirror of ROADMAP Part 0 scope contract
# ---------------------------------------------------------------------------

SCOPE_TOPIC_IDS: list[str] = ["T11338", "T10299", "T11429", "T10502"]

_PUB_YEAR_FILTER = "2012-2025"
_BASE_URL = "https://api.openalex.org"
_PAGE_SIZE = 200
_INTER_PAGE_SLEEP_S = 0.2
_MAX_RETRIES = 3
_RETRY_BASE_S = 10
MAX_RETRY_WAIT_S = 120  # refuse to sleep longer than this; surface the rate-limit instead


# ---------------------------------------------------------------------------
# Pure helpers (tested in isolation)
# ---------------------------------------------------------------------------


def reconstruct_abstract(inverted_index: dict[str, list[int]]) -> str:
    """Reconstruct an abstract string from OpenAlex's inverted index format.

    The inverted index maps each token to its list of positions. Gaps are
    preserved as empty strings so position semantics are not lost.
    """
    if not inverted_index:
        return ""
    max_pos = max(pos for positions in inverted_index.values() for pos in positions)
    tokens: list[str] = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            tokens[pos] = word
    return " ".join(tokens)


def parse_work(work: dict[str, Any]) -> dict[str, Any]:
    """Flatten one OpenAlex work API record into a storable dict."""
    inv_index: dict[str, list[int]] = work.get("abstract_inverted_index") or {}

    institution_ids: list[str] = []
    institution_rors: list[str] = []
    authorships = cast(list[dict[str, Any]], work.get("authorships") or [])
    for authorship in authorships:
        institutions = cast(list[dict[str, Any]], authorship.get("institutions") or [])
        for inst in institutions:
            if inst_id := cast(str | None, inst.get("id")):
                institution_ids.append(inst_id)
            if ror := cast(str | None, inst.get("ror")):
                institution_rors.append(ror)

    primary_topic: dict[str, Any] = work.get("primary_topic") or {}

    return {
        "openalex_id": work.get("id", ""),
        "doi": work.get("doi"),
        "title": work.get("title"),
        "publication_date": work.get("publication_date"),
        "publication_year": work.get("publication_year"),
        "language": work.get("language"),
        "abstract": reconstruct_abstract(inv_index) if inv_index else None,
        "primary_topic_id": primary_topic.get("id"),
        "primary_topic_name": primary_topic.get("display_name"),
        "institution_ids": institution_ids,
        "institution_rors": institution_rors,
    }


def paginate_works(
    client: httpx.Client,
    filter_str: str,
    mailto: str,
) -> Iterator[dict[str, Any]]:
    """Yield individual work dicts from the OpenAlex /works cursor page."""
    headers = {"User-Agent": f"paper-to-patent/0.1 (mailto:{mailto})"}
    select_fields = (
        "id,doi,title,publication_date,publication_year,language,"
        "abstract_inverted_index,primary_topic,authorships"
    )
    cursor: str | None = "*"

    while cursor is not None:
        for attempt in range(_MAX_RETRIES):
            resp = client.get(
                f"{_BASE_URL}/works",
                params={
                    "filter": filter_str,
                    "per-page": str(_PAGE_SIZE),
                    "cursor": cursor,
                    "select": select_fields,
                },
                headers=headers,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", _RETRY_BASE_S * (2**attempt)))
                if wait > MAX_RETRY_WAIT_S:
                    raise RuntimeError(
                        f"OpenAlex rate-limited for {wait}s (Retry-After header). "
                        "Wait for the cooldown to expire then re-run the asset."
                    )
                logger.warning("OpenAlex 429; retrying in %ds (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            raise RuntimeError(f"OpenAlex 429 after {_MAX_RETRIES} retries; giving up.")

        data: dict[str, Any] = resp.json()
        results: list[Any] = data.get("results") or []
        yield from results

        meta: dict[str, Any] = data.get("meta") or {}
        cursor = meta.get("next_cursor")
        if cursor is not None:
            time.sleep(_INTER_PAGE_SLEEP_S)


def delete_r2_object(account_id: str, api_token: str, bucket: str, key: str) -> None:
    """Delete one R2 object via the Cloudflare REST API. 404 is treated as success."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/r2/buckets/{bucket}/objects/{key}"
    )
    resp = httpx.delete(url, headers={"Authorization": f"Bearer {api_token}"}, timeout=30)
    if resp.status_code not in (200, 204, 404):
        raise RuntimeError(
            f"Failed to delete R2 object '{key}': {resp.status_code} {resp.text[:200]}"
        )


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="ingest",
    description=(
        "Paginates the OpenAlex /works endpoint filtered to scope topic IDs "
        f"({', '.join(SCOPE_TOPIC_IDS)}) and publication years {_PUB_YEAR_FILTER}, "
        "with language:en and has_abstract:true. Reconstructs abstracts from the "
        "inverted index. Keeps institution IDs and ROR. "
        "Output: r2://p2p-lake/raw/openalex/v{snapshot_date}/works.parquet"
    ),
)
def openalex_works_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    r2_path = f"r2://{r2.bucket}/raw/openalex/v{snapshot_date}/works.parquet"

    # Idempotency: skip if this snapshot already exists
    with duckdb.get_connection() as con:
        try:
            existing = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{r2_path}')"
            ).fetchone()
            count = existing[0] if existing else 0
            context.log.info(f"Snapshot already at {r2_path} ({count:,} rows). Skipping.")
            return
        except Exception:
            pass  # File not found — proceed with download

    mailto = os.environ.get("OPENALEX_MAILTO", "")
    if not mailto:
        raise RuntimeError("OPENALEX_MAILTO env var is not set")

    topic_filter = "|".join(f"https://openalex.org/{t}" for t in SCOPE_TOPIC_IDS)
    filter_str = (
        f"primary_topic.id:{topic_filter},"
        f"publication_year:{_PUB_YEAR_FILTER},"
        "language:en,"
        "has_abstract:true"
    )

    logger.info("Starting OpenAlex pagination — filter: %s", filter_str)
    records: list[dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        for i, work in enumerate(paginate_works(client, filter_str, mailto)):
            records.append(parse_work(work))
            if (i + 1) % 5000 == 0:
                context.log.info(f"Fetched {i + 1:,} works so far…")

    context.log.info(f"Pagination complete: {len(records):,} works. Writing to {r2_path}")

    df = pl.DataFrame(records)
    staging_path = f"{r2_path}.staging"
    staging_key = f"raw/openalex/v{snapshot_date}/works.parquet.staging"

    # Stage: polars → local temp → R2 staging (old final untouched if this fails)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        df.write_parquet(tmp)
        with duckdb.get_connection() as con:
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{tmp.as_posix()}')) "
                f"TO '{staging_path}' (FORMAT PARQUET)"
            )
    finally:
        tmp.unlink(missing_ok=True)

    # Promote: staging → final (window where no good data exists is just this COPY)
    context.log.info("Staging complete. Promoting to final path.")
    with duckdb.get_connection() as con:
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{staging_path}')) "
            f"TO '{r2_path}' (FORMAT PARQUET)"
        )

    # Clean up staging
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if api_token:
        delete_r2_object(r2.account_id, api_token, r2.bucket, staging_key)
    else:
        logger.warning("CLOUDFLARE_API_TOKEN not set; staging file left in R2: %s", staging_key)

    context.log.info(f"Written {len(records):,} rows -> {r2_path}")
    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "row_count": len(records),
            "r2_path": r2_path,
        }
    )
