# Paper → Patent: The Chips Behind AI

Tracing science-adjacent microchip hardware — EUV lithography, silicon photonics, neuromorphic & in-memory compute — from research paper to US patent.

We ingest global scientific output (OpenAlex) and US patents (PatentsView bulk data), resolve the organisations behind both into one identity, link papers to the patents that cite them via non-patent-literature (NPL) citations, cluster everything into named technology families, and surface three things:

- The **citation lag** between a paper's publication and the filing of the patent citing it
- **Who is capturing the IP** (assignee competitive intelligence)
- **How concentrated US patenting is** relative to the breadth of global research

A curious teenager should grasp the map in 90 seconds. An R&D strategist or VC analyst should respect the linkage methodology.

> **Scope**: US patents only (PatentsView). English-language papers only (OpenAlex). Citation lag is publication → filing date — it is not R&D-to-market time and does not imply causation.

---

## Status

<!-- MAINTAINED: status -->
| Part | Description | Status |
|---|---|---|
| 0 | Pre-flight + NPL feasibility spike | ✅ Done |
| 1 | Foundation + OpenAlex ingest | ✅ Done |
| 2 | PatentsView bulk ingest | ✅ Done |
| 3 | Entity resolution + organisation crosswalk | ✅ Done |
| 4 | dbt modeling + NPL linkage + gold eval | ✅ Done |
| 5 | Embeddings, clustering, and interpretable labels | ✅ Done |
| 6 | Citation-lag & competitive-intelligence analytics | ✅ Done |
| 7 | Streamlit app + polish | ⬜ Pending |
| 8 | Documentation, deploy, portfolio integration | ⬜ Pending |
<!-- /MAINTAINED -->

---

## Tech stack

Python 3.11+ · `uv` · `ruff` · `pyright` strict · `pytest` · Terraform 1.9+ · Dagster OSS · Cloudflare R2 · Parquet · DuckDB · dbt-core + dbt-duckdb · `polars` · `sentence-transformers` (`all-MiniLM-L6-v2`) · `umap-learn` + `hdbscan` · `langdetect` · `rapidfuzz` · Streamlit · Plotly (`scattergl`) · Claude Haiku (cluster labels)

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for design rationale and [`ROADMAP.md`](ROADMAP.md) for the build plan.

---

## Repo layout

```
pipelines/     Dagster project; package `nexus/`
models/        dbt project (sources → staging → intermediate → marts)
apps/ui/       Streamlit app (Community Cloud)
infra/         Terraform (Cloudflare R2)
docs/          Data source manifest, eval sets, cluster label review
notebooks/     Exploratory; never imported by pipelines
```

---

## Running locally

```bash
cp .env.example .env.local   # fill in credentials
uv sync
uv run --env-file .env.local dagster asset materialize -m nexus --select openalex_works_raw
uv run pytest
uv run ruff check pipelines/nexus/
uv run pyright pipelines/nexus/
```

See [`SETUP.md`](SETUP.md) for the full credential checklist.

---

## License

Data sources: OpenAlex (CC-BY 4.0), PatentsView (CC-BY 4.0), Marx & Fuegi dataset (CC-BY 4.0).
Code: MIT.
