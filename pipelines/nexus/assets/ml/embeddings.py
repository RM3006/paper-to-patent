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

Input:   dev.duckdb (main_marts.dim_paper, main_marts.dim_patent)
Output:  r2://p2p-lake/intermediate/embeddings/v{date}/embeddings.parquet
Schema:  doc_id, doc_type, text_source, model_version, truncated, embedding (FLOAT[384])
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
from dagster import OpExecutionContext, asset
from langdetect import (
    DetectorFactory,
    LangDetectException,
    detect,  # type: ignore[reportUnknownVariableType]
)

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

DetectorFactory.seed = 0  # deterministic language detection across runs

_MODEL_NAME = "all-MiniLM-L6-v2"
_MAX_SEQ_LEN = 256   # model hard cap (tokens, including special tokens)
_BATCH_SIZE = 128

# Quality gate constants (see module docstring)
_PLACEHOLDER_ABSTRACT_RE = re.compile(r"^\s*abstract\s+not\s+(provided|available)", re.IGNORECASE)
_VERSION_TITLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*\s+v?\d+\.\d+(\.\d+)?(\s*\(.*\))?\s*$")
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


def load_corpus(dev_con: "_duckdb_lib.DuckDBPyConnection") -> list[dict[str, str]]:
    """Return all embeddable documents from dev.duckdb as a unified list.

    Papers  → text_source='abstract' or 'title' (see resolve_paper_text),
              doc_type='paper', doc_id=work_id
    Patents → text_source='title', doc_type='patent', doc_id=patent_id

    Rows with no trustworthy text in either field are skipped entirely —
    they would produce meaningless embeddings that distort cluster centroids.
    See resolve_paper_text and is_version_style_title for the quality gate.
    """
    paper_rows = dev_con.execute(
        "SELECT work_id, title, abstract FROM main_marts.dim_paper "
        "WHERE abstract IS NOT NULL AND length(abstract) > 0"
    ).fetchall()
    patent_rows = dev_con.execute(
        "SELECT patent_id, title FROM main_marts.dim_patent "
        "WHERE title IS NOT NULL AND length(title) > 0"
    ).fetchall()

    corpus: list[dict[str, str]] = []
    for work_id, title, abstract in paper_rows:
        resolved = resolve_paper_text(title or "", abstract)
        if resolved is None:
            continue
        text, text_source = resolved
        corpus.append({
            "doc_id": work_id,
            "doc_type": "paper",
            "text_source": text_source,
            "text": text,
        })
    for patent_id, title in patent_rows:
        if is_version_style_title(title):
            continue
        corpus.append({
            "doc_id": patent_id,
            "doc_type": "patent",
            "text_source": "title",
            "text": title,
        })
    return corpus


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
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
)
def document_embeddings(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    """Embed scope documents (papers + patents) and write to R2.

    Produces: r2://p2p-lake/intermediate/embeddings/v{date}/embeddings.parquet
    Depends on: dev.duckdb built by `dbt build` (Part 4 / Step 0c).
    Output: r2://p2p-lake/intermediate/embeddings/v{date}/embeddings.parquet
    """
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    r2_path = f"r2://{bucket}/intermediate/embeddings/v{snapshot_date}/embeddings.parquet"

    # Idempotency: skip if snapshot already written today
    with duckdb.get_connection() as con:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{r2_path}')").fetchone()
            existing: int | None = n[0] if n else None
        except Exception:
            existing = None
    if existing is not None:
        context.log.info("Snapshot %s exists (%s rows). Skipping.", r2_path, f"{existing:,}")
        return

    dev_db_path = pathlib.Path(os.environ.get("DBT_DUCKDB_PATH", "dev.duckdb"))
    if not dev_db_path.exists():
        raise FileNotFoundError(
            f"dev.duckdb not found at {dev_db_path}. Run 'dbt build' first."
        )

    # Lazy import: keeps module importable in tests without downloading the model
    context.log.info("Loading model %s…", _MODEL_NAME)
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    model = SentenceTransformer(_MODEL_NAME)
    tokenizer = model.tokenizer

    # Load corpus from the mart layer
    dev_con = _duckdb_lib.connect(str(dev_db_path), read_only=True)
    try:
        context.log.info("Loading corpus from dev.duckdb…")
        corpus = load_corpus(dev_con)
    finally:
        dev_con.close()

    n_papers = sum(1 for d in corpus if d["doc_type"] == "paper")
    n_patents = sum(1 for d in corpus if d["doc_type"] == "patent")
    context.log.info(
        "Corpus: %s docs (%s papers, %s patents).",
        f"{len(corpus):,}", f"{n_papers:,}", f"{n_patents:,}",
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

    # Write to R2 via stage-then-promote
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

    context.log.info("Written %s rows → %s", f"{len(df):,}", r2_path)
    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "total_docs": len(df),
            "n_papers": n_papers,
            "n_patents": n_patents,
            "n_truncated": n_truncated,
            "pct_truncated": round(100.0 * n_truncated / max(len(df), 1), 2),
            "model_version": _MODEL_NAME,
            "embedding_dim": 384,
            "r2_path": r2_path,
        }
    )
