"""Document embedding asset for Part 5 — semantic clustering.

Embeds all scope documents with all-MiniLM-L6-v2 (384-dim) on CPU, in batches.
Papers are normally embedded using their abstract; patents using their title
(PatentsView bulk data does not include patent abstracts — see
docs/data_source_manifest.md).

Quality gate (see resolve_paper_text): a paper falls back to its title, or is
excluded from embedding entirely, when its abstract can't be trusted as real
scientific content. Derived from inspecting real artifact clusters (c_4, c_65,
c_25) found by measuring cluster family purity (2026-07-04):
  1. Placeholder abstract ("Abstract not provided.", etc.) -> title fallback.
  2. Abstract shorter than _MIN_ABSTRACT_LEN chars (conference-session
     pointers, thesis citation records, editorial blurbs) -> title fallback.
  3. Title itself looks like a software-release name+version
     ("libBigWig 0.1.5") -> excluded entirely; the abstract is release-note
     prose in these cases, not science, even when it reads as well-formed
     English. Applied to both papers and patents.
  4. Abstract's detected language isn't English -> title fallback if the
     title itself detects as English, else excluded. OpenAlex's own
     `language` field is unreliable here: French/Italian/Catalan PhD thesis
     abstracts were all found tagged 'en'.

A truncated flag is set for any document whose tokenized length exceeds the
model's 256-token hard limit. The model silently truncates on encode; this flag
lets downstream analysis treat over-long inputs with appropriate caution.

Documents the gate excludes entirely (version-style title, or non-English
title+abstract) are also persisted as a second output, excluded_documents —
computed in the same pass as the embeddings (a multi_asset, not a separate
asset re-deriving the same decision), so dbt's staging-layer exclusion of
these same documents from the served corpus can never drift out of sync with
what this gate actually decided.

Input:   dev.duckdb (main_marts.dim_paper, main_marts.dim_patent)
Output:  r2://p2p-lake/intermediate/embeddings/v{date}/embeddings.parquet
         r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet
Schema:  embeddings — doc_id, doc_type, text_source, model_version, truncated,
         embedding (FLOAT[384])
         excluded_documents — doc_id, doc_type, exclusion_reason, model_version
"""

import datetime
import os
import pathlib
import re
import tempfile
from typing import Any

import duckdb as _duckdb_lib
import numpy as np
import polars as pl
from dagster import AssetOut, MaterializeResult, OpExecutionContext, multi_asset
from langdetect import (
    DetectorFactory,
    LangDetectException,
    detect,  # type: ignore[reportUnknownVariableType]
)

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource
from nexus.resources.warehouse import connect_warehouse

DetectorFactory.seed = 0  # deterministic language detection across runs

_MODEL_NAME = "all-MiniLM-L6-v2"
_MAX_SEQ_LEN = 256   # model hard cap (tokens, including special tokens)
_BATCH_SIZE = 128

# Quality gate constants (see module docstring)
_PLACEHOLDER_ABSTRACT_RE = re.compile(r"^\s*abstract\s+not\s+(provided|available)", re.IGNORECASE)
_VERSION_TITLE_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_\-]*\s+v?\d+\.\d+(\.\d+)?(\s*\(.*\))?\s*$"
    # "Name: Name v1.2.3" -- release-note titles that repeat the project name
    # before the colon (e.g. "seL4: seL4 3.0.1"), which the bare pattern above
    # doesn't match because of the leading "Name: " prefix.
    r"|^(?P<name>[A-Za-z][A-Za-z0-9_\-]*)\s*:\s*(?P=name)\s+v?\d+\.\d+(\.\d+)?(\s*\(.*\))?\s*$"
)
_MIN_ABSTRACT_LEN = 50


# ---------------------------------------------------------------------------
# Pure helpers — independently testable without the model
# ---------------------------------------------------------------------------


def is_truncated(text: str, tokenizer: Any, max_len: int = _MAX_SEQ_LEN) -> bool:
    """Return True if text encodes to more tokens than max_len.

    Tokenizes without truncation so we can detect docs that would be silently
    clipped by model.encode(). Includes special tokens in the count, matching
    how the model's encode() counts them.
    """
    ids: list[int] = tokenizer.encode(text, add_special_tokens=True, truncation=False)
    return len(ids) > max_len


def is_version_style_title(title: str) -> bool:
    """Return True if title looks like a software-release name+version.

    Matches patterns like "libBigWig 0.1.5" or "seL4 2.10 (minor release)" —
    a short name token followed by a bare version number and nothing else.
    Legitimate scientific paper titles essentially never take this shape.
    """
    return bool(_VERSION_TITLE_RE.match(title.strip()))


def _detect_language(text: str) -> str | None:
    """Return the detected ISO 639-1 language code, or None if undetectable."""
    try:
        return detect(text)  # type: ignore[reportUnknownVariableType]
    except LangDetectException:
        return None


def resolve_paper_text(title: str, abstract: str) -> tuple[str, str] | None:
    """Apply the abstract-quality gate to one paper's (title, abstract).

    Returns (text, text_source) to embed, or None if the paper has no
    trustworthy scientific-content text in either field and should be
    excluded from embedding entirely.

    Order matters: a version-style title excludes regardless of abstract
    quality (the abstract is release-note prose in these cases, not a
    quality problem an abstract check would catch). Placeholder and
    too-short abstracts fall back to title — the paper itself is real, it's
    just missing a usable abstract. A non-English abstract falls back to
    title only if the title itself detects as English, since OpenAlex's own
    `language` field cannot be trusted here (see module docstring).
    """
    title = title.strip()
    abstract = abstract.strip()

    if is_version_style_title(title):
        return None

    if _PLACEHOLDER_ABSTRACT_RE.match(abstract) or len(abstract) < _MIN_ABSTRACT_LEN:
        return (title, "title") if title else None

    if _detect_language(abstract) != "en":
        if title and _detect_language(title) == "en":
            return (title, "title")
        return None

    return (abstract, "abstract")


def load_corpus(
    dev_con: "_duckdb_lib.DuckDBPyConnection",
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (embeddable corpus, excluded documents) from dev.duckdb.

    Corpus:
      Papers  → text_source='abstract' or 'title' (see resolve_paper_text),
                doc_type='paper', doc_id=work_id
      Patents → text_source='title', doc_type='patent', doc_id=patent_id

    Excluded: doc_id, doc_type, exclusion_reason ('version_style_title' or
    'non_english_content') for documents with no trustworthy text in either
    field — they would produce meaningless embeddings that distort cluster
    centroids. See resolve_paper_text and is_version_style_title for the
    quality gate. Returned (not just dropped) so document_embeddings can
    persist this list to R2 for dbt to exclude the same documents from the
    served corpus — a single computation feeding both, so the two can never
    drift apart the way an independently-written SQL approximation could.

    A NULL/missing abstract is coalesced to '' here (not filtered out by the
    query) so it goes through the same too-short-abstract branch of
    resolve_paper_text() as a placeholder abstract, falling back to title
    instead of being silently dropped before the gate ever sees it — a paper
    missing its abstract is exactly the same "no usable abstract" case as
    one with a too-short abstract, not a reason to exclude the document.

    Title is coalesced to '' the same way and is NOT required to be non-empty
    by the query — title and abstract can each independently be missing (a
    handful of OpenAlex works have title='' despite a substantial, usable
    abstract), and gating entry on title alone silently dropped those papers
    before resolve_paper_text() ever saw them: neither embedded nor recorded
    in excluded_documents, the same invisible third state the abstract-side
    fix above was written to close. resolve_paper_text() already handles an
    empty title correctly (falls through to the abstract). Patents have no
    abstract field at all, so an empty patent title truly has no usable text;
    that case is still recorded in excluded_documents rather than silently
    dropped from patent_rows.
    """
    paper_rows = dev_con.execute(
        "SELECT work_id, COALESCE(title, ''), COALESCE(abstract, '') FROM main_marts.dim_paper "
        "WHERE length(COALESCE(title, '')) > 0 OR length(COALESCE(abstract, '')) > 0"
    ).fetchall()
    patent_rows = dev_con.execute(
        "SELECT patent_id, COALESCE(title, '') FROM main_marts.dim_patent"
    ).fetchall()

    corpus: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for work_id, title, abstract in paper_rows:
        resolved = resolve_paper_text(title, abstract)
        if resolved is None:
            # resolve_paper_text() returns None in exactly two cases: a
            # version-style title (checked first, internally), or no
            # trustworthy English text in either field — title may itself be
            # empty here, not just too short, so this is a best-effort label
            # rather than a strict "confirmed non-English" claim.
            reason = (
                "version_style_title"
                if is_version_style_title(title)
                else "non_english_content"
            )
            excluded.append({"doc_id": work_id, "doc_type": "paper", "exclusion_reason": reason})
            continue
        text, text_source = resolved
        corpus.append({
            "doc_id": work_id,
            "doc_type": "paper",
            "text_source": text_source,
            "text": text,
        })
    for patent_id, title in patent_rows:
        if not title:
            excluded.append({
                "doc_id": patent_id,
                "doc_type": "patent",
                "exclusion_reason": "no_usable_text",
            })
            continue
        if is_version_style_title(title):
            excluded.append({
                "doc_id": patent_id,
                "doc_type": "patent",
                "exclusion_reason": "version_style_title",
            })
            continue
        corpus.append({
            "doc_id": patent_id,
            "doc_type": "patent",
            "text_source": "title",
            "text": title,
        })
    return corpus, excluded


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


def _write_parquet_to_r2(
    df: pl.DataFrame,
    r2_path: str,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
    bucket: str,
) -> None:
    """Write df to r2_path via local-temp-file stage-then-promote."""
    staging_r2 = f"{r2_path}.staging"
    staging_key = staging_r2.removeprefix(f"r2://{bucket}/")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as _f:
        tmp = pathlib.Path(_f.name)
    try:
        df.write_parquet(tmp)
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


@multi_asset(
    outs={
        "document_embeddings": AssetOut(
            group_name="ml",
            description=(
                "Embeds all scope documents with all-MiniLM-L6-v2 (384-dim) on CPU, batched. "
                "Papers use abstract (falling back to title, or excluding the doc entirely, "
                "via the quality gate in resolve_paper_text — placeholder/too-short/non-English "
                "abstracts, version-style titles); patents use title (no abstracts in "
                "PatentsView bulk data). Records a truncated flag for docs exceeding the "
                "256-token model limit. Persisted to R2 so re-clustering never re-embeds. "
                "Depends on: dev.duckdb (main_marts.dim_paper, main_marts.dim_patent). "
                "Output: r2://p2p-lake/intermediate/embeddings/v{date}/embeddings.parquet"
            ),
        ),
        "excluded_documents": AssetOut(
            group_name="ml",
            description=(
                "Documents the embedding quality gate excluded entirely (version-style "
                "title, or title+abstract both detected non-English) — see load_corpus. "
                "Computed in the same pass as document_embeddings, not a separately "
                "maintained filter, so dbt's staging-layer exclusion (stg_openalex_works, "
                "stg_patents_scoped) can never drift from what Part 5 actually decided. "
                "Depends on: dev.duckdb (main_marts.dim_paper, main_marts.dim_patent). "
                "Output: r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet"
            ),
        ),
    },
)
def document_embeddings(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> tuple[MaterializeResult[Any], MaterializeResult[Any]]:
    """Embed scope documents (papers + patents), and write both outputs to R2.

    Produces: embeddings.parquet (the corpus) and excluded_documents.parquet
    (what the gate dropped and why) — one computation, two artifacts, so dbt
    can exclude exactly the same documents from the served corpus.
    Depends on: dev.duckdb built by `dbt build` (Part 4 / Step 0c).
    Output: r2://p2p-lake/intermediate/embeddings/v{date}/embeddings.parquet
            r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet
    """
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    r2_path = f"r2://{bucket}/intermediate/embeddings/v{snapshot_date}/embeddings.parquet"
    excluded_r2_path = (
        f"r2://{bucket}/intermediate/excluded_documents/v{snapshot_date}/excluded_documents.parquet"
    )

    # Idempotency: skip if snapshot already written today (both outputs are
    # always produced together in this same function call, so checking the
    # embeddings path alone is a sufficient gate for both).
    with duckdb.get_connection() as con:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{r2_path}')").fetchone()
            existing: int | None = n[0] if n else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info("Snapshot %s exists (%s rows). Skipping.", r2_path, f"{existing:,}")
        return (
            MaterializeResult(asset_key="document_embeddings", metadata={"r2_path": r2_path}),
            MaterializeResult(
                asset_key="excluded_documents", metadata={"r2_path": excluded_r2_path}
            ),
        )

    # Lazy import: keeps module importable in tests without downloading the model
    context.log.info("Loading model %s…", _MODEL_NAME)
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    model = SentenceTransformer(_MODEL_NAME)
    tokenizer = model.tokenizer

    # Load corpus from the mart layer
    dev_con = connect_warehouse()
    try:
        context.log.info("Loading corpus from the warehouse…")
        corpus, excluded = load_corpus(dev_con)
    finally:
        dev_con.close()

    n_papers = sum(1 for d in corpus if d["doc_type"] == "paper")
    n_patents = sum(1 for d in corpus if d["doc_type"] == "patent")
    context.log.info(
        "Corpus: %s docs (%s papers, %s patents). Excluded: %s.",
        f"{len(corpus):,}", f"{n_papers:,}", f"{n_patents:,}", f"{len(excluded):,}",
    )

    texts = [d["text"] for d in corpus]

    # Compute truncation flags before encoding (no extra overhead; tokenize once)
    context.log.info("Computing truncation flags…")
    truncated_flags = [is_truncated(t, tokenizer) for t in texts]
    n_truncated = sum(truncated_flags)
    context.log.info(
        "Truncated: %s / %s docs (%.1f%%).",
        f"{n_truncated:,}", f"{len(texts):,}",
        100.0 * n_truncated / max(len(texts), 1),
    )

    context.log.info(
        "Embedding %s docs on CPU (batch_size=%s)…", f"{len(texts):,}", _BATCH_SIZE
    )
    embeddings_np = np.asarray(
        model.encode(  # type: ignore[reportUnknownMemberType]
            texts,
            batch_size=_BATCH_SIZE,
            show_progress_bar=False,
            normalize_embeddings=True,
        ),
        dtype=np.float32,
    )
    context.log.info("Embedding complete. Shape: %s.", str(embeddings_np.shape))

    df = pl.DataFrame(
        {
            "doc_id": [d["doc_id"] for d in corpus],
            "doc_type": [d["doc_type"] for d in corpus],
            "text_source": [d["text_source"] for d in corpus],
            "model_version": [_MODEL_NAME] * len(corpus),
            "truncated": truncated_flags,
            "embedding": embeddings_np.tolist(),
        },
        schema={
            "doc_id": pl.String,
            "doc_type": pl.String,
            "text_source": pl.String,
            "model_version": pl.String,
            "truncated": pl.Boolean,
            "embedding": pl.List(pl.Float32),
        },
    )
    _write_parquet_to_r2(df, r2_path, r2, duckdb, bucket)
    context.log.info("Written %s rows → %s", f"{len(df):,}", r2_path)

    excluded_df = pl.DataFrame(
        {
            "doc_id": [d["doc_id"] for d in excluded],
            "doc_type": [d["doc_type"] for d in excluded],
            "exclusion_reason": [d["exclusion_reason"] for d in excluded],
            "model_version": [_MODEL_NAME] * len(excluded),
        },
        schema={
            "doc_id": pl.String,
            "doc_type": pl.String,
            "exclusion_reason": pl.String,
            "model_version": pl.String,
        },
    )
    _write_parquet_to_r2(excluded_df, excluded_r2_path, r2, duckdb, bucket)
    context.log.info("Written %s rows → %s", f"{len(excluded_df):,}", excluded_r2_path)

    return (
        MaterializeResult(
            asset_key="document_embeddings",
            metadata={
                "snapshot_date": snapshot_date,
                "total_docs": len(df),
                "n_papers": n_papers,
                "n_patents": n_patents,
                "n_truncated": n_truncated,
                "pct_truncated": round(100.0 * n_truncated / max(len(df), 1), 2),
                "model_version": _MODEL_NAME,
                "embedding_dim": 384,
                "r2_path": r2_path,
            },
        ),
        MaterializeResult(
            asset_key="excluded_documents",
            metadata={
                "snapshot_date": snapshot_date,
                "total_excluded": len(excluded_df),
                "r2_path": excluded_r2_path,
            },
        ),
    )
