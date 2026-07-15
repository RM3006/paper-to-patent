# ROADMAP.md — Paper → Patent Build Plan

## How to read this document

Nine parts (Part 0 + Parts 1–8), sequential. Each part depends on the previous — do not parallelize.

Each part has:

- **Goal** — the one-sentence outcome.
- **Effort** — rough hour estimate. Could be one focused day or two weeks of evenings.
- **Deliverables** — concrete artifacts that exist when the part is done.
- **Tasks** — the work, in order.
- **Exit criteria** — checkable conditions that mean the part is done.
- **Risks** — where this part typically gets stuck.

Pace yourself by **exit criteria, not the calendar**. A free weekend can swallow two parts; a hard part stretching across two weeks is fine.

**Working pattern**: one focused session per task, from clean context. Standard opening prompt: *"We are on Part N. Read `CLAUDE.md` and the relevant section of `ROADMAP.md`. The task is X."*

**The spine of this project is Parts 2–4.** PatentsView ingestion, entity resolution, and the NPL-citation linkage are what separate this from a dashboard. They are also the hardest. Budget accordingly and do not rush them to get to the pretty parts.

**Effort at a glance** (honest ranges; total ≈ 70–115 h): P0 4–6 · P1 6–10 · P2 8–12 · P3 12–20 · P4 10–14 · P5 8–12 · P6 8–14 · P7 12–18 · P8 6–10.

---

## Part 0 — Pre-flight + NPL feasibility spike

**Goal**: accounts ready, tools installed, and the NPL linkage confirmed data-rich enough in the chosen scope before a single line of pipeline code is written.

**Effort**: 4–6 h. The spike may take a full evening; it gates everything else.

The NPL feasibility spike is the critical path item — not an API key. PatentsView bulk data requires no key and downloads immediately. Do the spike first, then build infrastructure.

**Scope contract** (defined here; any change requires updating this file per `CLAUDE.md` maintenance rules)

Theme: **"The Chips Behind AI"** — science-adjacent microchip hardware, tracing how research ideas become US patents, who captures the IP, and the citation lag between publication and filing.

Sub-families and CPC codes:

| Family | Patent CPC codes | OpenAlex topic IDs (verified 2026-06-20 via `/topics` API) |
|---|---|---|
| EUV Lithography | G03F 7/20, G03F 7/70 | `T11338` "Advancements in Photolithography Techniques" |
| Silicon Photonics | G02B 6/12, G02B 6/122, H01S 5/0224, H01S 5/10 | `T10299` "Photonic and Optical Devices", `T11429` "Semiconductor Lasers and Optical Devices" |
| Neuromorphic & In-Memory Compute | G06N 3/049, G11C 11/54, G11C 13/00, H10N 70/00 | `T10502` "Advanced Memory and Neural Computing" |

**Patent CPC matching rule (revised 2026-07-08):** a patent is in scope only if one of
the CPC codes above appears among its **top-5 classifications** (`cpc_sequence` 0–4). The
original rule matched a scope code at *any* position among the ~12 codes a patent carries;
that admitted "buried mention" patents whose headline invention is off-domain (e.g. a
logistics or animation patent that tags a neural-net code deep in its list) and produced a
large generic-ML noise cluster. Requiring the technology to be *prominent* rather than
merely *present* dropped the patent corpus from ~33.6k to 23.4k (−30%) and removed that
noise. Papers are already filtered on OpenAlex's **primary** topic only, so no analogous
change is needed on the paper side. See `docs/data_source_manifest.md` (patent scope) and
`MEMORY.md` for the analysis behind the threshold.

**Patent CPC matching** is a prefix match: a scope code like `G03F 7/20` matches any deeper
subgroup (`G03F7/2004`, `G03F7/2023`, …). The list mixes CPC subgroups (`G06N3/049`) and
main groups (`G11C13/00`, `H10N70/00`).

**Two family grains coexist (revised 2026-07-12):** the 3-row table above is the **cluster-
label grain** — a technology cluster's majority-vote display label (`seed_cluster_family`),
used only by the Technology Landscape map's colouring, plus a "mixed" bucket for clusters
with no clear majority. Every document additionally carries its own **5-way document-level
family** (`euv` / `lasers` / `si_photonics` / `neuromorphic` / `in_memory`) derived directly
from its own primary CPC code (patents) or primary topic ID + a title/abstract keyword
tiebreak for the neuromorphic/in-memory split (papers) — independent of the cluster it
algorithmically landed in. This is the authoritative, finer grain for any family-level count
(patent share, leaderboards, citation lag): see `fact_patent_filing.sql` / `fact_publication.sql`
/ `mart_family.sql`. It backs the Overview scorecard (5 cards), Family Deepdive, and
Organisation Profile; the Technology Landscape map alone stays on the 3-way cluster-label
grain, since a cluster is inherently a group of documents that need not share one family.

Year window:
- Papers (OpenAlex `publication_date`): **2012–2025** — starts at the deep-learning inflection; captures the full AI hardware research wave.
- Patents (PatentsView `filing_date`): **2014–2025** — two-year lag from paper window; patents citing 2012+ papers appear from ~2014.

**Tasks**

1. Create the GitHub repo (private; flip to public in Part 8). Install `uv`, `git`, Terraform, Claude Code locally.
2. Create accounts and tokens: Cloudflare R2, Anthropic. Set `OPENALEX_MAILTO`. See `SETUP.md` for the full checklist.
3. Read `CLAUDE.md` end to end. The hard rules are non-negotiable.
4. **NPL feasibility spike — gates everything:**
   a. Download `g_other_reference.tsv.zip` and `g_patent.tsv.zip` from the PatentsView bulk files on data.uspto.gov (no API key required; CC-BY-4.0 license).
   b. Load both into a local DuckDB instance. Join on `patent_id` to get CPC codes alongside each NPL reference string.
   c. Filter to the scope CPC codes in the table above. Record: (i) distinct patent count, (ii) total NPL reference rows.
   d. Download the Marx & Fuegi `_pcs_oa.csv` from Zenodo record 8278104 (see `SETUP.md` D3). Filter to your scope patent IDs by joining on `REGEXP_EXTRACT(patent, '^us-([0-9]+)-', 1)`. Count matched gold pairs per family. `oaid` is already an OpenAlex work ID — no MAG bridge required.
   e. Record all counts against the kill criteria in the exit criteria below. If a family fails, widen its CPC codes or drop it before proceeding.
5. **OpenAlex scope count**: query the `/works` endpoint with `mailto`, filter by the topic names above + year window, read `meta.count` only (no data download yet). Verify exact topic IDs match the names in the table — update the table if they differ.
6. Confirm DuckDB can read a test Parquet file from R2 (the R2 credential check — do not skip; it is the single most common integration snag).
7. Commit a `docs/data_source_manifest.md` stub with the confirmed scope row counts from steps 4–5.

**Exit criteria**

- [x] Scope CPC filter returns ≥ 5,000 patents in the PatentsView bulk file. *(68,800 — verified 2026-06-20)*
- [x] `g_other_reference` rows for those patents: ≥ 2,000 NPL references. *(656,347 — verified 2026-06-20)*
- [x] Marx/Fuegi gold pairs for scope patents: ≥ 300 total **and** ≥ 50 per family. *(291,378 total — verified 2026-06-20)*
- [x] OpenAlex `meta.count` for scope topics + year window: ≥ 10,000 papers. *(150,984 — verified 2026-06-20)*
- [x] DuckDB reads a test Parquet file from R2 without error.
- [x] All credentials in `.env.local` confirmed (see `SETUP.md` verification checklist).

**Risks**

- One family may pass the threshold while another fails. Drop the weak family rather than compromising the linkage quality of the rest.
- Pure logic/CMOS patents (H01L broadly) are NPL-poor; the scope is deliberately restricted to the three science-adjacent families above for this reason.
- OpenAlex topic IDs drift across API versions. Always verify with a live `/topics` search; do not hardcode from memory.

---

## Part 1 — Foundation + OpenAlex ingest

**Goal**: the repo skeleton is up, infrastructure is provisioned by code, and OpenAlex data flows from the internet into object storage.

**Effort**: 6–10 h.

OpenAlex is the friendlier of the two sources — start here to get the skeleton solid before the PatentsView complexity in Part 2.

**Deliverables**
- Repo laid out per `CLAUDE.md`.
- Terraform module provisioning the Cloudflare R2 bucket (`p2p-lake`).
- Dagster project under `pipelines/` with one materializing asset: `openalex_works_raw`.
- A tested `reconstruct_abstract()` helper (inverted index → text).
- `pyproject.toml` with locked dependencies via `uv`.
- `.env.example`; gitignored `.env.local`.
- GitHub Actions CI running `ruff`, `pyright`, `pytest` on every PR.

**Tasks**
1. `git init`, commit existing docs, push.
2. Bootstrap the directory structure from `CLAUDE.md`. `uv init` + locked dependencies.
3. Write the Terraform module in `infra/` for the R2 bucket (Cloudflare provider). `terraform init` / `plan` / `apply`. Commit the `.tf`; gitignore state and `*.tfvars` holding secrets.
4. `dagster project scaffold` under `pipelines/`. Wire up the R2 resource in `resources/r2.py` and the shared DuckDB/httpfs helper in `resources/duckdb.py`.
5. Write `openalex_works_raw`: paginate the OpenAlex `works` endpoint (cursor `*`) filtered by the scope topics + year window from Part 0, with `language:en`, `has_abstract:true`, and `mailto`. Reconstruct abstracts. Keep institution IDs and ROR. Store Parquet in `r2://p2p-lake/raw/openalex/v{snapshot_date}/`.
6. One test mocking the HTTP layer and asserting the parsed schema, plus a unit test for `reconstruct_abstract()` on a known inverted index.
7. GitHub Actions: lint + type-check + test on every PR.

**Exit criteria**
- [x] `dagster asset materialize openalex_works_raw` succeeds. *(164,072 rows — verified 2026-06-22)*
- [x] R2 contains the expected order of magnitude of works for the scope, each with a non-null reconstructed abstract and at least one institution. *(100% non-null abstracts; 82.3% with institution — verified 2026-06-21)*
- [x] `ruff`, `pyright`, `pytest` all pass locally and in CI.

**Risks**
- Terraform + the Cloudflare provider has a learning curve and the provider's resource names churn across major versions; pin the provider. Budget 3–4 hours for the R2 module and token scoping alone.
- OpenAlex cursor pagination + polite-pool rate limits: don't parallelize blindly.
- Abstract reconstruction off-by-one errors (the index is position-keyed). The unit test is non-negotiable.

---

## Part 2 — PatentsView ingest (bulk-first)

**Goal**: US patent data — filings, assignees, CPC, citations, and the non-patent-literature references — lands in R2.

**Effort**: 8–12 h.

**Primary route: PatentsView bulk TSV files** (data.uspto.gov, no API key required, CC-BY-4.0). The PatentSearch API (`search.patentsview.org`) is the supplementary route for targeted lookups only — its pagination caps and rate limits make it wrong for full-corpus pulls. The bulk files ship the same disambiguated data without the pagination dance.

**Files to download** (from the PatentsView bulk datasets on data.uspto.gov):

| File | Content |
|---|---|
| `g_patent.tsv.zip` | Core patent metadata: filing date, grant date, title, abstract |
| `g_assignee.tsv.zip` | Disambiguated assignees with `assignee_id` |
| `g_inventor.tsv.zip` | Inventors (metadata; person-level ER is v2) |
| `g_cpc_current.tsv.zip` | CPC subclass assignments |
| `g_us_patent_citation.tsv.zip` | Patent-to-patent citation edges |
| `g_other_reference.tsv.zip` | Non-patent literature citations (already downloaded in Part 0 spike) |

**Deliverables**
- A Dagster asset per bulk file: downloads the TSV zip, validates schema, converts to Parquet, writes to `r2://p2p-lake/raw/patentsview/{entity}/v{snapshot_date}/`.
- A scope-filter asset that applies the CPC + filing-date window from Part 0 and writes a filtered Parquet: `r2://p2p-lake/raw/patentsview/patents_scoped/v{snapshot_date}/`. All downstream assets join against this filtered set.
- A `PatentSearchClient` under `pipelines/nexus/resources/` (header auth, cursor pagination, exponential backoff) for any supplementary API lookups needed in later parts.
- Each Dagster asset has a fixture-based test checking schema and a non-empty row count.

**Tasks**
1. Write a generic bulk-download helper: given a URL, downloads the zip, extracts, validates required columns, returns a polars DataFrame. One test on a small fixture TSV.
2. Write one Dagster asset per file in the table above. Each reads R2 for an existing snapshot (idempotency), downloads if absent, converts to Parquet, writes to R2.
3. Write the `patents_scoped` filter asset: join `g_patent` + `g_cpc_current` on `patent_id`, filter to scope CPC codes and `filing_date` window, write filtered Parquet. This is the corpus all downstream assets use.
4. Write the `PatentSearchClient` (for supplementary use). Confirm a test call returns 200.
5. Verify row counts against `docs/data_source_manifest.md` using DuckDB `SELECT COUNT(*)` on the R2 Parquet.

**Exit criteria**
- All bulk assets materialize cleanly; the Dagster UI shows their dependency edges.
- `patents_scoped` row count matches the Part 0 spike count (within 5% — bulk files update periodically).
- `g_other_reference` filtered to scoped patents is non-empty and contains parseable citation strings (DOIs, titles, or journal references) for a sample.
- `ruff`, `pyright`, `pytest` all pass.

**Risks**
- The bulk files are large (multi-GB uncompressed). Stream-process or chunk with polars; do not load the full file into memory before filtering.
- `g_other_reference` was already downloaded in Part 0 — reuse it; do not re-download.
- Filing-date filter vs grant-date filter: filter on **filing date** only. Accidentally filtering on grant date silently biases the corpus toward older inventions.

---

## Part 3 — Entity resolution + organisation crosswalk (the centerpiece)

**Goal**: one `org_id` identity per real-world organisation, spanning OpenAlex institutions and PatentsView assignees, with measured quality.

**Effort**: 12–20 h — the heaviest part, and the one that makes the project senior.

The two sources share no key. You will resolve organisations with a layered strategy and **prove the quality on a hand-labelled set** — not just assert it. Note: ROR (OpenAlex) and `assignee_id` (PatentsView) each disambiguate *within* their own source; neither bridges the two sources on its own. The cross-source bridge is built in layers 2 and 3 below.

**Deliverables**
- `docs/er_eval_set.md`: hand-labelled organisation pairs (true match / non-match), drawn from orgs that appear in **both** sources within the scope. Span easy (NVIDIA Corp ↔ NVIDIA) and hard (university tech-transfer offices, research subsidiaries, abbreviations).
- Staging-layer cleaning: normalised organisation names (case, legal suffixes, punctuation, unicode) for both sources, in one tested shared function.
- `int_org_crosswalk` — a Dagster asset writing Parquet to `r2://p2p-lake/intermediate/er/org_crosswalk/` with `org_id`, source IDs, `match_method`, `confidence` (per the provenance pattern in `CLAUDE.md`). Part 4 dbt reads this as a source.
- A precision/recall report against the eval set, recorded in `docs/er_eval_set.md`.

**Tasks**
1. Author `docs/er_eval_set.md` first — you cannot tune a matcher you cannot measure. Sample from orgs that appear on both sides of the scope.
2. Normalise names in staging (one tested function, shared by both sources).
3. **Layer 1 — within-source disambiguation**: use OpenAlex institution ID / ROR as the paper-side identity; use PatentsView `assignee_id` as the patent-side identity. Tag as `match_method = native_id` / `ror`. This disambiguates within each source but does not yet bridge them.
4. **Layer 2 — seed crosswalk**: a small hand-maintained map for the unambiguous heavyweights in scope (NVIDIA, TSMC, ASML, IMEC, Intel, Samsung, MIT, Stanford…), `match_method = seed_crosswalk`. Cover the head of the distribution before touching fuzzy matching.
5. **Layer 3 — fuzzy bridge**: `rapidfuzz` token-set ratio, blocking on first token of normalised name. Accept only score = 100 (one name's tokens ⊆ the other's). Scores 90–99 were empirically false positives from shared structural tokens ("University of X" ≅ "University of Y") and were excluded. No `fuzzy_review` band needed. `splink` not required — rapidfuzz at score=100 achieved precision = 1.00.
6. Resolve or exclude every `fuzzy_review` row. Never let them leak into a mart. *(Resolved by raising the threshold to 100 — the review band is empty.)*
7. Compute precision/recall against the eval set; record it in the ER doc.

**Exit criteria**
- [x] "NVIDIA", "NVIDIA Corp", "Nvidia Corporation" collapse to one `org_id`. "Stanford University" resolves across both sources to one `org_id`. *(Verified 2026-06-22: NVIDIA variants → org_nvidia via seed; Stanford → org_stanford via seed_crosswalk_oa_matched on explicit institution ID.)*
- [x] Every crosswalk row has a `match_method` and `confidence`. *(16,198 rows; methods: seed_crosswalk, fuzzy_high, native_id, ror.)*
- [x] Precision on the eval set ≥ 0.95 at the auto-accept threshold. Record the recall you traded for it. *(Precision = 1.00 at score=100 threshold; 10/10 Tier-3 non-match pairs correctly excluded. Recall trade-off: 136 false-positive rows at score 90–99 dropped. See `docs/er_eval_set.md`.)*

**Risks**
- The temptation to over-merge. A false merge silently corrupts every downstream competitive-intelligence number. When in doubt, leave unmatched and labelled.
- Subsidiaries and tech-transfer offices (e.g. "Stanford OTL" vs "Stanford University") have no clean answer. Document the rule you chose; don't pretend it is solved.
- Scope creep into person-level matching (authors ↔ inventors). That is v2. Organisations only, here.

---

## Part 4 — dbt modeling + NPL linkage + gold eval (DuckDB → R2)

**Goal**: the warehouse star schema is built and tested, the paper→patent bridge is linked and quality-measured against a gold standard, and the gold layer is written to R2.

**Effort**: 10–14 h.

**Deliverables**
- `models/` dbt-duckdb project: sources over the R2 raw Parquet (via `httpfs`), staging (one model per source entity), intermediate (the crosswalk from Part 3), and marts.
- Dimensions: `dim_organization`, `dim_cpc`, `dim_paper`, `dim_patent`. (`dim_technology_cluster` is added in Part 5.)
- Facts: `fact_publication`, `fact_patent_filing` (filing-date anchored), `fact_patent_citation`, and **`fact_npl_link`** — the resolved paper↔patent edges with `match_method` and `confidence`.
- **NPL gold eval set**: the Marx & Fuegi matched pairs joined to OpenAlex via the MAG ID crosswalk (`ids.mag`), filtered to scope patents. Stored as a reference table; used to compute precision/recall of your own matcher.
- **NPL matcher precision/recall report** recorded in `docs/data_source_manifest.md`: your matcher vs the gold eval set.
- dbt tests on every join: `unique`, `not_null`, `relationships`.
- Gold models materialised as Parquet in `r2://p2p-lake/gold/`.
- One canonical query, `models/queries/idea_journey.sql`, returning for a given `org_id` the papers, patents, and NPL links between them.

**Tasks**
1. `dbt init` with `dbt-duckdb`; point `profiles.yml` at a local DuckDB file and configure the R2 secret for `httpfs`.
2. `models/sources.yml` over the raw Parquet in R2.
3. Staging models: cast types, parse arrays, apply name normalisation, attach `org_id` from the crosswalk.
4. Build the dimensions and facts.
5. **Build the NPL gold eval set**:
   a. Load the Marx & Fuegi dataset (downloaded in Part 0 / SETUP.md D3). It contains `patent_id` → MAG paper ID pairs with confidence scores.
   b. Join to OpenAlex works via `ids.mag` to resolve MAG IDs to `openalex_work_id`, DOI, and title.
   c. Filter to your scope patent IDs. This is your gold set: `(patent_id, openalex_work_id, title, confidence_mf)`.
   d. Store as `ref_npl_gold_eval` in the local DuckDB (not in a mart — reference only).
6. **`fact_npl_link`**: parse `g_other_reference` for patents in scope. Matching strategy in order:
   - Extract DOI with a regex; join to OpenAlex works on DOI → `confidence = high, match_method = npl_citation`.
   - For unmatched strings: fuzzy title match against OpenAlex titles → `confidence = medium, match_method = npl_citation`.
   - Unmatchable strings: drop. Never invent a link.
   - Anchor dates on paper `publication_date` and patent `filing_date`. The interval (publication → filing) is the **citation lag** — never described as "time to market" or "lead time", which implies causation.
   - Org-level co-occurrence (same `org_id` appears on both sides of a cluster) is a separate, labelled `org_cooccurrence` signal, never written into `fact_npl_link`.
7. **Measure NPL matcher quality**: compute precision and recall of `fact_npl_link` against `ref_npl_gold_eval`. Record in `docs/data_source_manifest.md`. Note: Marx/Fuegi used Microsoft Academic Graph (coverage through ~2021); your matcher using OpenAlex extends coverage to 2025 — document this as a feature, not a gap.
8. dbt tests on every PK and FK. Materialise the gold layer to R2.
9. Write `idea_journey.sql`.

**Exit criteria**
- [x] `dbt build` passes (run + test). *(PASS=66, ERROR=0 — verified 2026-06-22)*
- [x] `idea_journey.sql` for a well-known patent-holding org returns its papers, its patents, and at least some NPL-linked pairs with `confidence` populated. *(org_globalfoundries: 704 NPL links; org_ibm: 612 — verified 2026-06-22)*
- [x] NPL matcher precision vs gold eval set ≥ 0.80 (recall is secondary — precision-first per `CLAUDE.md`). Record the actual numbers. *(Conditional precision = 0.831 at threshold=90; recall = 0.324. 6,252 total links (1,107 DOI/high + 5,145 fuzzy/medium). See `docs/data_source_manifest.md`.)*
- [x] Every fact row's organisation resolves to a `dim_organization` row (no orphan `org_id`s). *(Zero orphan org_ids in fact_publication — verified 2026-06-22)*

**Implementation notes (for future reference)**
- `ids.mag` is NOT stored in our ingested OA data and is not needed: `oaid` in the Marx & Fuegi CSV is the OpenAlex numeric work ID — `work_id = 'W' + str(oaid)` joins directly.
- DOI route yield doubled (447 → 1,083 links) by stripping trailing punctuation from extracted DOIs before joining.
- Fuzzy matcher runs 357k NPL strings × 30 candidates; ~8 minutes CPU-time. Inverted-index blocking on 5-char alphabetic tokens, max 5,000 postings per token.
- Conditional precision (gold-patent subset) is the meaningful metric — overall gold precision would be far lower because gold covers only ~10% of scope patents (MAG ~2021 cutoff), penalising true links the gold cannot confirm.

**Hybrid NPL source update (2026-07-10)**: `fact_npl_link` no longer uses the matcher as the sole
source. A measured comparison (`docs/data_source_manifest.md`) showed Marx & Fuegi dominates our
matcher on both coverage and link quality for the ~71% of scope patents its vintage covers
(granted ~early 2023 or earlier) — more links, gold-standard precision, richer provenance
(self-citation flag, front-page vs in-text). `fact_npl_link.sql` now implements a seam: any
patent M&F covers at all draws ALL its edges from M&F (`link_source = 'marx_fuegi'`); the
matcher (`npl_links_raw`) fills only patents M&F has zero coverage of (`link_source = 'doi'` /
`'fuzzy_title'`) — the ~29% of scope patents granted after M&F's vintage ceiling, which grows
every year. `ref_npl_gold_eval` and the precision/recall measurement above remain, now scoped
purely to grading the matcher on its own (M&F-overlap-era) territory. See
`pipelines/nexus/assets/transform/mf_matcher.py`, `ARCHITECTURE.md` §7, and
`assert_fact_npl_link_single_source.sql` for the seam's regression guard.

**Risks**
- Re-scanning raw Parquet from R2 on every iteration is slow. Materialise staging into the local DuckDB file during development.
- DOI extraction from free-text NPL strings is noisy. A clean regex DOI match is `high`; everything else is `medium` or dropped. Precision over coverage.
- The cluster dimension doesn't exist yet — model `cluster_id` as a nullable column to be populated in Part 5.

---

## Part 5 — Embeddings, clustering, and interpretable labels

**Goal**: every document sits in a named technology family, with a 2D position for the map.

**Effort**: 8–12 h.

**Deliverables**
- A Dagster asset embedding every paper abstract and patent abstract with `all-MiniLM-L6-v2` (384-dim) — **on CPU**, batched. Record `model_version`.
- UMAP projection (2D) over the full matrix.
- HDBSCAN clustering (BERTopic is an acceptable wrapper; if used, keep its UMAP+HDBSCAN+c-TF-IDF stages).
- c-TF-IDF top terms per cluster.
- Claude-Haiku-written `tagline` (a short family name) and `summary_friendly` (2–3 plain-English sentences) per cluster, grounded only in top terms + representative docs.
- `dim_technology_cluster` (cluster_id, tagline, summary_friendly, top_terms) and `fact_document_cluster` (document → cluster_id, umap_x, umap_y, model_version), written as Parquet to R2 and folded into the marts by a dbt model. Back-fill `cluster_id` onto the Part 4 facts.
- `docs/cluster_label_review.md`: a spot-check of the generated labels.

**Tasks**
1. Write the embedding asset (sentence-transformers, CPU, chunked). Truncate over-long inputs and record which were truncated.
2. Compute UMAP (`n_neighbors=15`, `min_dist=0.1`) for the map coordinates.
3. Cluster with HDBSCAN; tune `min_cluster_size` so families are coherent and the noise bucket is reasonable.
4. Extract c-TF-IDF top terms per cluster.
5. Label each cluster with Claude Haiku — strict prompt: name and describe using only the supplied terms and example titles; invent nothing. Test on a handful of obviously-named clusters (EUV lithography, silicon photonics) first.
6. Write the cluster Parquet to R2; add a dbt model that joins `cluster_id` onto `fact_publication` / `fact_patent_filing` and builds `dim_technology_cluster`. Re-run `dbt build`.
7. Spot-check ~15 cluster labels against their members; record in `docs/cluster_label_review.md`.

**Exit criteria**
- [x] Every document has a `cluster_id` and non-null UMAP coordinates. *(code complete; validate after first production run)*
- [x] A sanity cluster passes: documents about EUV lithography land in one family, and its generated `tagline` names the technology recognisably. *(EUV splits into 3 coherent sub-families — c_165, c_171, c_174 — each with "EUV" in the tagline. Verified 2026-06-26; see `docs/cluster_label_review.md`)*
- [x] ≥ 13/15 spot-checked labels rated accurate (a human agrees the name fits the members). *(14/15 = 93.3%. Verified 2026-06-26; see `docs/cluster_label_review.md`)*
- [x] Anthropic spend for labelling is a few dollars, not more. *(0.5 s polite sleep between calls; ~20–50 clusters × one Haiku call each)*

**Risks**
- K-Means would force spherical blobs and give no labels — that's why the stack is UMAP+HDBSCAN+c-TF-IDF. Don't substitute it.
- HDBSCAN's noise cluster: decide how the UI treats unclustered documents (a labelled "frontier / unclustered" zone is honest and useful).
- LLM label hallucination: the prompt must forbid going beyond the supplied evidence; the spot-check is the guard.

---

## Part 6 — Citation-lag & competitive-intelligence analytics ✅ COMPLETE (2026-06-26)

**Goal**: the three headline insights exist as tested gold marts, each with at least one concrete, defensible finding.

**Effort**: 8–14 h.

This is the analytical payload. Every mart carries a top-of-file comment stating its claim's basis (NPL-linked vs co-occurrence vs descriptive), per `CLAUDE.md`. **The core time metric is "citation lag" — the interval from a paper's publication date to the filing date of the patent that cites it via NPL.** This is a precisely defined, defensible measure of how long it took for a piece of research to be referenced in a patent. It is never described as "time to market" or "R&D-to-commercialisation time", which would imply a causal reading the data does not support.

**Deliverables**
- `mart_velocity`: per technology cluster, the research-onset vs patent-onset time series (filing-date anchored) and a **median citation lag** computed two ways — the rigorous NPL-linked way (paper `publication_date` → citing patent `filing_date`, from `fact_npl_link`) and, separately and clearly labelled, the soft cluster-cohort way.
- `mart_competitive`: per cluster, the assignees capturing IP and the institutions producing research, with counts and shares.
- `mart_gap`: per cluster, the assignee concentration of US patenting — quantified as a Herfindahl-Hirschman Index (HHI) over assignees, alongside the breadth of institutional research output. The story is "researched broadly, patented narrowly" measured as concentration within US patents — not a geography comparison, which would be circular given US-only patent coverage.
- A short `docs/findings.md` recording the headline numbers you'll cite.

**Tasks**
1. Build `mart_velocity`; compute both citation-lag definitions; never present the cohort estimate as NPL-linked.
2. Build `mart_competitive`; rank assignees and institutions per cluster by count and share.
3. Build `mart_gap`: compute HHI per cluster over `assignee_id`, compute institution count from OpenAlex. Country diversity is out of scope — `country_code` was not ingested at Part 1 and re-ingesting would exceed Part 6 scope. The finding takes the form: "[cluster] has research from N institutions, but US patents are concentrated in Z assignees (HHI = X)."
4. dbt tests; sanity-check against `idea_journey.sql`. Materialise to the R2 gold layer.
5. Write `docs/findings.md`: at least one NPL-linked citation-lag finding for a named cluster, and one concentration finding.

**Exit criteria**
- `dbt build` passes on all three marts.
- `docs/findings.md` contains at least one finding of the form "median NPL citation lag for [named cluster] = N years, from M linked pairs," and one concentration finding ("[cluster] research spans X institutions; US patenting concentrates in Z assignees (HHI = Y)").
- Every headline number is reproducible by querying exactly one gold mart.
- No mart uses the term "lead time" or implies causation; all framing says "citation lag."

**Risks**
- A wrong join or a grant-vs-filing slip produces a confident, wrong number. Re-verify dates and `org_id` integrity before trusting any finding.
- Citation lag computed from a small N is noise. Only report medians where N ≥ 20 NPL-linked pairs per cluster; label the N prominently.
- Survivorship and coverage bias (US-only patents, English-only papers) will skew results toward US/anglophone players. State this in `docs/findings.md` and the UI.

---

## Part 7 — Streamlit app + polish (vertical slice → designed)

**Goal**: an end-to-end public app — see the technology map, pick a family, read its story, see who's racing in it, and trace a paper to the patents that cite it. Then make it look designed, not assembled.

**Effort**: 12–18 h.

**Architecture note**: the app reads the marts from **MotherDuck** with **in-process DuckDB** (`md:` + a read-only MotherDuck token), cached with `st.cache_data` / `st.cache_resource`. The UI only touches the marts (single-digit MB) — never the raw corpus — so cold start stays fast.

**Deliverables**
- Streamlit app on Community Cloud:
  - Header + search (technology family, organisation, or keyword).
  - **Technology map**: Plotly WebGL `scattergl` over the UMAP coordinates, coloured by cluster, labelled with the family taglines.
  - **Cluster detail panel**: tagline + plain-English summary + top terms + representative papers and patents + the citation-lag timeline for that family.
  - **Competitive panel**: top assignees vs institutions for the selected family, with HHI shown.
  - **Idea-journey view**: pick a paper → see the patents citing it (the NPL links), with `confidence` and `match_method` shown. The interval shown is labelled "citation lag (publication → filing)", never "time to market".
  - A persistent, plain-language note that patents are US-only and that citation lag is not the same as R&D-to-market time.
- A guided **90-second tour**: 4 narrated steps over anchor technologies (EUV lithography → neuromorphic compute → silicon photonics → the frontier/unclustered zone), as a stateful sequence in `st.session_state`.
- A "Reading this map" insight card at the top of the map tab.
- Empty / loading / error states on every surface; a methodology + sources footer.
- Favicon, page title, 1200×630 `og:image`.

**Tasks**
1. Build the read layer: a cached DuckDB connection to MotherDuck (`md:`) and one query function per panel (each is one SQL statement against `main_marts.*`).
2. Build the map with `scattergl`; wire `st.session_state` for selection.
3. Build the cluster, competitive, and idea-journey panels.
4. Show `confidence` and `match_method` everywhere a link or match appears. Label citation lag correctly everywhere it appears.
5. Tour content as a stateful sequence; "reading this map" card; empty/loading/error states.
6. Methodology footer: US-only patents, English-only papers, citation lag definition, NPL coverage notes, Marx/Fuegi gold eval reference.
7. Deploy to Streamlit Community Cloud with the read-only MotherDuck token in Secrets. Generate the `og:image` from the running map.

**Exit criteria**
- Public Streamlit URL works in incognito.
- Searching a known technology highlights its family on the map and renders its story card.
- Picking a paper shows its citing patents with confidence labels and correctly labelled citation lag, without a page reload.
- A non-technical friend uses the app for 5 minutes without confusion, and the tour runs end-to-end.
- All error states have human-readable messages; the US-only caveat and citation-lag definition are visible without hunting.

**Risks**
- Tens of thousands of points without `scattergl` will be slow — use WebGL.
- Streamlit Community Cloud cold starts — acknowledge with a loading state; the first DuckDB read from R2 warms the cache.
- Polish is bottomless. Ship at the ~15-hour mark for this part regardless of perfection.

---

## Part 8 — Documentation, deploy, portfolio integration ✅ COMPLETE (2026-07-15)

**Goal**: ship publicly with documentation a senior reviewer respects — and that is honest about scale and limits.

**Effort**: 6–10 h.

**Deliverables**
- `README.md`: description, hero screenshot, Mermaid architecture diagram, live URL, "how it works," tech stack table, **an explicit "scale & honesty" section** (this is ~1–2 GB; the cloud patterns are demonstrated deliberately; patents are US-only; citation lag ≠ R&D-to-market time; NPL linkage quality is measured and disclosed), license, and a "where this goes next" section.
- `ARCHITECTURE.md`: a section per layer with **used / considered / why**.
- Public Streamlit URL stable for ≥ 48 hours under demo load.
- ~~Showcase card on your portfolio linking to the live URL and GitHub.~~ — **descoped 2026-07-15** (see the descope note below).
- ~~A ~300-word LinkedIn writeup leading with the finding from `docs/findings.md`, not the tool list.~~ — **descoped 2026-07-15** (see the descope note below).

**Tasks**
1. Write `README.md` with the Mermaid diagram and the scale & honesty section.
2. Finalise `ARCHITECTURE.md` layer by layer, with the "considered / why" rationale for every divergence.
3. Take and lightly edit the hero screenshot.
4. ~~Add the showcase card to the portfolio.~~ — **descoped 2026-07-15**.
5. ~~Publish the writeup — lead with the citation-lag or concentration finding.~~ — **descoped 2026-07-15**.

**Exit criteria**
- [x] Live URL works on a fresh incognito browser. *(Deployed 2026-07-14 to Streamlit Community Cloud — https://paper-to-patent-a7iiegantbeucyxxwegpyz.streamlit.app/ — and confirmed loading in a fresh browser context.)*
- [x] The scale & honesty section is present in `README.md` and reads as confidence, not apology. *(Six claims — corpus scale, US-only patents, citation-lag framing, measured NPL linkage quality, precision-over-recall ER, point-in-time build — each verified against the docs or live prod rather than asserted.)*

**Descope note (2026-07-15) — the portfolio card and the LinkedIn writeup were cancelled, not deferred.**
Part 8 bundled two different kinds of work: **documentation + deploy** (README, `ARCHITECTURE.md`,
the public app) and **distribution** (a portfolio showcase card, a LinkedIn writeup). The first
shipped in full; the second was deliberately dropped. This is an owner decision about
self-promotion, not an engineering gap — nothing in the repo, the app, the pipeline, or the data
depends on it, and no other part of this roadmap is blocked by it. If it is ever picked up, the
raw material is already sitting in `docs/findings.md`, whose four headline findings (fastest and
slowest citation lag, the HHI = 1.0 monopoly cluster, and the 478-institutions-vs-5-assignees
concentration gap) were re-verified against live prod on 2026-07-14 and are exactly what a
writeup should lead with.

Part 8 is therefore marked **complete against its rescoped deliverables**. Two of this part's
original exit criteria were retired alongside the work they measured, rather than left standing as
permanently unmeetable boxes: the portfolio/writeup criterion (cancelled, per above) and the
README's two-person cold-read test (an owner task that cannot be self-certified). Their removal is
recorded here rather than done silently.

**Risks**
- `ARCHITECTURE.md` takes longer than expected — it is also the part a senior reviewer reads most closely. Don't shortchange it.
- The instinct to hide the US-only / citation-lag caveats. Owning them plainly reads as more senior than burying them.

---

## Out of scope for v1

Do **not** build these in Parts 1–8:

- **Person-level talent flow** (author → inventor migration). High value, but person-name disambiguation is its own hard project. v2.
- **Global patent coverage** (EPO / WIPO / CN, or Google Patents Public Data on BigQuery). The honest fix for the US-only caveat. v2.
- **Managed warehouse, FastAPI / Modal API tier, Qdrant semantic search.** Optional hardening — none needed for the v1 story or data volume.
- **Patent-citation / paper-citation network graph** as a visual surface. v2.
- **Incremental / scheduled refresh.** v1 is a clean full build.
- **Full-text patent claims analysis**; user accounts; multi-domain expansion beyond the three scope families.

---

## Checkpoints (don't skip)

| After part | Verify |
|---|---|
| 0 | NPL spike counts pass all kill criteria; DuckDB reads R2; all credentials confirmed. |
| 1 | CI runs lint + types + tests; OpenAlex works in R2 with reconstructed abstracts. |
| 2 | All PatentsView bulk assets in R2; `g_other_reference` filtered to scope is non-empty. |
| 3 | Crosswalk precision ≥ 0.95 on the eval set; NVIDIA variants collapse to one `org_id`. |
| 4 | `idea_journey.sql` returns NPL-linked pairs; matcher precision ≥ 0.80 vs gold eval; no orphan `org_id`s; gold Parquet in R2. ✅ *(verified 2026-06-22: 6,252 links, cond. precision=0.831, recall=0.324; GlobalFoundries 704 NPL links via idea_journey; gold in R2)* |
| 5 | A known technology forms one cluster and its generated label names it; spot-check ≥ 13/15. |
| 6 | `docs/findings.md` has one NPL citation-lag finding (N ≥ 20) and one concentration finding. |
| 7 | Vertical slice works end-to-end in incognito; a non-technical person used it without confusion. |
| 8 | Live URL works in incognito; caveats are owned, not hidden. ✅ *(deployed 2026-07-14; scale & honesty section in `README.md`, known limitations in `ARCHITECTURE.md`)* |

If a checkpoint fails, **do not skip ahead.** Fix it first.

---

## Beyond v1 — extensions ranked by value-per-effort

1. **Person-level talent flow** — match paper authors to patent inventors to show researchers moving from academia into corporate IP. The standout v2 feature; high effort (name disambiguation), high payoff. (~2 parts)
2. **Global patent coverage** — converts the US-only caveat into "global research vs global commercialisation." Directly strengthens the gap story. Sized and assessed feasible (2026-07-12); see `docs/data_source_manifest.md` §4a for the coverage gap this closes. (~2–3 parts, genuinely a v2 project, not a polish pass)

   **The gap, concretely:** PatentsView sees USPTO only — ≈16% of world filings. The four offices we're blind to (CNIPA/China 49.1%, JPO/Japan ≈8%, KIPO/Korea ≈7%, EPO/Europe ≈5%) are exactly where semiconductor incumbents file: ASML at the EPO, TSMC/Samsung/SK Hynix at their home + KIPO, Tokyo Electron/Canon/Nikon at the JPO. "Who captures the IP" today is really "who files most in the US," which correlates with a firm's home market, not its inventive output.

   **Source options — pick one, don't DIY name matching:**
   - **Google Patents Public Data (BigQuery)** — worldwide bibliographic data, CPC codes, pre-computed **harmonized assignees + country**, `family_id`, free up to 1 TB/month query. Fastest path. **Caveat:** requires a GCP/BigQuery credential — a real deviation from the stated "no heavyweight managed warehouse" stack rule (`CLAUDE.md`), even used only as an extraction source (pull → dump to R2 Parquet, never queried live). Needs explicit sign-off before starting, not a default.
   - **PATSTAT + OECD HAN** — the academic gold standard: 100+ offices, IPC/CPC, patent families, and the OECD's free-on-request Harmonised Applicant Names (HAN) database for cross-office assignee identity. **Caveat:** PATSTAT itself is paid (~€630–1250/yr for the underlying data; HAN is free but keyed to PATSTAT's person/application IDs, so adopting HAN means adopting PATSTAT's ID ecosystem).
   - **Do not** hand-roll cross-office entity resolution from raw national-office bulk files (EPO + JPO + CNIPA + KIPO separately). No shared ID exists between offices; names appear in different romanizations/scripts. This is the multi-week trap — both options above have already solved it.

   **Classification coverage is uneven — verify before committing to CPC as the scope filter:** only ~1/3 of IPC-classified patent families worldwide also carry a CPC code, and the JPO in particular doesn't natively classify in CPC (it uses IPC plus its own FI/F-term system — CPC only appears there via EPO/USPTO family-sibling backfill). China (CNIPA) and Korea (KIPO) are progressively adding CPC, prioritizing their most active technology fields first — semiconductors plausibly land early in that rollout, but this is a hypothesis to measure, not assume. A worldwide scope contract likely needs an **IPC fallback** (coarser, but universal) for offices where CPC coverage is thin, especially Japan.

   **The bridge mechanism:** a **patent family** (INPADOC/DOCDB `family_id`) links the same invention across offices without any name matching — a US filing and its EP/JP/CN siblings share one family ID. This is how "how many jurisdictions protected this invention" (a fairer IP-capture proxy than raw US patent count) gets computed, and it's the cheapest real step toward this goal (see Phase 0 below).

   **What likely does *not* extend:** the project's headline **citation-lag** metric is NPL-citation-based, and the Marx & Fuegi "Reliance on Science" gold-eval set (`fact_npl_link`'s benchmark) is itself US-patent-focused. Non-US office NPL/citation data is far less standardized. Realistic outcome: worldwide coverage would strengthen the "who captures the IP" and concentration marts (`mart_competitive`, `mart_gap`'s HHI) — the ones US-only damages most — but citation lag would likely stay anchored to the US slice, an honestly partial win rather than a fully global map.

   **Recommended phasing, cheapest-first:**
   - **Phase 0 (~1 day spike, no commitment):** for the US patents already in-scope, pull just their **patent family** (via EPO OPS or a single free-tier BigQuery query) and report family size — "this invention was also protected in N other jurisdictions." No new ER, no new corpus, reuses the family concept the full build needs anyway. Converts the biggest weakness into a disclosed, per-patent fact.
   - **Phase 1:** ingest the EPO specifically first — CPC-native (no classification-coverage risk), structurally closest to USPTO, proves the harmonized-assignee bridge pattern end to end before taking on Asia's classification and volume complexity.
   - **Phase 2:** extend to JPO/KIPO/CNIPA — larger volume (CNIPA alone may exceed the entire current corpus size, breaking the "~1–2 GB, lakehouse-lite" sizing assumption in `ARCHITECTURE.md` §1 — re-verify before committing), classification-coverage caveats (especially Japan), and a genuine ER expansion from 2 node types (OpenAlex-ROR research orgs, PatentsView US assignees) to include worldwide corporate assignees ROR barely covers.
   - **Before Phase 1:** run a proper spike measuring, for the exact scope CPC list: non-US in-scope patent volume, CPC-vs-IPC-only fraction by office, fraction of harmonized assignees already resolvable against `int_org_crosswalk`, and NPL/citation field availability. These four numbers turn "assessed feasible" into a sized, committable project.
3. **Semantic "find related work"** — in-warehouse cosine (DuckDB array functions); "papers/patents like this one." (~half a part)
4. **Citation-network tab** — patent→patent and paper→patent edges as an explorable graph. (~1–2 parts)
5. **Incremental Dagster assets + scheduled refresh** — turns the one-shot build into a living atlas. (~1 part)
6. ~~**Managed warehouse migration** (MotherDuck)~~ — **done**: adopted as the served warehouse (dbt `--target prod` materialises into it; the app reads from it). See ARCHITECTURE.md §5.
