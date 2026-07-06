"""Document clustering asset for Part 5 — UMAP + HDBSCAN + c-TF-IDF.

Reads the embedding Parquet from R2, projects to 2D with UMAP, clusters with
HDBSCAN, then extracts the most distinctive vocabulary per cluster via
class-based TF-IDF (BERTopic's c-TF-IDF formula).

Noise points (HDBSCAN label = -1) → cluster_id = 'c_noise'. They retain
UMAP coordinates and are presented honestly in the UI as an unclustered frontier.

Input:   R2 intermediate/embeddings/, dev.duckdb (texts for c-TF-IDF)
Output:  r2://p2p-lake/intermediate/clusters/v{date}/clusters.parquet
         r2://p2p-lake/intermediate/cluster_terms/v{date}/cluster_terms.parquet
"""

import datetime
import os
import pathlib
import tempfile

import numpy as np
import polars as pl
from dagster import OpExecutionContext, asset
from sklearn.feature_extraction.text import CountVectorizer

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.assets.ml.embeddings import load_corpus
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource
from nexus.resources.warehouse import connect_warehouse

_UMAP_N_NEIGHBORS = 15
_UMAP_MIN_DIST = 0.1
_HDBSCAN_MIN_CLUSTER_SIZE = 50
_CTFIDF_N_TERMS = 15
_MODEL_VERSION = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Pure helpers — independently testable
# ---------------------------------------------------------------------------


def make_cluster_id(label: int) -> str:
    """Map HDBSCAN integer label to a cluster_id string.

    Negative labels (noise) → 'c_noise'. Non-negative → 'c_{label}'.
    """
    return "c_noise" if label < 0 else f"c_{label}"


def compute_ctfidf_terms(
    doc_ids: list[str],
    labels: list[int],
    id_to_text: dict[str, str],
    n_terms: int = _CTFIDF_N_TERMS,
) -> dict[str, list[str]]:
    """Return top c-TF-IDF terms per cluster.

    Each cluster is treated as a single class document (all document texts
    concatenated). IDF is computed across classes, so terms shared by many
    clusters score low regardless of within-cluster frequency — only terms
    that are distinctive to a cluster surface at the top.

    The noise cluster 'c_noise' always receives an empty term list because it
    is a mixed-genre bucket with no coherent defining vocabulary.

    Returns dict mapping cluster_id → [term, ...], n_terms long per cluster.
    """
    cluster_texts: dict[int, list[str]] = {}
    for doc_id, label in zip(doc_ids, labels, strict=True):
        if label < 0:
            continue
        text = id_to_text.get(doc_id, "")
        if text:
            cluster_texts.setdefault(label, []).append(text)

    non_noise_labels = sorted(cluster_texts)
    result: dict[str, list[str]] = {"c_noise": []}

    if not non_noise_labels:
        return result

    class_docs = [" ".join(cluster_texts[lb]) for lb in non_noise_labels]

    vectorizer = CountVectorizer(
        stop_words="english",
        max_features=10_000,
        ngram_range=(1, 2),
        min_df=1,
    )
    count_matrix = vectorizer.fit_transform(class_docs)  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]

    # np.asarray restores a concrete ndarray type after the sparse→dense conversion
    count_arr = np.asarray(count_matrix.toarray(), dtype=np.float32)  # type: ignore[union-attr]
    tf = count_arr / (count_arr.sum(axis=1, keepdims=True) + 1e-9)

    n_classes = len(non_noise_labels)
    df = (count_arr > 0).sum(axis=0)
    idf = np.log(n_classes / (df + 1e-9))

    ctfidf = tf * idf
    vocab = vectorizer.get_feature_names_out()  # type: ignore[reportUnknownMemberType]

    for i, label in enumerate(non_noise_labels):
        # numpy argsort/tolist chain → list[Any]; type: ignore is narrower than disabling the rule
        top_idx: list[int] = ctfidf[i].argsort()[::-1][:n_terms].tolist()  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
        result[f"c_{label}"] = [str(vocab[j]) for j in top_idx]  # type: ignore[reportUnknownVariableType]

    return result


# ---------------------------------------------------------------------------
# Private write helper (stage-then-promote, same pattern as other ML assets)
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
    deps=["document_embeddings"],
    description=(
        "UMAP (2D, cosine, n_neighbors=15, min_dist=0.1) + HDBSCAN (min_cluster_size=50) "
        "over all scope document embeddings. "
        "Extracts top c-TF-IDF terms per cluster. Noise points → cluster_id='c_noise'. "
        "Depends on: R2 embeddings Parquet (document_embeddings asset), "
        "dev.duckdb (main_marts.dim_paper, main_marts.dim_patent) for c-TF-IDF text. "
        "Output: r2://p2p-lake/intermediate/clusters/v{date}/clusters.parquet "
        "and r2://p2p-lake/intermediate/cluster_terms/v{date}/cluster_terms.parquet"
    ),
)
def document_clusters(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    """Cluster scope documents and extract per-cluster vocabulary.

    Produces:
      - r2://p2p-lake/intermediate/clusters/v{date}/clusters.parquet
      - r2://p2p-lake/intermediate/cluster_terms/v{date}/cluster_terms.parquet
    Depends on: document_embeddings asset (R2), dev.duckdb (dbt mart layer).
    Output: see above.
    """
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    clusters_path = (
        f"r2://{bucket}/intermediate/clusters/v{snapshot_date}/clusters.parquet"
    )
    terms_path = (
        f"r2://{bucket}/intermediate/cluster_terms/v{snapshot_date}/cluster_terms.parquet"
    )

    # Idempotency: skip if both outputs exist
    with duckdb.get_connection() as con:
        def _exists(path: str) -> bool:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()
                return bool(n and n[0] > 0)
            except Exception:
                return False

        if _exists(clusters_path) and _exists(terms_path):
            context.log.info(
                "Both cluster outputs exist for %s. Skipping.", snapshot_date
            )
            return

    # Locate the latest embeddings snapshot
    with duckdb.get_connection() as con:
        try:
            rows = con.execute(
                f"SELECT file FROM glob('r2://{bucket}/intermediate/embeddings/*/*.parquet') "
                "ORDER BY file DESC LIMIT 1"
            ).fetchall()
        except Exception as exc:
            raise RuntimeError(f"Cannot list embeddings on R2: {exc}") from exc

    if not rows:
        raise RuntimeError(
            "No embeddings snapshot found at "
            f"r2://{bucket}/intermediate/embeddings/. "
            "Run document_embeddings first."
        )
    embeddings_path = rows[0][0]
    context.log.info("Using embeddings: %s", embeddings_path)

    # Load embeddings from R2 → numpy matrix
    context.log.info("Loading embeddings…")
    with duckdb.get_connection() as con:
        rows = con.execute(
            f"SELECT doc_id, doc_type, embedding "
            f"FROM read_parquet('{embeddings_path}') "
            "ORDER BY doc_id"
        ).fetchall()

    doc_ids: list[str] = [r[0] for r in rows]
    doc_types: list[str] = [r[1] for r in rows]
    embedding_matrix = np.array([r[2] for r in rows], dtype=np.float32)
    context.log.info(
        "Embeddings loaded: %s docs, shape %s.", f"{len(doc_ids):,}", str(embedding_matrix.shape)
    )

    # UMAP 2D — lazy import keeps test suite fast (avoids numba JIT on import)
    import umap as _umap  # noqa: PLC0415

    context.log.info(
        "Running UMAP (n_neighbors=%s, min_dist=%s, metric=cosine)…",
        _UMAP_N_NEIGHBORS, _UMAP_MIN_DIST,
    )
    reducer = _umap.UMAP(  # type: ignore[reportUnknownMemberType]
        n_components=2,
        n_neighbors=_UMAP_N_NEIGHBORS,
        min_dist=_UMAP_MIN_DIST,
        metric="cosine",
        random_state=42,
    )
    coords = np.asarray(
        reducer.fit_transform(embedding_matrix),  # type: ignore[reportUnknownMemberType]
        dtype=np.float32,
    )
    context.log.info("UMAP complete. Coords shape: %s.", str(coords.shape))

    # HDBSCAN — lazy import (numba)
    import hdbscan as _hdbscan  # noqa: PLC0415

    context.log.info("Running HDBSCAN (min_cluster_size=%s)…", _HDBSCAN_MIN_CLUSTER_SIZE)
    clusterer = _hdbscan.HDBSCAN(  # type: ignore[reportUnknownMemberType]
        min_cluster_size=_HDBSCAN_MIN_CLUSTER_SIZE,
        metric="euclidean",
    )
    labels_arr = np.asarray(
        clusterer.fit_predict(coords),  # type: ignore[reportUnknownMemberType]
        dtype=np.int32,
    )
    labels: list[int] = labels_arr.tolist()

    n_clusters = len({lb for lb in labels if lb >= 0})
    n_noise = sum(1 for lb in labels if lb < 0)
    context.log.info(
        "HDBSCAN: %s clusters, %s noise points (%.1f%%).",
        n_clusters, f"{n_noise:,}", 100.0 * n_noise / max(len(labels), 1),
    )

    # Load original texts for c-TF-IDF
    dev_con = connect_warehouse()
    try:
        corpus, _excluded = load_corpus(dev_con)
    finally:
        dev_con.close()
    id_to_text = {d["doc_id"]: d["text"] for d in corpus}

    context.log.info("Computing c-TF-IDF top terms (%s terms per cluster)…", _CTFIDF_N_TERMS)
    ctfidf_terms = compute_ctfidf_terms(doc_ids, labels, id_to_text, n_terms=_CTFIDF_N_TERMS)
    context.log.info(
        "c-TF-IDF complete. %s cluster entries (including c_noise).", len(ctfidf_terms)
    )

    # Build clusters DataFrame
    cluster_ids = [make_cluster_id(lb) for lb in labels]
    clusters_df = pl.DataFrame(
        {
            "doc_id": doc_ids,
            "doc_type": doc_types,
            "cluster_id": cluster_ids,
            "umap_x": coords[:, 0].tolist(),
            "umap_y": coords[:, 1].tolist(),
            "model_version": [_MODEL_VERSION] * len(doc_ids),
        },
        schema={
            "doc_id": pl.String,
            "doc_type": pl.String,
            "cluster_id": pl.String,
            "umap_x": pl.Float32,
            "umap_y": pl.Float32,
            "model_version": pl.String,
        },
    )

    # Build cluster_terms DataFrame — join doc_count from clusters
    doc_counts = clusters_df.group_by("cluster_id").agg(pl.len().alias("doc_count"))
    terms_df = (
        pl.DataFrame(
            [{"cluster_id": cid, "top_terms": terms} for cid, terms in ctfidf_terms.items()],
            schema={"cluster_id": pl.String, "top_terms": pl.List(pl.String)},
        )
        .join(doc_counts, on="cluster_id", how="left")
        .with_columns(pl.col("doc_count").cast(pl.Int32).fill_null(0))
    )

    # Write both outputs
    context.log.info("Writing clusters.parquet (%s rows)…", f"{len(clusters_df):,}")
    _write_df_to_r2(clusters_df, clusters_path, bucket, duckdb, r2)

    context.log.info("Writing cluster_terms.parquet (%s rows)…", len(terms_df))
    _write_df_to_r2(terms_df, terms_path, bucket, duckdb, r2)

    context.log.info(
        "document_clusters complete. %s clusters + noise at %s.",
        n_clusters, snapshot_date,
    )
    context.add_output_metadata(
        {
            "snapshot_date": snapshot_date,
            "total_docs": len(doc_ids),
            "n_clusters": n_clusters,
            "n_noise": n_noise,
            "pct_noise": round(100.0 * n_noise / max(len(labels), 1), 2),
            "min_cluster_size": _HDBSCAN_MIN_CLUSTER_SIZE,
            "umap_n_neighbors": _UMAP_N_NEIGHBORS,
            "clusters_path": clusters_path,
            "terms_path": terms_path,
        }
    )
