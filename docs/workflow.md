# workflow.md — Paper → Patent end-to-end workflow

The single end-to-end runbook: every stage from raw ingest to the Streamlit app, in
execution order, with **what** it does, **why** it exists, and **what to watch for**.

This is a narrative map, not a source of truth for numbers. For exact, current figures
see `docs/findings.md` (headline metrics), `docs/data_source_manifest.md` (columns), and
`ARCHITECTURE.md` (design rationale). For the rules that constrain every stage, see
`CLAUDE.md`; for the build order and scope contract, `ROADMAP.md`.

Orchestrated by **Dagster** (idempotent software-defined assets). Data lake is **Parquet
on Cloudflare R2**; the engine is **DuckDB** (local `dev.duckdb` for iteration,
**MotherDuck** for the served build). One `dbt build` node runs the whole SQL layer. The
genuinely hard work is concentrated in two places — **entity resolution** and
**paper↔patent NPL linkage**; everything else is plumbing around them.

> **A subtlety to hold from the start.** This is **not a clean single-pass DAG**. The dbt
> SQL layer and the ML layer are mutually entangled (ML reads dbt's staging corpus; dbt's
> marts read ML's clusters), so a full build resolves as **two dbt passes around the ML
> block**, bootstrapped by an "empty relation until ML has run once" default. Stage 4 and
> Stage 9 are the two dbt passes; Stage 5's `excluded_documents` output is what closes the
> loop.

---

## Stage 0 — Scope contract (precondition, not a runtime step)

**What.** Before any asset runs, scope is fixed in `ROADMAP.md` Part 0: three technology
families (EUV lithography; silicon photonics, incl. lasers; neuromorphic & in-memory
compute), defined by **CPC prefixes** on the patent side (G03F → EUV; H01S/G02B →
photonics; G06N/G11C/H10N → neuromorphic/in-memory) and **OpenAlex topic IDs** on the
paper side (T11338, T10299, T11429, T10502).

**Why.** Pure logic/CMOS patents are NPL-poor — they don't cite scientific literature — so
the whole paper→patent bridge would be thin outside these families. Scope is what makes the
linkage dense enough to measure.

**Watch-outs.** Any change here cascades into a re-ingest, a re-cluster, and a docs update
(per the maintenance table in `CLAUDE.md`). The most recent scope change — requiring a
scope CPC in a patent's **top-5** classifications (`cpc_sequence` 0–4) rather than anywhere
— dropped the patent corpus materially and forced a full re-cluster. Scope edits are
expensive; treat them as releases.

---

## Stage 1 — Ingest (Dagster group `ingest`) → R2 `raw/`

**What.** Two sources land as Parquet, untransformed:

- **`openalex_works_raw`** — paginates the OpenAlex `/works` API filtered to the scope
  topics + publication years, `language:en`, `has_abstract:true`; reconstructs abstracts
  from the inverted index; keeps institution IDs + ROR.
- **PatentsView bulk TSVs** (one asset per file, no API key): `patentsview_patents_raw`
  (metadata), `patentsview_applications_raw` (**filing_date** — the velocity anchor),
  `patentsview_assignees_raw` (disambiguated `assignee_id`), `patentsview_cpc_raw` (CPC),
  `patentsview_npl_raw` (`g_other_reference` NPL citation strings — the bridge fuel),
  `patentsview_citations_raw` (patent→patent edges), `patentsview_inventors_raw` (metadata
  only; person-ER is out of scope for v1).

**Why.** OpenAlex gives global research with ROR IDs (free ER wins), a topic taxonomy
(scope), and reconstructable abstracts (embeddings). PatentsView bulk gives disambiguated
assignees + CPC + the NPL citation table without API rate limits.

**Watch-outs.**

- **OpenAlex: one full run per day, max.** Smoke-test first; the pool applies escalating
  cooldowns. Always send `mailto` (polite pool).
- **PatentsView is US-only** — this constraint propagates to every headline. It is
  disclosed, never hidden.
- Writes use a **stage-then-promote** pattern (write to a temp key, then atomic rename) so
  a crash never leaves a half-written snapshot. Snapshots are date-versioned
  (`v{snapshot_date}/`).
- Filing date, not grant date, is ingested as the time anchor from the start — grant date
  is metadata only.

---

## Stage 2 — Scope filtering: `patents_scoped` (group `ingest`) → R2 `raw/…/patents_scoped/`

**What.** Joins `patents_raw` + `applications_raw` + `cpc_raw` and keeps only patents with
a **scope CPC in their top-5 classifications** (`cpc_sequence` 0–4) and **filing_date
2014–2025**. Every downstream patent asset joins against this filtered set.

**Why.** It's the patent-side realization of the Stage 0 scope contract, materialized once
so no downstream asset re-derives the filter (and they can't drift).

**Watch-outs.** The "top-5" rule is deliberately stricter than "CPC appears anywhere" — a
patent that only glances at a scope technology in its 8th classification is not in-scope. If
patent counts move sharply, suspect this join and the `cpc_sequence` bound before believing
a finding.

---

## Stage 3 — Entity resolution (group `entity_resolution`) → R2 `intermediate/er/`

The project's spine: one `org_id` per real-world organisation, unifying two sources that
**share no key**. It runs as a layered cascade, every output row tagged `match_method` +
`confidence`:

| Order | Asset | Layer | Method |
|---|---|---|---|
| 1 | `patentsview_orgs_staging` | Within-source (PV) | `native_id` (assignee_id) |
| 1 | `openalex_institutions_staging` | Within-source (OA) | `ror` |
| 2 | `seed_crosswalk_matched` | Hand-seed (PV side) | `seed_crosswalk` |
| 2 | `seed_crosswalk_oa_matched` | Hand-seed (OA side, explicit OA ID) | `seed_crosswalk` |
| 3 | `fuzzy_org_bridge` | Cross-source fuzzy | `fuzzy_high` (**score = 100 only**) |
| 3b | `ror_bridge` | OpenAlex Institutions API subset-match | `ror_bridge` |
| — | `int_organization_crosswalk` (assemble) | Union + dedupe → the crosswalk | — |

**Why.** A single false org merge poisons every downstream competitive-intelligence number
(HHI, assignee counts, leaderboards), so the whole cascade **favours precision over
recall**. Seeds handle the head of the distribution (NVIDIA, TSMC, ASML…); the ROR bridge
closes the acronym↔full-name gap that first-token blocking misses (IBM ↔ "International
Business Machines"); fuzzy at 100 sweeps the same-name long tail.

**Watch-outs.**

- **The fuzzy threshold is 100 and must stay 100.** `token_set_ratio` < 100 produced real
  false positives on institution names (Southampton↔Roehampton scored ~90). Subset/exact
  only.
- **Cross-dataset joins go through `org_id`, never a raw name string.** Hard rule.
- Quality is measured against a hand-labelled eval set (`docs/er_eval_set.md`); precision on
  the non-match tier is 1.00 at the score-100 rule. If you touch any ER threshold, re-run
  that eval and update `er_eval_set.md` + `ARCHITECTURE.md` in the same commit.

---

## Stage 4 — dbt transform, **pass 1**: staging + intermediate + base dims/facts (group `transform`, node `paper_to_patent_dbt_assets`)

**What.** `dbt build --target {dev|prod}` reads R2 raw Parquet in place via `httpfs`
external sources and builds: **staging** (`stg_patents_scoped`, `stg_openalex_works`,
`stg_assignees`, `stg_cpc`, `stg_npl`, `stg_patent_citations`), **intermediate**
(`int_org_crosswalk` from the ER output), and the **base dims/facts** that don't need
clusters or NPL yet (`dim_patent`, `dim_paper`, `dim_organization`, `dim_cpc`,
`fact_patent_filing`, `fact_publication`, `fact_patent_citation`).

**Why.** This produces the **document corpus that embeddings consume**. It also assigns each
document its **own** 5-way `family_id` directly from its CPC prefix / topic — this
per-document column, not the cluster it lands in, is authoritative for every count.

**Watch-outs.**

- **Bootstrap dependency (the entanglement).** `stg_patents_scoped` and `stg_openalex_works`
  exclude doc_ids listed in `ml_intermediate.excluded_documents` — which the ML embedding
  gate (Stage 5) produces. On a **cold pipeline that table doesn't exist yet**, so
  `create_external_sources()` defaults it to an **empty relation** and the exclusion is a
  harmless no-op. This is why staging "depends on ML having run once" without being a hard
  build error the first time.
- **Guarded against the silent-leak variant of that same gap.** A cold start is a harmless
  no-op, but a build where ML has already run and `excluded_documents` *still* comes back
  empty (a partial `document_embeddings` write, a deleted/corrupted R2 object, a
  `source_root` misconfiguration) would silently ship low-quality documents into the served
  marts with no error. `models/tests/assert_excluded_documents_not_silently_empty.sql` fails
  the build loudly in exactly that case (clusters populated, exclusions empty) while staying
  silent on genuine cold start (both empty) — per the "fail loudly, never silently coerce"
  rule in `CLAUDE.md`.
- dbt enforces `unique`/`not_null`/`relationships` here — a bad ER merge surfaces as a
  failing test, not silent corruption.

---

## Stage 5 — Embeddings: `document_embeddings` (group `ml`, a `multi_asset`) → R2 embeddings + `excluded_documents`

**What.** Reads the scope corpus from the warehouse, embeds every document with
**`all-MiniLM-L6-v2` (384-dim) on CPU**, batched. A **quality gate** (`resolve_paper_text`)
runs four ordered checks per paper: version-style title → exclude; placeholder/<50-char
abstract → fall back to title; non-English abstract (`langdetect`) → title if the title is
English else exclude; otherwise use the abstract. It emits **two** outputs in one pass: the
embeddings **and** `excluded_documents` (the doc_ids Stage 4 staging filters out).

**Why.** One computation decides both the embedding corpus and the served corpus, so they
**cannot drift** the way two independently-written SQL filters would. The gate exists
because purity analysis found artifact clusters built from "Abstract not provided."
placeholders and mistagged non-English theses — non-content text was diffusing the whole
embedding space, not just forming its own clusters.

**Watch-outs.**

- CPU-bound but fine at this scale (minutes). No GPU by design.
- Patents have no abstracts in the bulk data — they embed on title only. A known asymmetry
  vs papers.
- This is the asset whose `excluded_documents` output closes the Stage 4 bootstrap loop.

---

## Stage 6 — Clustering: `document_clusters` (group `ml`, deps `document_embeddings`) → R2 clusters + `cluster_terms`

**What.** **UMAP → 2D** (cosine, `n_neighbors=15`, `min_dist=0.1`) → **HDBSCAN**
(`min_cluster_size=50`, `min_samples=50`) → **c-TF-IDF** top terms per cluster. Noise →
`c_noise`. (Current cluster count and noise rate: see `docs/findings.md` and
`ARCHITECTURE.md` §8.)

**Why UMAP+HDBSCAN over K-Means/LDA.** Technology families are organic and uneven; K-Means
forces spherical equal clusters and needs a preset *k*; HDBSCAN finds variable-density
clusters and gives a **principled noise bucket** surfaced honestly as a "frontier /
unclustered" zone.

**Watch-outs — the most-investigated step in the project.**

- **UMAP is non-deterministic in this environment** even with `random_state=42`
  (numba/float non-determinism). Independent runs on identical input give different cluster
  counts and noise rates, so cluster IDs and even the noise rate are stable only *within one
  persisted snapshot*.
- **The freeze is the fix.** The asset stamps a `corpus_signature` (16-char sha256 of the
  sorted-deduped doc-id set) onto `clusters.parquet` and, each run, compares the current
  corpus signature to the stamped one: **identical → reuse the frozen snapshot (skip
  re-cluster); different (documents onboarded) → cut a fresh dated snapshot.** Clustering is
  now a function of its input corpus, not the wall clock — idempotent on an unchanged
  corpus, re-cut only when the corpus genuinely changes. This is what stops taglines,
  `findings.md`, and `cluster_label_review.md` silently invalidating on rerun.
- **The noise rate is intrinsic, not a tuning miss.** An un-confounded dimensionality sweep
  confirmed higher-D UMAP is *worse* (more noise) at flat purity. Don't re-litigate this
  without a new embedding model or scope change. Full evidence in `ARCHITECTURE.md` §8.
- **The 2D coords are not actually plotted** — the live map is a bubble chart (Stage 10), so
  `umap_x`/`umap_y` are effectively vestigial (no UI query reads them; the dead
  `load_umap_points()` helper that once did was removed). Clustering dimensionality is
  therefore a free parameter, unconstrained by the plot.

---

## Stage 7 — Cluster labels: `cluster_labels` (group `ml`, deps `document_clusters`) → R2 labels

**What.** For each cluster, feeds the top c-TF-IDF terms + representative document titles to
**Claude Haiku**, which writes a `tagline` (2–6 words) and a 2–3 sentence
`summary_friendly`. `c_noise` gets a fixed label with no API call.

**Why.** The readability contract: a reader sees "EUV Lithography", never "cluster 23". The
LLM is grounded strictly on the cluster's own terms/docs — it names, it does not invent
facts.

**Watch-outs.** Spend-capped (a few dollars total). Because it's downstream of the (now
frozen) clustering, labels are stable run-to-run — but if you ever force a re-cluster,
labels regenerate and `cluster_label_review.md` must be refreshed.

---

## Stage 8 — NPL linkage: `npl_links_raw` (group `transform`, npl_matcher) → R2 `intermediate/npl/`

**What.** Resolves paper↔patent edges from the free-text `g_other_reference` strings. **DOI
route** (regex → exact join, `confidence=high`); **fuzzy route** (inverted-index + rapidfuzz
title match, `confidence=medium`). Reads `stg_npl` + `stg_openalex_works` from the
warehouse; writes `npl_links.parquet`.

**Why.** An NPL citation is a **real directed link** from a patent to the literature it
cites — the analytical core. The interval from paper `publication_date` → citing patent
`filing_date` is the **citation lag**.

**Watch-outs.**

- **It is "citation lag", never "lead time" / "time to market" / "R&D-to-commercialisation".**
  Those imply causation the data doesn't support. Hard rule.
- **Anchored on filing date, never grant.** Grant carries years of administrative lag.
- Quality is measured against the **Marx & Fuegi gold eval set** (precision/recall recorded
  in `docs/data_source_manifest.md`). Unmatchable references are dropped → the linkage is a
  high-precision **sample**, not exhaustive.

---

## Stage 9 — dbt transform, **pass 2**: cluster/NPL-dependent facts + marts

**What.** With Stages 5–8 done, `dbt build` finalizes: `fact_document_cluster` (reads
`clusters.parquet`), `dim_technology_cluster` (reads labels), `fact_npl_link` (reads
`npl_links.parquet`), `seed_cluster_family` (cluster→family roll-up), and the gold marts
**`mart_velocity`, `mart_competitive`, `mart_gap`, `mart_family`**. Staging now also
actually excludes `excluded_documents` (no longer an empty relation).

**Why.** Marts are the single source of truth the UI reads; each gold mart carries a
top-of-file comment stating the claim it backs and its basis (NPL-linked vs co-occurrence vs
descriptive count).

**Watch-outs — the two-tier family scheme + the Mixed floor.**

- **Two grains, deliberately not one.** Per-document `family_id` (5-way, on
  `fact_patent_filing`/`fact_publication`) is authoritative for **counting**. Cluster-level
  `seed_cluster_family` (3-way) is **display-only** — map colour and cluster cards.
- **The confidence floor.** A cluster gets a real family only when a single family is
  **≥ 80% of its family-resolvable docs AND those resolvable docs are ≥ 50% of the
  cluster**. Otherwise it's **`mixed`** (renamed from the earlier "adjacent"). Clusters that
  fail the floor — genuinely two-family or mostly off-scope patent thickets — go to Mixed
  and are excluded from headline charts. The current Mixed list is in
  `docs/cluster_label_review.md`.
- A singular dbt test (`models/tests/assert_seed_cluster_family_floor.sql`) re-derives
  purity/coverage and fails if a real-family label doesn't meet both thresholds (or a Mixed
  label does). Don't weaken the floor without that test going green.
- **Deployment coupling.** `seed_cluster_family` (a `models/**` change) and the UI's
  `adjacent`→`mixed` rename must ship in the **same PR** — merging to main triggers the
  MotherDuck prod rebuild, and the app filters `mixed`; a split deploy briefly mismatches.

---

## Stage 10 — Serving: MotherDuck + Streamlit (`apps/ui/`)

**What.** The prod `dbt build --target prod` materializes marts straight into **MotherDuck**
(`md:paper_to_patent`). The Streamlit app (Community Cloud) reads them with **in-process
DuckDB** (`md:` + token), cached via `st.cache_data`/`st.cache_resource`. Pages: `app.py`
(overview/scorecard), `1_Map.py` (**per-cluster patents×papers bubble chart**, colour =
family), `2_Family.py` (the 3 headline families), `3_Org.py` (ILIKE org searchbox),
`4_Trace.py` (trace a paper→patent journey); `data.py` (connection + queries), `render.py`
(Plotly + FAMILY_COLORS/LABELS), `tour.py`.

**Why.** MotherDuck is the same DuckDB engine the marts were built with, so the app queries
it directly — no export step to keep in sync. This **replaced** the prior "export versioned
gold Parquet to R2, read over httpfs" design: one served source of truth, no
`R2_SNAPSHOT_DATE` to coordinate.

**Watch-outs.**

- The dev/prod switch (local `dev.duckdb` vs MotherDuck) is resolved **once** —
  `resources/warehouse.py` for the pipeline, `apps/ui/data.py` for the app. Assets never
  re-derive it. Both pick MotherDuck when `MOTHERDUCK_TOKEN` is set.
- The app should run on a **read-only** MotherDuck token, but the free tier can't issue one,
  so it currently shares the build's read-write token — accepted risk (warehouse is fully
  rebuildable from R2 in about a minute, so a leak means downtime not data loss; app kept
  private meanwhile).
- **The UI shows confidence.** An NPL-linked lag is rendered differently from a
  co-occurrence signal — the reader always knows hard link vs soft.
- Streamlit `session_state` + `st.rerun()` has a known footgun with `key=` on text inputs
  alongside `st.page_link`; and Windows hot-reload misses changes (kill process + clear
  `__pycache__`).

---

## Cross-cutting — CI / quality gates (every merge)

GitHub Actions runs **ruff + pyright (strict on `pipelines/`, basic on `apps/ui/`) +
pytest** on every PR; all must pass before merge. Every Dagster asset has a fixture-based
**value** test (not just "runs"). ER and citation-lag logic get tests on hand-labelled
fixtures. Docs are updated **in the same commit** as the change that triggers them
(maintenance table in `CLAUDE.md`).

---

# Strengths & weaknesses of the workflow

## Strengths

1. **Complexity is spent where it belongs.** ER and NPL linkage — the two places a
   paper→patent claim actually gets made or broken — carry real rigour (layered cascade,
   score-100 precision rule, gold-eval benchmarking). Storage and warehouse are deliberately
   lean. That allocation is architecturally mature.
2. **Provenance is structural, not cosmetic.** Every match/edge carries `match_method` +
   `confidence`, and the UI renders it. The single most credible thing about the project to
   a skeptical reviewer.
3. **Honesty is enforced in the schema, not just the README.** "Citation lag" is dated from
   filing; correlational signals never sit in a column implying causation; US-only is stated
   everywhere. The vocabulary discipline is a genuine differentiator.
4. **The lakehouse-lite topology fits the data.** R2 + DuckDB + MotherDuck at ~1–2 GB is
   right-sized; no cosplay infrastructure. Zero-egress R2 + same-engine MotherDuck removes
   an entire class of export-staleness bugs.
5. **The clustering freeze finally makes the pipeline honestly idempotent.** Keying
   re-cluster on a corpus signature (rather than chasing UMAP determinism) is the correct
   engineering call — it re-cuts exactly when the corpus changes and not otherwise.
6. **Reproducibility is first-class.** dbt tests guard the joins, every asset is
   fixture-tested, lineage is a readable Dagster graph.

## Weaknesses

1. **The dbt↔ML entanglement is the real fragility.** Staging depends on ML's
   `excluded_documents`; marts depend on ML's clusters; ML depends on staging's corpus. It's
   resolved by an "empty relation until ML runs once" bootstrap + effectively two dbt passes
   — clever, but it means a cold rebuild has an ordering that isn't expressible as one clean
   DAG, and a newcomer running "materialize all" once may get a subtly incomplete first
   build. The least obvious, most bite-prone part of the system. **Partially mitigated**: the
   silent-leak variant (ML has run, but `excluded_documents` still resolves empty) now fails
   the build loudly via `assert_excluded_documents_not_silently_empty.sql` — the ordering
   itself is still two passes, but it can no longer fail *quietly*.
2. **The clustering noise rate is a real product ceiling.** It's been proven intrinsic to
   the embedding geometry (not a tuning miss), which is honest — but a large minority of
   documents sit in "frontier/unclustered" and never join a named family on the map. The
   finding is well-defended; the *coverage cost* remains. A stronger domain-tuned embedding
   is the only real lever, and it's out of scope.
3. **The map underuses its own computation.** UMAP produces 2D coords that aren't plotted
   (the map is a bubble chart) — `umap_x`/`umap_y` are written to `fact_document_cluster`
   and never read by the UI (the dead `load_umap_points()` query that once read them was
   removed 2026-07-10). So the entire UMAP step exists **only** to feed HDBSCAN — a lot of
   non-deterministic machinery for a partition, with the spatial output discarded.
   Defensible, but worth naming.
4. **US-only + English-only is a structural, not incidental, limitation.** For
   semiconductors especially, most patenting is non-US. The framing ("global research vs
   *US* commercialisation") is honest, but it caps how strong any "who captures the IP" claim
   can be. A v2 data-coverage problem, not a code problem.
5. **No versioned history of served snapshots.** Each prod build overwrites MotherDuck
   (`CREATE OR REPLACE`); the immutable R2 gold layer was traded away for a single source of
   truth. Fine for a point-in-time portfolio piece, but there's no time-travel on the served
   marts, and the app's availability is now coupled to MotherDuck's free-tier caps.
6. **The app has no automated test suite.** `apps/ui/` is ruff+pyright-only; pages are
   exercised manually, and pyright runs at `basic` there. The most demo-visible layer is the
   least-tested one — a `data.py` query regression wouldn't be caught by CI. **Partially
   mitigated**: `apps/ui/tests/test_data.py` now covers `data.py`'s main query-function shapes
   (plain select+order, aggregation with an exclusion invariant, join+coalesce+filter, window
   ranking, ilike search) against a fixture DuckDB warehouse, plus the shared `_query()` error
   path. It is deliberately thin, not exhaustive over all query functions, and pages themselves
   are still exercised manually — no `AppTest`-style page-level coverage.
7. **NPL linkage is a high-precision *sample*, not a census.** Unmatchable references are
   dropped, so absolute link counts understate reality and vary with matcher recall. The
   precision claim is solid; anyone reading a raw count of links should know it's a floor.
