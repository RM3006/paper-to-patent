# CLAUDE.md — Paper → Patent

**"The Chips Behind AI"** — tracing science-adjacent microchip hardware (EUV lithography, silicon photonics, neuromorphic & in-memory compute) from research paper to US patent. We ingest global scientific output (OpenAlex) and US patents (PatentsView bulk data), resolve the organisations behind both into one identity, link papers to the patents that cite them via non-patent-literature citations, cluster everything into named technology families, and surface three things: the citation lag between a paper's publication and the filing of the patent citing it, who is capturing the IP, and how concentrated US patenting is relative to the breadth of global research. A curious teenager should grasp the map in 90 seconds; an R&D strategist or VC analyst should respect the linkage methodology and the entity resolution.

## Hard rules

1. **Organisation joins go through the crosswalk.** Cross-dataset org joins use `org_id` from `int_organization_crosswalk`. Never join on a raw name string. Within a single source, use that source's native disambiguated ID: OpenAlex institution ID / ROR for papers, PatentsView `assignee_id` for patents.
2. **Velocity is dated from filing, never grant. The metric is citation lag, not lead time.** The interval between a paper's `publication_date` and a citing patent's `filing_date` is a **citation lag** — the time between publication and the moment a patent referenced it. It is never described as "lead time", "time to market", or "R&D-to-commercialisation time"; those phrases imply causation the data does not support. Grant date carries years of administrative lag and is never used for any time metric. Grant date may be displayed as metadata only.
3. **Every link and match carries provenance and confidence.** See the provenance pattern below. No paper↔patent edge and no org match exists in a mart without a `match_method` and a `confidence`. A correlation is never written to a column that implies a causal link.
4. **The patent lens is US-only, and we say so.** PatentsView is US patents. The UI, README, and every chart that could be misread as global patent coverage states the limitation in plain language. We never imply we see EPO/WIPO/CN filings.
5. **No invented data.** Missing field → `NULL`. Never synthesise a value, a link, an abstract, or an organisation. A paper→patent link exists only if it is in the non-patent-literature citation data, or it is an org-level co-occurrence explicitly labelled as such.
6. **No secrets in code.** Env vars or `.env.local` only.
7. **No CSV in pipelines.** Parquet, the DuckDB warehouse, or formal clients. CSV is debug-only.
8. **Idempotent assets.** Every Dagster asset is safe to rerun.
9. **No new dependencies without asking.** Stack is fixed below.
10. **Tests for every asset.** One fixture-based correctness test, next to the code. Tests check values, not just "runs without error." Entity resolution and lead-time logic get tests on hand-labelled fixtures, not just schema checks.
11. **`ruff`, `pyright`, `pytest` all pass before merge.** No `print` in production paths; use `from nexus.logging import logger`.
12. **Dynamic documentation.** Update the affected `docs/` files in the same commit as the change that triggers it (see the maintenance table).

## Provenance & confidence pattern (the integrity backbone)

This is the project's signature pattern — the analog of a curation tier, but for trust rather than polish. Every organisation match and every paper↔patent edge carries two columns:

- `match_method` — one of: `native_id`, `ror`, `seed_crosswalk`, `fuzzy_high`, `fuzzy_review`, `npl_citation`, `org_cooccurrence`.
- `confidence` — `high` | `medium` | `low`.

Rules that follow from it:
- The UI **shows** confidence. An NPL-citation-linked lead time is presented differently from a co-occurrence signal. The user always knows whether they are looking at a hard link or a soft one.
- `fuzzy_review` rows (matches below the auto-accept threshold) never enter a mart silently — they are either resolved in the eval set or excluded.
- Any headline number in the UI must be reproducible from a single gold mart whose top-of-file comment states the claim's basis.
- **NPL linkage quality is measured against the Marx & Fuegi gold eval set** (their matched pairs joined to OpenAlex via `ids.mag`). Precision and recall vs that benchmark are recorded in `docs/data_source_manifest.md` and disclosed in the UI methodology footer.

## Tech stack (fixed — ask before deviating)

Python 3.11+ · `uv` · `ruff` · `pyright` strict · `pytest` · Terraform 1.9+ · Dagster OSS (with `dagster-dbt`) · Cloudflare R2 · Parquet · DuckDB (embedded analytical warehouse) · dbt-core + dbt-duckdb · `polars` (not pandas) · `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) · `umap-learn` + `hdbscan` (BERTopic is an acceptable wrapper) · `scikit-learn` · `rapidfuzz` (ER fuzzy bridge; `splink` only if rapidfuzz precision on the eval set falls below 0.95) · Streamlit (Community Cloud) · Plotly (`scattergl`) · Claude Haiku for cluster labels.

**Deliberately not in the stack** (divergence from prior projects — reasons in `ARCHITECTURE.md`):
- **No managed warehouse** (MotherDuck / Snowflake / BigQuery). The served dataset is single-digit MB and the whole corpus is ~1–2 GB; DuckDB over R2 Parquet covers both build and serve. A managed warehouse would add a service, a credential, and a usage cap without solving a problem at this scale.
- **No Modal / no GPU.** `all-MiniLM-L6-v2` is small; embeddings run on CPU inside a Dagster asset.
- **No Qdrant.** Clustering, not similarity search, is the product. UMAP coordinates live in the warehouse; in-warehouse cosine covers any future "related work" need.

## Repo layout

```
CLAUDE.md  README.md  ARCHITECTURE.md  ROADMAP.md  SETUP.md  pyproject.toml  .env.example
docs/        data-source manifest, CPC/topic seed lists, ER eval set, cluster-label review
infra/       Terraform modules (R2)
pipelines/   Dagster project; package `nexus/`
             (assets/ingest, assets/entity_resolution, assets/transform, assets/ml,
              resources, tests)
models/      dbt project (sources, staging, intermediate, marts)
apps/ui/     Streamlit on Community Cloud
notebooks/   exploratory; never imported elsewhere
```

One module per data source under `pipelines/nexus/assets/ingest/` (`openalex.py`, `patentsview.py`). Entity-resolution logic lives under `pipelines/nexus/assets/entity_resolution/`, never inline in an ingest asset. The package is imported as `nexus` (e.g. `from nexus.logging import logger`).

## Conventions

- Type hints on every signature.
- Docstrings only where logic is non-obvious.
- `pathlib.Path` over `os.path`.
- Every Dagster asset has a docstring naming (1) what it produces, (2) its dependencies, (3) where the output lands (the R2 path or the warehouse model).
- Every gold mart that backs a UI claim has a top-of-file comment stating the claim and its basis (NPL-linked vs co-occurrence vs descriptive count).
- **PatentsView is ingested via bulk TSV files from data.uspto.gov** (no API key required for bulk; CC-BY-4.0). The PatentSearch API (`search.patentsview.org`) is used only for supplementary targeted lookups and is accessed through one shared client with header auth, cursor pagination, and exponential backoff — never ad-hoc `requests` calls scattered across assets.
- OpenAlex requests always pass `mailto` (the polite pool). Abstracts are reconstructed from `abstract_inverted_index` in one tested helper.
- **DuckDB reads R2 via `httpfs` with the R2/S3 secret configured once in a shared helper** (`resources/duckdb.py`); never re-declare credentials per query. dbt-duckdb uses the same configuration.
- **The Streamlit app reads the gold Parquet in R2 with a read-only R2 token** (least privilege), never the read-write build credentials.

## Two-tier readability pattern

The atlas covers every document that passes the technology filter — tens of thousands of papers and patents. A human never reads a cluster ID. Each technology cluster (there will be dozens, not thousands) gets a Claude-Haiku-written **name** (`tagline`) and a 2–3 sentence **plain-English description** (`summary_friendly`), grounded only in the cluster's top terms and representative documents. Individual abstracts are shown verbatim on expand; we do not rewrite every document. The reader meets named technology families, trends, and company names — never raw model output.

## Where to find answers

| Question | File |
|---|---|
| What does this column mean? | `docs/data_source_manifest.md` |
| Which CPC codes / OpenAlex topics define the scope? | `ROADMAP.md` Part 0 (scope contract) |
| How is entity-resolution quality measured? | `docs/er_eval_set.md` |
| Which cluster labels were reviewed? | `docs/cluster_label_review.md` |
| What's the current task? | `ROADMAP.md` |
| Why was this designed this way? | `ARCHITECTURE.md` |

## Documentation maintenance

Project documentation is kept in sync with code. Any commit whose change matches a trigger below must include an update to the listed file(s) in the same commit. A PR that violates this rule does not pass review.

| Change trigger | Files to update |
|---|---|
| Tech stack change (add or remove a dependency, service, or version) | `README.md`, `CLAUDE.md`, `ARCHITECTURE.md` |
| Schema change (new table, new column, changed join key) | `docs/data_source_manifest.md`, `ARCHITECTURE.md` |
| Scope change (CPC codes or topics added/removed; feature added/removed) | `ROADMAP.md` Part 0 scope contract, `README.md` |
| ER method or threshold change | `docs/er_eval_set.md`, `ARCHITECTURE.md` |
| Status milestone (a Part is completed) | `README.md` (Status section, checkbox) |
| New data source added | `docs/data_source_manifest.md`, `README.md`, `ARCHITECTURE.md` |
| Architecture change (component added, removed, or repurposed) | `README.md`, `ARCHITECTURE.md` |
| License change | `README.md`, every file with attribution |
| Repo structure change | `README.md`, `CLAUDE.md` |

Sections in `README.md` and `ARCHITECTURE.md` marked with `<!-- MAINTAINED: name -->` ... `<!-- /MAINTAINED -->` comments are the auto-updated targets — locate them by searching the marker. Edit only inside the marker pair; do not move or rename the markers.

When starting a session that touches any trigger above, **read the affected MAINTAINED sections first** so the doc update is part of the same edit pass as the code change, not an afterthought.
When ending a dedicated part of the ROADMAP as defined in `ROADMAP.md`, properly update all docs files.

## When unsure

Stop and ask. If a source returns something unexpected, fail loudly with a clear error — never silently coerce. If an analytical result looks surprising, suspect the join and the dates before believing the finding.
