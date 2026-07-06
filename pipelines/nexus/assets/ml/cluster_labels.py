"""Cluster labelling asset for Part 5 — Claude Haiku-generated technology family names.

Reads cluster_terms.parquet (top c-TF-IDF terms per cluster) from R2, samples
representative document titles, and calls Claude Haiku to generate a human-readable
tagline and plain-English summary_friendly for each cluster. The noise cluster
receives a fixed label with no API call.

Prompt rule: name and describe using ONLY the supplied terms and titles; invent nothing.

Input:   R2 intermediate/cluster_terms/ (from document_clusters)
         R2 intermediate/clusters/ (for representative doc titles)
         dev.duckdb (main_marts.dim_paper, main_marts.dim_patent for titles)
Output:  r2://p2p-lake/intermediate/cluster_labels/v{date}/cluster_labels.parquet
Schema:  cluster_id, tagline, summary_friendly, top_terms
"""

import datetime
import json
import os
import pathlib
import tempfile
import time
from collections import defaultdict

import anthropic as _anthropic
import polars as pl
from dagster import OpExecutionContext, asset

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource
from nexus.resources.warehouse import connect_warehouse

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 256
_N_REPRESENTATIVE = 5
_API_DELAY_S = 0.5

_NOISE_TAGLINE = "Frontier / Unclustered"
_NOISE_SUMMARY = (
    "Documents that do not fit cleanly into any named technology family. "
    "They may represent emerging research directions, interdisciplinary work, "
    "or rare topics at the frontier of the three scope sub-families "
    "(EUV lithography, silicon photonics, neuromorphic & in-memory compute)."
)

# Strict prompt: name and describe using only supplied evidence, invent nothing.
_SYSTEM_PROMPT = (
    "You are labelling technology clusters from a research database covering "
    "microchip hardware patents and papers (EUV lithography, silicon photonics, "
    "neuromorphic & in-memory computing). "
    "Use ONLY the terms and titles supplied — do not invent information not present "
    "in the evidence. Respond with valid JSON only, no markdown fences."
)


# ---------------------------------------------------------------------------
# Pure helpers — independently testable without the API
# ---------------------------------------------------------------------------


def build_label_prompt(
    cluster_id: str,
    top_terms: list[str],
    representative_titles: list[str],
) -> str:
    """Build the strict labelling prompt for one cluster.

    Limits to 15 terms and _N_REPRESENTATIVE titles so the prompt stays compact.
    The system prompt forbids the model from going beyond the supplied evidence.
    """
    terms_str = ", ".join(top_terms[:15])
    titles_str = "\n".join(
        f"- {t}" for t in representative_titles[:_N_REPRESENTATIVE]
    )
    return (
        f"Cluster: {cluster_id}\n"
        f"Top discriminating terms: {terms_str}\n\n"
        f"Representative document titles:\n{titles_str}\n\n"
        "Using ONLY the terms and titles above, provide:\n"
        "1. tagline: a short human-readable name for this technology family (2-6 words).\n"
        "2. summary_friendly: 2-3 plain-English sentences describing what "
        "research/patents in this cluster are about.\n\n"
        'Respond with valid JSON only: {"tagline": "...", "summary_friendly": "..."}'
    )


def parse_label_response(response_text: str, cluster_id: str) -> tuple[str, str]:
    """Extract (tagline, summary_friendly) from the Haiku JSON response.

    Falls back to a generic label when parsing fails so one bad API response
    never blocks the whole labelling run.
    """
    text = response_text.strip()
    # Strip markdown fences defensively (system prompt forbids them, but be safe)
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            lines[1:-1] if lines[-1].startswith("```") else lines[1:]
        )
    try:
        data = json.loads(text)
        tagline = str(data.get("tagline", "")).strip()
        summary = str(data.get("summary_friendly", "")).strip()
        if tagline and summary:
            return tagline, summary
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return (
        f"Technology Cluster {cluster_id}",
        (
            "A technology cluster identified from microchip hardware patent "
            f"and paper data. Cluster identifier: {cluster_id}."
        ),
    )


# ---------------------------------------------------------------------------
# Private write helper (stage-then-promote)
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
    deps=["document_clusters"],
    description=(
        f"Labels each technology cluster with {_MODEL}. "
        "Reads top c-TF-IDF terms and representative doc titles from R2; "
        "generates a tagline (2-6 words) and a 2-3 sentence summary per cluster. "
        f"Noise cluster (c_noise) gets a fixed label; no API call for it. "
        "Depends on: R2 cluster_terms + clusters Parquet (document_clusters), "
        "dev.duckdb (main_marts.dim_paper, main_marts.dim_patent). "
        "Output: r2://p2p-lake/intermediate/cluster_labels/v{date}/cluster_labels.parquet"
    ),
)
def cluster_labels(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    """Generate human-readable labels for every technology cluster via Claude Haiku.

    Produces: r2://p2p-lake/intermediate/cluster_labels/v{date}/cluster_labels.parquet
    Depends on: document_clusters asset (R2), dev.duckdb (dbt mart layer).
    Output: see above.
    """
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    labels_path = (
        f"r2://{bucket}/intermediate/cluster_labels/"
        f"v{snapshot_date}/cluster_labels.parquet"
    )

    # Idempotency
    with duckdb.get_connection() as con:
        try:
            n = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{labels_path}')"
            ).fetchone()
            existing: int | None = n[0] if n else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info(
            "Snapshot %s exists (%s rows). Skipping.", labels_path, f"{existing:,}"
        )
        return

    # Find latest cluster_terms snapshot
    with duckdb.get_connection() as con:
        try:
            term_rows = con.execute(
                f"SELECT file FROM glob('r2://{bucket}/intermediate/cluster_terms/*/*.parquet') "
                "ORDER BY file DESC LIMIT 1"
            ).fetchall()
        except Exception as exc:
            raise RuntimeError(f"Cannot list cluster_terms on R2: {exc}") from exc
    if not term_rows:
        raise RuntimeError(
            "No cluster_terms snapshot found. Run document_clusters first."
        )
    terms_path: str = str(term_rows[0][0])

    # Find latest clusters snapshot (for representative doc_ids)
    with duckdb.get_connection() as con:
        try:
            clus_rows = con.execute(
                f"SELECT file FROM glob('r2://{bucket}/intermediate/clusters/*/*.parquet') "
                "ORDER BY file DESC LIMIT 1"
            ).fetchall()
        except Exception as exc:
            raise RuntimeError(f"Cannot list clusters on R2: {exc}") from exc
    if not clus_rows:
        raise RuntimeError(
            "No clusters snapshot found. Run document_clusters first."
        )
    clusters_path: str = str(clus_rows[0][0])

    context.log.info("cluster_terms: %s", terms_path)
    context.log.info("clusters:      %s", clusters_path)

    # Load cluster_terms → cluster_id → top_terms
    with duckdb.get_connection() as con:
        terms_rows = con.execute(
            f"SELECT cluster_id, top_terms, doc_count FROM read_parquet('{terms_path}')"
        ).fetchall()

    cluster_terms_map: dict[str, list[str]] = {}
    for row in terms_rows:
        cid = str(row[0])
        cluster_terms_map[cid] = [str(t) for t in (row[1] or [])]  # type: ignore[reportUnknownVariableType,reportUnknownArgumentType]

    context.log.info("Loaded %s cluster entries from cluster_terms.", len(cluster_terms_map))

    # Load representative doc_ids per cluster (first _N_REPRESENTATIVE sorted by doc_id)
    with duckdb.get_connection() as con:
        cluster_doc_rows = con.execute(
            f"SELECT cluster_id, doc_id FROM read_parquet('{clusters_path}') "
            "WHERE cluster_id != 'c_noise' "
            "ORDER BY cluster_id, doc_id"
        ).fetchall()

    cluster_doc_map: dict[str, list[str]] = defaultdict(list)
    for row in cluster_doc_rows:
        cid = str(row[0])
        did = str(row[1])
        if len(cluster_doc_map[cid]) < _N_REPRESENTATIVE:
            cluster_doc_map[cid].append(did)

    # Load doc titles from the warehouse for representative display in prompts
    dev_con = connect_warehouse()
    try:
        paper_rows = dev_con.execute(
            "SELECT work_id, title FROM main_marts.dim_paper WHERE title IS NOT NULL"
        ).fetchall()
        patent_rows = dev_con.execute(
            "SELECT patent_id, title FROM main_marts.dim_patent WHERE title IS NOT NULL"
        ).fetchall()
    finally:
        dev_con.close()

    id_to_title: dict[str, str] = {str(r[0]): str(r[1]) for r in paper_rows}
    id_to_title.update({str(r[0]): str(r[1]) for r in patent_rows})
    context.log.info("Loaded %s doc titles.", f"{len(id_to_title):,}")

    # Label clusters
    api_client = _anthropic.Anthropic()

    # Output columns built as parallel lists for clean typing
    cluster_ids_out: list[str] = ["c_noise"]
    taglines_out: list[str] = [_NOISE_TAGLINE]
    summaries_out: list[str] = [_NOISE_SUMMARY]
    top_terms_out: list[list[str]] = [[]]

    non_noise_clusters = sorted(c for c in cluster_terms_map if c != "c_noise")
    context.log.info(
        "Labelling %s clusters with %s (c_noise gets fixed label)…",
        len(non_noise_clusters), _MODEL,
    )

    for i, cluster_id in enumerate(non_noise_clusters):
        top_terms = cluster_terms_map.get(cluster_id, [])
        doc_ids = cluster_doc_map.get(cluster_id, [])
        titles = [
            id_to_title[d] for d in doc_ids if d in id_to_title
        ][:_N_REPRESENTATIVE]

        prompt = build_label_prompt(cluster_id, top_terms, titles)

        try:
            response = api_client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = ""
            for block in response.content:
                if block.type == "text":
                    response_text = block.text  # type: ignore[reportAttributeAccessIssue]
                    break
            tagline, summary = parse_label_response(response_text, cluster_id)
        except Exception as exc:
            logger.warning(
                "Haiku call failed for %s: %s. Using generic label.", cluster_id, exc
            )
            tagline, summary = parse_label_response("", cluster_id)

        cluster_ids_out.append(cluster_id)
        taglines_out.append(tagline)
        summaries_out.append(summary)
        top_terms_out.append(top_terms)

        # Polite pause between API calls
        if i < len(non_noise_clusters) - 1:
            time.sleep(_API_DELAY_S)

        if (i + 1) % 10 == 0 or (i + 1) == len(non_noise_clusters):
            context.log.info(
                "Labelled %s / %s clusters.", i + 1, len(non_noise_clusters)
            )

    df = pl.DataFrame(
        {
            "cluster_id": cluster_ids_out,
            "tagline": taglines_out,
            "summary_friendly": summaries_out,
            "top_terms": top_terms_out,
        },
        schema={
            "cluster_id": pl.String,
            "tagline": pl.String,
            "summary_friendly": pl.String,
            "top_terms": pl.List(pl.String),
        },
    )

    context.log.info("Writing cluster_labels.parquet (%s rows)…", len(df))
    _write_df_to_r2(df, labels_path, bucket, duckdb, r2)

    context.log.info(
        "cluster_labels complete. %s labels written to %s.", len(df), labels_path
    )
    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "total_clusters": len(df),
            "non_noise_clusters": len(non_noise_clusters),
            "model": _MODEL,
            "labels_path": labels_path,
        }
    )
