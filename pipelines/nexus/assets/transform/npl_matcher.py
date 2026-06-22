"""NPL link matcher — resolves paper↔patent edges from g_other_reference citation strings.

Two-route approach:
  1. DOI route (confidence=high): regex-extracted bare DOI → exact join on doi_bare.
  2. Fuzzy-title route (confidence=medium): inverted-index candidate generation +
     rapidfuzz.token_set_ratio at the lowest threshold in [90, 95, 100] that achieves
     conditional precision ≥ 0.80 on the Marx & Fuegi gold eval set.

"Conditional precision" is measured only over patents that appear in the gold set,
to avoid penalising links for patents the gold set cannot confirm (MAG coverage ~2021).

Output: r2://p2p-lake/intermediate/npl/v{date}/npl_links.parquet
Schema: patent_id, work_id, match_method, confidence, doi_extracted

Gold eval stored in dev.duckdb as ref_npl_gold_eval (reference, not a mart).
Precision/recall recorded in docs/data_source_manifest.md.
"""

import datetime
import os
import pathlib
import re
import tempfile
from collections import Counter, defaultdict
from typing import Any

import duckdb as _duckdb_lib
import polars as pl
from dagster import OpExecutionContext, asset
from rapidfuzz import fuzz

from nexus.assets.ingest.openalex import delete_r2_object
from nexus.logging import logger
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-Z]{5,}")
_MF_CSV = pathlib.Path("data") / "reference" / "marx_fuegi_pcs.csv"
_MAX_POSTINGS = 5_000   # skip tokens in >5k OA titles (no discriminating power)
_MAX_CANDIDATES = 30    # per NPL string: evaluate top-N candidates by shared tokens
_MIN_TITLE_WORDS = 5    # skip OA titles shorter than this (too generic)
_MIN_NPL_LEN = 40       # skip NPL strings shorter than this (too little signal)
_THRESHOLDS = (90, 95, 100)
_MIN_PRECISION = 0.80


# ---------------------------------------------------------------------------
# Pure helpers — independently testable
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> frozenset[str]:
    """Extract distinctive alphabetic tokens (≥ 5 chars) from text."""
    return frozenset(t.lower() for t in _TOKEN_RE.findall(text))


def build_inverted_index(
    pairs: list[tuple[str, str]],
    max_postings: int = _MAX_POSTINGS,
) -> dict[str, list[str]]:
    """Build token → [work_id, ...] inverted index from (work_id, title) pairs.

    Tokens appearing in more than max_postings titles are dropped — they carry
    no discriminating power and would inflate candidate sets.
    """
    raw: dict[str, list[str]] = defaultdict(list)
    for work_id, title in pairs:
        for tok in _tokenize(title):
            raw[tok].append(work_id)
    return {tok: wids for tok, wids in raw.items() if len(wids) <= max_postings}


def evaluate_matches(
    match_pairs: set[tuple[str, str]],
    gold_pairs: set[tuple[str, str]],
) -> dict[str, float]:
    """Precision/recall of match_pairs against gold_pairs."""
    tp = len(match_pairs & gold_pairs)
    fp = len(match_pairs - gold_pairs)
    fn = len(gold_pairs - match_pairs)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return {
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "precision": precision,
        "recall": recall,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_gold_eval(
    dev_con: "_duckdb_lib.DuckDBPyConnection",
    mf_csv: str,
) -> pl.DataFrame:
    """Build ref_npl_gold_eval in dev.duckdb; return as DataFrame.

    Filters Marx & Fuegi to (scope patents ∩ OA corpus).
    oaid in the CSV is the OpenAlex numeric work ID; work_id = 'W' + str(oaid).
    """
    dev_con.execute(f"""
        CREATE OR REPLACE TABLE ref_npl_gold_eval AS
        WITH mf AS (
            SELECT
                regexp_extract(patent, '^us-([0-9]+)-', 1) AS patent_id,
                'W' || CAST(oaid AS VARCHAR)               AS work_id,
                confscore::integer                         AS confscore
            FROM read_csv('{mf_csv}', header = true)
        )
        SELECT DISTINCT patent_id, work_id, confscore
        FROM mf
        WHERE patent_id != ''
          AND patent_id IN (SELECT patent_id FROM main_staging.stg_patents_scoped)
          AND work_id    IN (SELECT work_id    FROM main_staging.stg_openalex_works)
    """)
    rows = dev_con.execute(
        "SELECT patent_id, work_id, confscore FROM ref_npl_gold_eval"
    ).fetchall()
    return pl.DataFrame(rows, schema=["patent_id", "work_id", "confscore"], orient="row")


def _doi_match(
    dev_con: "_duckdb_lib.DuckDBPyConnection",
    doi_bare_to_work_id: dict[str, str],
) -> list[dict[str, Any]]:
    """High-confidence matches via pre-extracted bare DOIs in stg_npl."""
    rows = dev_con.execute("""
        SELECT DISTINCT patent_id, doi_extracted
        FROM main_staging.stg_npl
        WHERE doi_extracted IS NOT NULL AND doi_extracted != ''
    """).fetchall()

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for patent_id, doi in rows:
        wid = doi_bare_to_work_id.get(doi)
        if wid:
            key = (patent_id, wid)
            if key not in seen:
                out.append({
                    "patent_id": patent_id,
                    "work_id": wid,
                    "match_method": "npl_citation",
                    "confidence": "high",
                    "doi_extracted": doi,
                })
                seen.add(key)
    return out


def _fuzzy_match_all(
    npl_rows: list[tuple[str, int, str]],
    work_id_to_title: dict[str, str],
    index: dict[str, list[str]],
    max_candidates: int = _MAX_CANDIDATES,
) -> list[tuple[str, str, float]]:
    """For each NPL string, find its best-scoring OA work match.

    Returns (patent_id, work_id, score) for the top match per NPL string.
    No threshold filtering here — caller filters by threshold.
    """
    results: list[tuple[str, str, float]] = []
    for patent_id, _, npl_text in npl_rows:
        if len(npl_text) < _MIN_NPL_LEN:
            continue
        npl_toks = _tokenize(npl_text)
        if not npl_toks:
            continue

        counts: Counter[str] = Counter()
        for tok in npl_toks:
            for wid in index.get(tok, []):
                counts[wid] += 1

        if not counts:
            continue

        best_wid: str | None = None
        best_score = 0.0
        for wid, _ in counts.most_common(max_candidates):
            title = work_id_to_title.get(wid, "")
            if len(title.split()) < _MIN_TITLE_WORDS:
                continue
            score = float(fuzz.token_set_ratio(title.lower(), npl_text.lower()))
            if score > best_score:
                best_score = score
                best_wid = wid

        if best_wid is not None and best_score > 0:
            results.append((patent_id, best_wid, best_score))

    return results


def _dedup_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate on (patent_id, work_id), preferring high over medium confidence."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for m in matches:
        key = (m["patent_id"], m["work_id"])
        existing = seen.get(key)
        if existing is None or (
            existing["confidence"] == "medium" and m["confidence"] == "high"
        ):
            seen[key] = m
    return list(seen.values())


# ---------------------------------------------------------------------------
# Dagster asset
# ---------------------------------------------------------------------------


@asset(
    group_name="transform",
    description=(
        "NPL link matcher: resolves paper↔patent edges from g_other_reference strings. "
        "DOI route (high confidence): pre-extracted bare DOI → exact join. "
        "Fuzzy route (medium confidence): inverted-index + rapidfuzz token_set_ratio "
        "at threshold tuned on the Marx & Fuegi gold eval set (precision ≥ 0.80). "
        "Output: r2://p2p-lake/intermediate/npl/v{date}/npl_links.parquet. "
        "Depends on dbt staging models (stg_npl, stg_openalex_works) in dev.duckdb."
    ),
)
def npl_links_raw(
    context: OpExecutionContext,
    r2: R2Resource,
    duckdb: DuckDBR2Resource,
) -> None:
    snapshot_date = datetime.date.today().isoformat()
    bucket = r2.bucket
    r2_path = f"r2://{bucket}/intermediate/npl/v{snapshot_date}/npl_links.parquet"

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

    # Open dev.duckdb for reading/writing gold eval
    dev_db_path = pathlib.Path(os.environ.get("DBT_DUCKDB_PATH", "dev.duckdb"))
    if not dev_db_path.exists():
        raise FileNotFoundError(
            f"dev.duckdb not found at {dev_db_path}. Run 'dbt build' (Step 1) first."
        )
    dev_con = _duckdb_lib.connect(str(dev_db_path))

    try:
        # Load OA works
        context.log.info("Loading OA works from dev.duckdb…")
        oa_rows = dev_con.execute(
            "SELECT work_id, doi_bare, title FROM main_staging.stg_openalex_works "
            "WHERE title IS NOT NULL"
        ).fetchall()
        work_id_to_title: dict[str, str] = {r[0]: r[2] for r in oa_rows}
        doi_bare_to_work_id: dict[str, str] = {
            r[1]: r[0] for r in oa_rows if r[1] and r[1] != ""
        }
        context.log.info(
            "OA works: %s total, %s with bare DOI.",
            f"{len(work_id_to_title):,}", f"{len(doi_bare_to_work_id):,}",
        )

        # Build gold eval (stored in dev.duckdb for future reference)
        context.log.info("Building ref_npl_gold_eval from Marx & Fuegi CSV…")
        mf_path = str(_MF_CSV.resolve())
        gold_df = _build_gold_eval(dev_con, mf_path)
        gold_pairs: set[tuple[str, str]] = set(
            zip(gold_df["patent_id"].to_list(), gold_df["work_id"].to_list(), strict=True)
        )
        gold_patent_set: set[str] = set(gold_df["patent_id"].to_list())
        context.log.info(
            "Gold eval: %s pairs, %s distinct patents.",
            f"{len(gold_pairs):,}", f"{len(gold_patent_set):,}",
        )

        # DOI match
        doi_matches = _doi_match(dev_con, doi_bare_to_work_id)
        context.log.info("DOI matches (high confidence): %s.", f"{len(doi_matches):,}")

        # Load unmatched NPL rows for fuzzy matching
        npl_rows = dev_con.execute(
            "SELECT patent_id, ref_sequence, ref_text FROM main_staging.stg_npl "
            "WHERE doi_extracted IS NULL OR doi_extracted = ''"
        ).fetchall()
        context.log.info("NPL rows for fuzzy matching: %s.", f"{len(npl_rows):,}")

        # Build inverted index
        index = build_inverted_index(list(work_id_to_title.items()))
        context.log.info("Inverted index: %s distinct tokens.", f"{len(index):,}")

        # Fuzzy match — collect raw scores, threshold-tune below
        context.log.info("Running fuzzy matching (this takes ~1 minute)…")
        raw_fuzzy = _fuzzy_match_all(npl_rows, work_id_to_title, index)
        context.log.info("Fuzzy candidates (all thresholds): %s.", f"{len(raw_fuzzy):,}")

        # Threshold tuning on gold eval
        # Conditional precision: measured only for patents in the gold set (avoids
        # penalising real links that gold cannot confirm due to ~2021 MAG coverage).
        eval_log: list[dict[str, Any]] = []
        for t in _THRESHOLDS:
            fuzzy_at_t = [
                {
                    "patent_id": pid, "work_id": wid,
                    "match_method": "npl_citation", "confidence": "medium",
                    "doi_extracted": None,
                }
                for pid, wid, score in raw_fuzzy
                if score >= t
            ]
            combined = _dedup_matches(doi_matches + fuzzy_at_t)
            cond_match_pairs: set[tuple[str, str]] = {
                (m["patent_id"], m["work_id"])
                for m in combined
                if m["patent_id"] in gold_patent_set
            }
            ev = evaluate_matches(cond_match_pairs, gold_pairs)
            context.log.info(
                "Threshold=%s: total_links=%s, gold_patent_links=%s, "
                "cond_precision=%.3f, recall=%.3f (tp=%s fp=%s fn=%s)",
                t, f"{len(combined):,}", f"{len(cond_match_pairs):,}",
                ev["precision"], ev["recall"],
                int(ev["tp"]), int(ev["fp"]), int(ev["fn"]),
            )
            eval_log.append({"threshold": t, **ev, "total_links": len(combined)})

        # Choose lowest threshold achieving conditional precision >= 0.80
        passing = [e for e in eval_log if e["precision"] >= _MIN_PRECISION]
        chosen = passing[0] if passing else eval_log[-1]  # fallback: 100
        chosen_threshold: int = int(chosen["threshold"])
        if not passing:
            context.log.warning(
                "No threshold achieved cond. precision >= %.2f. "
                "Using threshold=%s (most conservative). "
                "Report the actual precision in docs/data_source_manifest.md.",
                _MIN_PRECISION, chosen_threshold,
            )

        context.log.info(
            "Chosen threshold: %s (cond. precision=%.3f, recall=%.3f, "
            "total_links=%s).",
            chosen_threshold, chosen["precision"], chosen["recall"],
            f"{int(chosen['total_links']):,}",
        )

        # Build final output at chosen threshold
        fuzzy_final = [
            {
                "patent_id": pid, "work_id": wid,
                "match_method": "npl_citation", "confidence": "medium",
                "doi_extracted": None,
            }
            for pid, wid, score in raw_fuzzy
            if score >= chosen_threshold
        ]
        final_matches = _dedup_matches(doi_matches + fuzzy_final)
        final_df = pl.DataFrame(
            final_matches,
            schema={
                "patent_id": pl.String,
                "work_id": pl.String,
                "match_method": pl.String,
                "confidence": pl.String,
                "doi_extracted": pl.String,
            },
        )
        context.log.info(
            "Final output: %s links (DOI=%s, fuzzy@%s=%s).",
            f"{len(final_df):,}",
            f"{len(doi_matches):,}",
            chosen_threshold,
            f"{len(fuzzy_final):,}",
        )

    finally:
        dev_con.close()

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
            "doi_links": len(doi_matches),
            "fuzzy_links": len(fuzzy_final),
            "chosen_threshold": chosen_threshold,
            "cond_precision": round(chosen["precision"], 4),
            "recall": round(chosen["recall"], 4),
            "r2_path": r2_path,
        }
    )
