# MEMORY.md — Lessons Learned

Running log of non-obvious findings, operational gotchas, and decisions that are not captured in ROADMAP.md or CLAUDE.md. Update this file at the end of every part.

---

## Part 0 — Pre-flight + NPL feasibility spike

**Spike counts (CPC-only, no filing-date filter applied yet — Part 2 date-filtered corpus will be smaller):**
- 68,800 scope patents
- 656,347 NPL references
- 291,378 Marx/Fuegi gold pairs (all 3 families well above the 50-pair kill criterion)
- ~151,000 OpenAlex works (2012–2024 at spike time; scope extended to 2025 before Part 1 re-ingest)

**Terraform Cloudflare provider v5 import format:** three segments required — `account_id/bucket_name/` (empty third segment = default jurisdiction). The two-segment form fails with "expected 3 URL segments".

**Marx & Fuegi dataset note:** `oaid` in `_pcs_oa.csv` is already an OpenAlex work ID — no MAG bridge required. Patent coverage runs through ~2023; our own matcher adds 2024–2025 via OpenAlex.

---

## Part 2 — PatentsView ingest

**PatentsView bulk files must be downloaded manually — always:**
- `data.patentsview.org` does not resolve via DNS (decommissioned). The new home is `data.uspto.gov`, but that site is also a JavaScript SPA — programmatic download via httpx fails silently (returns the HTML shell, not the file).
- Rule: all PatentsView bulk TSVs must be placed in `data/raw/` by hand from a browser: `data.uspto.gov` → Datasets → PatentsView → Grant Data.
- The `load_bulk_tsv()` helper already checks local files first and only attempts a network download as a fallback — so once files are in `data/raw/`, assets work without any URL. The URL in `_URLS` is documentation only.
- This was already documented in SETUP.md D1 from Part 0. Do not attempt programmatic bulk download in future parts.

**`patent_id` must always be read as String in PatentsView TSVs:**
- Design patents (`D1035263`), reissues (`RE12345`), and plant patents (`PP12345`) have non-numeric IDs. Polars infers `i64` from the first 10,000 rows (all numeric) and fails later.
- Fix: `schema_overrides={"patent_id": pl.String}` in every `scan_csv` call. Applied to all 7 ingest assets. `citation_patent_id`, `assignee_id`, `inventor_id` also forced to String.

**Part 2 materialized row counts (2026-06-21):**
- `patentsview_patents_raw`: 9,454,161 rows
- `patentsview_applications_raw`: 9,451,902 rows
- `patentsview_assignees_raw`: 8,751,310 rows
- `patentsview_cpc_raw`: 59,805,669 rows
- `patentsview_npl_raw`: 65,161,274 rows
- `patents_scoped`: **33,578 patents** (CPC match + filing_date 2014–2025; smaller than Part 0 spike of 68,800 because the spike had no date filter — expected)

---

## Part 1 — Foundation + OpenAlex ingest

**OpenAlex rate limit — the hard operational constraint:**
- Undocumented daily volume cap per IP, observed at ~300–400k records (~1,500–2,000 page requests of 200 records each).
- Violations trigger **escalating** Retry-After cooldowns: first offence ~6h, second ~13h the same day.
- Rule: one full corpus pull per day maximum. Never re-ingest the same day unless you have no choice.
- Always run the 2-call smoke test (one count check, one sample record) before a full pagination run. Costs nothing against the cap.

**Atomic R2 write pattern (stage-then-promote):**
- Never pre-delete an existing good R2 snapshot before starting a new write. We did this once and the new run hit the rate limit mid-pagination — leaving R2 empty.
- Pattern: write to `works.parquet.staging` → verify → DuckDB COPY staging → `works.parquet` → delete staging via Cloudflare API. The dangerous window (no good data) is now the final COPY (seconds), not the full pagination (15+ min).
- Helper: `delete_r2_object()` in `pipelines/nexus/assets/ingest/openalex.py`.

**Python 3.13 + Dagster incompatibility:**
- `from __future__ import annotations` (PEP 563) makes annotations lazy strings. Dagster's runtime `get_type_hints()` cannot resolve them → `DagsterInvalidDefinitionError` on context parameter.
- Fix: never add `from __future__ import annotations` to Dagster asset files. CI runs Python 3.12 for this reason.

**polars → R2 without pyarrow:**
- pyarrow is not in the stack. `con.register("df", df)` in DuckDB calls `polars.to_arrow()` internally — fails.
- Pattern: `df.write_parquet(local_tmp_file)` (polars native Rust writer) → `DuckDB COPY (SELECT * FROM read_parquet(local_tmp)) TO 'r2://...'`.

**Final state at Part 1 close:**
- 19 tests passing, CI green (ruff + pyright strict + pytest + dagster definitions validate).
- R2: 164,072 rows at `r2://p2p-lake/raw/openalex/v2026-06-22/works.parquet` (2012–2025). +13,084 vs the 2024-cutoff run.
- PR open: `feat/part-1-foundation-openalex` → `main`.
- **`parse_work()` now captures `institution_display_names: list[str]`** — added before this re-ingest so the field is present in the Parquet and `openalex_institutions_staging` (Part 3) can be implemented without another re-ingest.
- **Always run with `--env-file .env.local`**: `uv run --env-file .env.local dagster asset materialize ...` — without it Dagster fails immediately because Cloudflare env vars are not set in the shell.

---

## Part 3 — Entity resolution (in progress, 2026-06-21)

**OpenAlex schema gap — prerequisite before OpenAlex half of Layer 1:**
- `parse_work()` in `openalex.py` does NOT capture `institution_display_names`. The field exists in the API response (`authorships[].institutions[].display_name`) but was not included in the original Parquet schema.
- The `openalex_institutions_staging` asset (Layer 1 OpenAlex side) cannot be implemented without it. Before the next OpenAlex re-ingest, add `institution_display_names: list[str]` to `parse_work()`, update its tests, then re-ingest.
- The `openalex_institutions_staging` Dagster asset is registered as a stub — it raises `RuntimeError` if the works Parquet is absent and `NotImplementedError` once data exists but the body is not yet implemented.

**Seed crosswalk design: name-based join, not UUID hardcoding:**
- Decision: `seed_crosswalk.csv` stores the *normalised form* of each PatentsView org name (`normalized_patentsview`), not the raw `assignee_id` UUID.
- Why: PatentsView assignee UUIDs are opaque and could drift across bulk snapshots. The normalised name is stable across versions and human-verifiable.
- The `seed_crosswalk_matched` asset joins `patentsview_orgs_staging.normalized_name` to `seed_crosswalk.normalized_patentsview`. Multiple CSV rows per `org_id` handle legal-entity variants (e.g., org_asml has two rows for "asml" and "asml netherlands").
- Downside: if `normalize_org_name()` logic changes, the CSV entries must be re-verified. The production CSV sanity tests (`test_production_seed_csv_*`) guard against blank entries and non-lowercase values.

**PatentsView dominant assignees in scope (2026-06-21, scoped corpus 33,578 patents):**
Top 15 by scoped patent count:
1. Taiwan Semiconductor Manufacturing Company, Ltd. — 1,863
2. ASML NETHERLANDS B.V. — 1,763
3. International Business Machines Corporation — 1,494
4. SAMSUNG DISPLAY CO., LTD. — 1,334 *(display division, not Samsung Electronics)*
5. Micron Technology, Inc. — 1,308
6. Carl Zeiss SMT GmbH — 676
7. Intel Corporation — 671
8. SK hynix Inc. — 531
9. NIKON CORPORATION — 442
10. CANON KABUSHIKI KAISHA — 412
11. GOOGLE LLC — 411
12. Applied Materials, Inc. — 300
13. Shin-Etsu Chemical Co., Ltd. — 293
14. Microsoft Technology Licensing, LLC — 292
15. KLA-TENCOR CORPORATION — 285

Notable: Samsung Electronics Co., Ltd. does not appear as a top assignee in our CPC scope — Samsung Display (OLED/display patents) dominates instead. NVIDIA only has 86 scoped patents (rank ~56).

**PatentsView org names: Japanese "Kabushiki Kaisha X" is not strippable from the right:**
- `normalize_org_name` strips legal suffix tokens from the RIGHT of the token list.
- "CANON KABUSHIKI KAISHA" → tokens end with "kabushiki", "kaisha" → both stripped → "canon" ✓
- "Kabushiki Kaisha Toshiba" → last token is "toshiba" (not a suffix) → stripping never reaches "kabushiki"/"kaisha" → result is "kabushiki kaisha toshiba".
- Seed CSV entry for Toshiba uses the full form "kabushiki kaisha toshiba" as the match key. This is correct and expected.

**normalize_org_name — additions made in Part 3:**
- Added `S.r.l.` dotted expansion → `"srl"` (Italian limited liability; e.g. STMicroelectronics S.r.l.)
- Added `"srl"`, `"kabushiki"`, `"kaisha"` to `_LEGAL_SUFFIXES`
- These fix: "STMICROELECTRONICS S.r.l." → "stmicroelectronics", "CANON KABUSHIKI KAISHA" → "canon"

**polars `DataFrame.with_columns` / `filter` → pyright strict mode:**
- These polars methods have overloads that pyright `strict` mode cannot fully resolve → `reportUnknownMemberType`.
- Fix: add `# type: ignore[reportUnknownMemberType]` on the specific call lines. Do not disable globally.
- Affects any ER asset file that calls these methods on a collected `pl.DataFrame` (as opposed to `pl.LazyFrame` operations, which are fine).

**State after 2026-06-22 session — all core ER assets built:**
- `rapidfuzz==3.14.5` added to pyproject.toml (approved in CLAUDE.md tech stack).
- `build_openalex_institutions_staging()` implemented in crosswalk.py: DuckDB parallel UNNEST on institution_ids + institution_display_names, deduplicate by institution_id, normalize, tag ror/high. 9 new tests → total 154, all green.
- `fuzzy_org_bridge` asset (fuzzy_bridge.py): token_set_ratio blocking on first token; HIGH_THRESHOLD=90→fuzzy_high/high, REVIEW_THRESHOLD=75→fuzzy_review/medium. 12 tests.
- `org_crosswalk` asset (assemble.py): long-format `int_org_crosswalk` (source, source_id, org_id, canonical_name, match_method, confidence). Seed org_ids inherited by OA side via fuzzy bridge; fallback org_ids generated as `org_pv_*` / `org_oa_*`. 15 tests.
- `docs/er_eval_set.md` created: ~55 labelled pairs across Tier 1 (unambiguous), Tier 2 (near matches), Tier 3 (hard non-matches). Precision/recall record table pending first materialize run.

**One remaining manual step before Part 3 is complete:**
Fill `openalex_institution_id` in `seed_crosswalk.csv` for orgs where PV and OA names differ too much to fuzzy_high (Stanford, MIT abbreviation). Query after materializing `openalex_institutions_staging`:
```sql
SELECT institution_id, display_name, normalized_name
FROM read_parquet('r2://p2p-lake/intermediate/er/openalex_institutions_staging/*/*.parquet')
WHERE normalized_name IN ('stanford university', 'massachusetts institute of technology',
                          'california institute of technology', 'imec')
ORDER BY normalized_name;
```
Then fill those IDs into seed_crosswalk.csv and update `seed_crosswalk_matched` to also join on `openalex_institution_id` (when not blank) against the OA staging.

**Part 3 exit criteria status:**
- ✅ 'NVIDIA', 'NVIDIA Corp', 'Nvidia Corporation' collapse to one org_id via seed crosswalk.
- ✅ Every crosswalk row has match_method and confidence.
- ⏳ Precision on eval set ≥ 0.95 — pending first materialize + eval run.
- ⏳ Stanford resolves across both sources — needs openalex_institution_id filled in seed CSV.

---

## Part 7 — Streamlit UI (apps/ui)

### config.toml must live at apps/ui/.streamlit/config.toml

Streamlit resolves config relative to its **working directory**. The app is always launched from `apps/ui/`, so a config at the project root is silently ignored. Symptom: dark header bar, white-on-white sidebar text, invisible chart labels — on every cold restart.

**Rule:** Always run `uv run streamlit run app.py` from `apps/ui/`. Never from the project root. If the light theme breaks after a restart, check config.toml placement first.

Correct content of `apps/ui/.streamlit/config.toml`:
```toml
[theme]
base = "light"
primaryColor = "#111111"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f5f5f5"
textColor = "#111111"
font = "sans serif"
```

### Do not patch dark-mode bleed with .stApp CSS overrides

Adding `.stApp { background: #ffffff; }` in a `st.markdown` `<style>` block causes a large black decoration bar at the top unless you also suppress `[data-testid="stDecoration"]` and `[data-testid="stHeader"]`. This is treating a symptom; the real fix is always config.toml placement above.

### Container border overrides: use .st-key-{key}, not data-testid

`[data-testid="stVerticalBlockBorderWrapper"]` loses to Streamlit's emotion CSS. The reliable pattern is:
```python
with st.container(height=N, border=True, key="my_container"):
    ...
```
```css
.st-key-my_container {
    border: 1px solid #e6e6e6 !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}
```

### st.dataframe ProgressColumn cannot be styled per-row or per-family

`st.dataframe` in Streamlit 1.40+ uses glide-data-grid — a canvas renderer. The entire grid including `ProgressColumn` bars is painted on a `<canvas>` element; no CSS selector can reach individual cells. The bar color follows `primaryColor` from config.toml.

**Attempted and rejected approaches:**
- CSS injection targeting `[data-testid="stDataFrameProgressBarValue"]` — no effect (canvas).
- Replacing `st.dataframe` with a custom HTML `<table>` — user rejected twice ("completely broken"). Streamlit's global table CSS and uncontrolled column widths caused layout breakage.

**Agreed solution for HHI:** plain `NumberColumn(format="%.2f")`, no bar. Column tooltip via `help=` in column_config. Subtitle text instructs user to hover: *"Hover over 'Lag (yr)' and 'HHI' columns for definitions."* Do not put `?` in the column name — also rejected.

### Sidebar must be rendered after data loading when it depends on query results

If the sidebar contains a widget whose options come from a DB query (e.g. a cluster multiselect), the data must be loaded first. In Streamlit, `with st.sidebar:` blocks can appear anywhere in the script and will still render in the sidebar, so placing them after the data loading calls is safe.

### Family page design — agreed layout (2_Family.py)

1. Header card (family name + description, no border)
2. 4 metric cards: patent share, citation lag, # patents, # papers
3. Two scrollable leaderboard bar charts side-by-side (top 50 patenters / researchers), 10 bars visible, `st.container(height=..., border=True, key=...)`
4. Velocity chart: papers vs patents over time; trailing N years dotted/faded where N = `round(median_lag_years_weighted)` (dynamic provisional window)
5. Cluster breakdown table: `st.dataframe`, sorted by patents descending, `help=` tooltips on Lag and HHI columns, map link right-aligned above the table

### `.card` family is centralized in render.py, not app.py

`.card`, `.card-tag`, `.card-stat`, `.family-explore`, `.card--metric`, `.card--row`, `.card--identity` are defined once in `render.py`'s `render_nav()`, which every page (`app.py` + all 4 `pages/*.py`) already calls. They used to live only in `app.py`'s local `_CSS`, which meant they were invisible on the other 4 pages — Streamlit does not re-run `app.py` when navigating to a `pages/` script, so anything injected only there never reached the rest of the site. Page-specific modifiers (`.card--family`, used only by the Overview family rows) stay local to their page; only classes reused across 2+ pages belong in render.py. If a future card style is added to only one page, don't reflexively centralize it — centralize only once a second page needs the same shape.

**Card shape catalogue** (all compose with base `.card`, override what differs):
- `.card--metric` — 90px fixed-height stat box, used on all 4 non-Overview pages for the "N metric cards" rows. Text color goes through `.card-stat` (`var(--accent, #111111)`); Org page's metric cards don't set `--accent` at all and rely on the `#111111` fallback, since org totals aren't tied to one family.
- `.card--row` — 48px compact list row (Org page's cluster mini-list).
- `.card--identity` — softened family-colored border (`{color}55`), tighter radius/padding; the Trace-a-Paper paper-subject box design, the one the user pointed to as the reference for what a "family-colored but not heavy" border should look like.
- `.card--family` — Overview-only, fixed 144px row, documented separately below.

**Known remaining inconsistency, not fixed:** the `.card--metric` boxes' `margin-bottom` still varies by page (1_Map: 0, relies on an external spacer div; 2_Family/3_Org: `1rem`; 4_Trace: `1.5rem`). Preserved as-is rather than silently unified, since each page's total gap before the next section was tuned around that specific value and changing it would shift layout beyond what was asked. Revisit only if explicitly requested, the same way `.card--family`'s margin-bottom was only unified after an explicit ask.

### `.card--family` deliberately overrides `.card`'s padding, not just color

`.card--family` (Overview page family rows) composes with `.card` but overrides `padding` (16px vs `.card`'s `22px 26px`) and `height` (fixed 144px). This is a fit constraint, not a style preference: the card holds a stat grid with fixed row heights (`grid-template-rows: 48px 48px; gap: 8px` = 104px). At `.card`'s 22px padding, available inner height would be `144 − 2(border) − 44(padding) = 98px` — less than the 104px grid needs, causing overflow. At 16px padding it's `110px`, which fits. Do not "align" this padding to `.card`'s value without also revisiting the fixed 144px height and grid dimensions. `margin-bottom` has no such constraint and was unified to `.card`'s `1rem` (was `0.75rem`, a leftover from before the class refactor, not an intentional choice).

### CSS `!important` on stVerticalBlockBorderWrapper blocks dynamic border colors

`[data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid #e6e6e6 !important; }` (app.py) wins over any per-instance `border-color` (including `var(--accent)`) set on a card built with `st.container(border=True, key=...)` — `!important` overrides regardless of selector specificity, and the failure is silent (no error, border just stays grey). Raw-HTML cards (`_html_family_card()`, built as a `<div class="card card--family">` string via `st.markdown(..., unsafe_allow_html=True)`) are unaffected — this only bites a card that switches to a native `st.container` (e.g. to embed a real widget like a button inside it). If that happens, the container's `.st-key-{key}` selector must set the accent border with matching `!important`, not just a plain declaration.

### Velocity chart colors

`PAPER_COLOR` / `PATENT_COLOR` from render.py were rejected as inconsistent with the palette. Both lines use `family_color`: papers at 45% opacity (`_hex_rgba(family_color, 0.45)`), patents at full strength. The `_hex_rgba(hex, alpha)` helper converts hex to `rgba(r,g,b,alpha)` string.

---

## Part 5/6 — Family tagging: 3-way clusters, 5-way documents, and an embedding quality gate (2026-07-04)

**The core trade-off: family granularity is not the same at the cluster level and the document level, and conflating them was the original bug.**

- **Clusters are tagged with the original 3 Part 0 scope families** (`euv`, `silicon_photonics` — now includes lasers, `neuromorphic_in_memory` — merged), not the 5-way split (EUV / Silicon Photonics / Lasers / Neuromorphic / In-Memory) used earlier. Why: measuring each cluster's purity against its *own documents'* CPC/topic tags showed 53 of ~299 clusters were a genuine Lasers↔SiPhotonics mix and 13 were a genuine Neuromorphic↔InMemory mix (each side ≥15% share), while every other family pair showed 0–3 such clusters. Those two seams are exactly where the 5-way split cut through what Part 0 originally scoped as one family — on-chip lasers and photonic integration are routinely the same research; memristors are natively both a neuromorphic synapse and a resistive memory cell. No cluster-level partition (rules, hierarchy, or an LLM) fixes this, because the content genuinely isn't single-family. `seed_cluster_family` (`models/models/marts/seed_cluster_family.sql`) computes this via CPC-prefix / OpenAlex-topic majority vote, recomputed fresh every dbt run (not a hand-maintained CSV) — cluster IDs are not stable across re-clustering runs, confirmed live twice this session.
- **Patents and papers each carry their own direct 5-way `family_id`** (`fact_patent_filing.family_id`, `fact_publication.family_id`), computed straight from that document's own `primary_cpc` prefix or `primary_topic_id` — independent of whichever cluster it algorithmically landed in. This is the authoritative column for any counting (patent-share, HHI, leaderboards); `seed_cluster_family` is a **display label only** (map colour, cluster card), never joined into a count. Concretely, before this split existed, patents/papers sitting in a cluster whose *majority* was a different family were silently mis-attributed — verified: EUV patent counts were inflated ~27% (4,879 cluster-based vs 3,546 per-document) and Lasers paper counts were understated ~20% (9,387 vs 11,723) under the old cluster-only scheme.
- **T10502 ("Advanced Memory and Neural Computing") is unambiguous at the 3-way cluster level** (maps straight to `neuromorphic_in_memory`, no tie-break needed) but still ambiguous per-document at the 5-way level (could be neuromorphic *or* in-memory) — resolved there via a keyword regex on that *document's own* title+abstract (not the cluster's tagline, which would just inherit the cluster's bias). Use `regexp_matches()`, not `SIMILAR TO` — DuckDB's `SIMILAR TO` with `%` wildcards did not match substrings as expected even in the simplest case (`'the memristor device' similar to '%memristor%'` → `false`); `regexp_matches()` with the same pattern (no `%`) worked correctly. This bug silently broke the tie-break and was only caught by comparing a cluster's own top_terms against its computed family.

**Embedding-input quality gate** (`resolve_paper_text()` in `pipelines/nexus/assets/ml/embeddings.py`), added after the purity measurement surfaced three artifact clusters formed from non-content text: a cluster of papers whose abstract was literally "Abstract not provided.", a cluster of French/Italian/Catalan PhD thesis abstracts all tagged `language: en` by OpenAlex (the language field cannot be trusted — it's derived from something other than the abstract body), and a cluster mixing conference-abstract placeholders, journal editorials, and a mistagged bioinformatics-software changelog. Checked in order, first match wins: (1) version-style title (`libBigWig 0.1.5`) → exclude entirely, checked *before* the abstract because release-note prose can otherwise read as well-formed English and pass every other check; (2) placeholder or abstract <50 chars → fall back to title (not exclude — the paper is real, just missing a usable abstract; threshold was dropped from 100→50 after sampling the 50–99 char band and finding real "journal highlight sentence" content there that a title-only fallback would have under-used); (3) non-English abstract (via `langdetect`, `DetectorFactory.seed=0` for determinism) → fall back to title only if the title itself is English, else exclude; (4) otherwise use the abstract. Applied the version-title check to patents too. Result: noise rate dropped 42.6%→35.4% as a side effect (the junk text had been diffusing the whole embedding space, not just forming its own clusters), mean cluster purity rose 92.6%→94.2% (median 98.1%→98.9%), and all three source artifact clusters are confirmed gone with nothing similar taking their place.

**Operational gotcha — same-day re-run needs the stale snapshot deleted first:** `document_embeddings`/`document_clusters`/`cluster_labels` key their idempotency check on `v{today's date}`. If you already materialized once today and then change the embedding code (e.g. adding this gate), re-running with the same command silently no-ops ("Snapshot exists, skipping") on all three assets — it reuses the morning's pre-change output. Fix: delete the R2 objects for today's date first (`delete_r2_object()`, same helper used for stage-then-promote cleanup), verify via `glob()` that only older dated snapshots remain, then re-run.

---

## Issue 3 fix — junk non-article titles that survive the `type` filter (2026-07-04)

**The `type:article|preprint|review` ingest filter is necessary but not sufficient**, because OpenAlex mistypes some non-research records as `type: article`. Four such records were flagged in the original checkpoint review (Issue 3): `seL4: seL4 3.0.1`, `IDBac v0.0.15`, `Refractiveindex.info database of optical constants`, plus others found by scanning for the same shape. Checked all of them directly — `IDBac`/`seL4`/`libBigWig`/`InChI`/`mygit`/`meowallet`/`clipper` are all genuine software-release-note titles with tiny, non-research abstracts (many are literally just a GitHub URL or "See release notes at ..."); `Refractiveindex.info` has a real, well-written 856-character abstract and is a legitimately published dataset paper — it's a topic-relevance edge case (why the Silicon Photonics classifier picked it up), not junk text, so **no filter was written for it** — inventing one risks false-positiving real "database of X" papers.

**Fix:** `stg_openalex_works.sql` excludes titles matching `^Name[: Name] v?1.2(.3)? (parenthetical)?$` (release-note shape) — verified against the live corpus this matches exactly the 9 known-junk titles above and zero legitimate paper titles (including ones with a colon subtitle, e.g. "Neuromorphic Computing: A Review of..."). DuckDB's regex engine (RE2) doesn't support backreferences, so the SQL pattern doesn't require the name to literally repeat before/after the colon (broader than the Python version below) — verified this doesn't introduce false positives on the current corpus, but re-check if the corpus grows.

**Second-order fix — orphan-proofing `fact_document_cluster`:** removing docs at the staging layer would otherwise silently reintroduce the exact Issue-1 failure mode (orphan points on the map — `fact_document_cluster` is a raw passthrough of the R2 ML-asset output, un-joined to anything). Changed it to inner-join the doc against `stg_openalex_works`/`stg_patents_scoped` (not `dim_paper`/`dim_patent` — those two depend on `fact_document_cluster` for `cluster_id` backfill, so joining the other way would be circular). This makes the orphan-proofing permanent and structural: any future staging-layer filter change automatically drops from the map instead of needing a matching Part 5 re-cluster every time.

**Also broadened** `is_version_style_title()` in `embeddings.py` to catch the `"Name: Name version"` shape too (Python supports the backreference DuckDB's RE2 can't), so a future re-cluster doesn't waste embedding compute on this title shape either — currently redundant with the staging fix since `load_corpus()` reads from `dim_paper`/`dim_patent` (post-staging-filter), but is defense-in-depth if the staging filter and the ML corpus source ever diverge.

**Net effect:** corpus 186,933 → 186,930 docs (153,355 → 153,352 papers; patents unchanged), 237 clusters unchanged, 0 orphans (was already 0, now structurally guaranteed rather than just currently true).

---

## `excluded_documents` R2 artifact + NULL-abstract bug (2026-07-05)

**A document excluded entirely by the embedding gate is invisible on the map but was still counted everywhere else — a third, undocumented state distinct from `c_noise`.** Verified live: `c_noise` docs *were* embedded (HDBSCAN just didn't group them — they have UMAP coordinates, show on the map). But 128 papers had `dim_paper.cluster_id IS NULL` — never embedded at all, no `fact_document_cluster` row, not even `c_noise` — yet 117/128 still appeared in `fact_publication` with a resolvable `family_id`, counting toward `mart_family` totals while being nonexistent on the one page whose job is to show where documents sit.

**Root-caused the 128, don't assume they're all the same cause:** re-ran `resolve_paper_text()` directly against all 128 rather than trusting the aggregate number. 119 were genuinely both-non-English (confirmed via inspection: French thesis abstracts). The other 9 were **not** excluded by the documented gate at all — `resolve_paper_text()` said they should include via title-fallback (e.g. "Miniaturization of Semiconductor Lasers with Photonic Crystal Technologies", a completely normal English title). They were dropped one layer earlier: `load_corpus()`'s SQL query was `WHERE abstract IS NOT NULL AND length(abstract) > 0` — a `NULL` abstract (not just short) never reached the gate function at all, so it never got the same "fall back to title" treatment a placeholder/short abstract gets. This is why validating a fix against *live data* matters more than trusting the gate's documented behavior — the SQL pre-filter was invisible in the module's own logic.

**Fix 1 — NULL-abstract bug:** `load_corpus()`'s query now selects `COALESCE(abstract, '')` and filters on `title` instead of `abstract`; the coalesced `''` correctly falls into the existing too-short-abstract branch of `resolve_paper_text()`, which was already designed for exactly this case.

**Fix 2 — close the corpus-vs-served-mart gap architecturally, not just for these 9:** rather than re-deriving "what did the gate exclude" as a second, independently-maintained SQL filter (the same drift risk that made the Issue-3 regex narrower than the Python version), `document_embeddings` is now a Dagster `multi_asset` with two outputs computed in **one pass**: `document_embeddings` (unchanged) and `excluded_documents` (new — `doc_id`, `doc_type`, `exclusion_reason`, written to `r2://p2p-lake/intermediate/excluded_documents/v{date}/`). `load_corpus()` returns `(corpus, excluded)` instead of just `corpus` — the exclusion reason is inferred cheaply and correctly inside `load_corpus()` itself (if `resolve_paper_text()` returns `None` and the title isn't version-style, it must be the non-English branch, since the SQL query now guarantees a non-empty title) rather than by re-implementing the language check a second time.

**`stg_openalex_works`/`stg_patents_scoped` now exclude doc_ids from `ml_intermediate.excluded_documents`.** This is a genuine new cross-pipeline dependency that didn't exist before — dbt staging now depends on Part 5 having run. Handled via `create_external_sources()`: unlike `clusters`/`cluster_labels` (only registered once their R2 path exists), `excluded_documents` is **always** created as a view, falling back to an explicit empty relation (`SELECT ... WHERE FALSE`) when Part 5 hasn't produced it yet — so the staging `NOT IN` filter is a safe no-op on a fresh build, not a compile/run error.

**Verified before committing to the `multi_asset` design:** tested Dagster 1.13's `@multi_asset` + `AssetOut` + `MaterializeResult(asset_key=...)` pattern in isolation first (including the specific case of one output's key matching the underlying Python function's name) — confirmed both outputs materialize correctly and are independently selectable via `--select`, before writing the real implementation.

**Not yet done (next step):** re-run Part 5 (`document_embeddings`, `document_clusters`, `cluster_labels` — all three must run together since HDBSCAN reassigns `cluster_id`s on every run, which would desync `cluster_labels` from `document_clusters` if only a subset ran) to make `dim_paper.cluster_id IS NULL` actually drop from 128 → ~119 in the live warehouse, and to populate `excluded_documents` for the first time.

---

## UMAP non-determinism confirmed; out-of-scope-document hypothesis investigated and refuted (2026-07-05)

**UMAP is not idempotent in this environment, even single-threaded.** Double-fit test (same embeddings, `random_state=42`, back-to-back in one process): coords not byte-identical, noise swung 51,482–82,175 across repeated fits of *identical* input, largest cluster swung 5,876–63,882. Clamping every BLAS/numba thread to 1 (`NUMBA_NUM_THREADS`, `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, plus `numba.set_num_threads(1)`) reduced mean coordinate drift (3.20→1.10) but did **not** fix it (max diff still 18.64, noise still differed by 30,693). Root cause is not thread races but UMAP's spectral initialization (ARPACK/LOBPCG eigensolver) and/or pynndescent's approximate-NN graph, neither of which `random_state` fully pins. Parameter sweeps (`min_samples` 10/20/30/40 vs baseline 50, `n_components` 2 vs 8) also failed to reliably cut noise: 8D made noise dramatically *worse* (+33K–41K docs) because 2D UMAP artificially inflates local density — more dimensions means emptier space, not tighter clusters. Doc-weighted purity stayed rock-stable (0.97–0.98) across every arm regardless of noise swings, so purity was never actually at risk. **Practical implication: `document_clusters` violates CLAUDE.md #8 (idempotent assets) as currently built** — the fix is not to chase UMAP determinism (two independent levers both failed) but to freeze a chosen UMAP/HDBSCAN realization as a versioned artifact and stop silently recomputing it. Decision on the freeze design is pending.

**Out-of-scope documents (kitchen electronics, music papers, etc.) are NOT what's causing the ~35% noise rate — hypothesis tested and refuted with numbers, not assumption.** Full audit against the live warehouse (`main_marts.fact_document_cluster`, `fact_patent_filing`, `fact_publication`, `dim_paper`, `dim_patent`):
- **Papers are not leaking.** OpenAlex ingest filters on `primary_topic.id` only (`SCOPE_TOPIC_IDS` in `openalex.py`) — 100% of the 153,480 staged papers sit in exactly the 4 scope topics (T11338/T10299/T11429/T10502). There is no mechanism for an off-topic paper to enter.
- **Patents have a real leak surface, but the actual off-theme volume is small.** `patents_scoped` matches if **any** of a patent's CPC codes hits a scope prefix (`filter_patents_to_scope()` in `patentsview.py`), so a patent's *primary* CPC can be unrelated to the 10 narrow prefixes — 73% of patents' primary CPC falls outside those exact prefixes. But that figure is a definitional artifact of the prefixes being narrow (e.g. a flash-memory patent classed `G11C16` is still memory, not noise). Using a fair CPC-*subclass* definition of "in our technology areas" (litho/optics/photonics/memory/neural/compute + photoresist chemistry + EUV-source/nano), genuinely off-theme patents are 6,867 of 33,578 (20.5%) — and most of those are still adjacent (metrology, packaging, exposure control), not alien. Truly unrelated patents (business methods, medical devices, vehicles, non-G/H CPC sections) are only ~1,700 (≈5% of patents, ≈1% of the whole 186,930-doc corpus).
- **Direct keyword search for the user's own examples found almost nothing:** music/instrument 10 papers + 8 patents, kitchen/appliance 41 papers + 12 patents, food/beverage 27+34, game/sport 1+3 — combined ~0.05% of the corpus. And the "hits" are false alarms on inspection — e.g. the 10 "music" papers are reservoir-computing/neuromorphic titles like *"Musical Approaches For Working With Time-Delayed Feedback Networks"*, genuinely on-topic.
- **Decisive test — off-scope/off-theme patents have a LOWER noise rate than in-scope/in-theme ones, not higher:** narrow-prefix definition, in-scope 42.4% noise vs off-scope 32.8%; subclass definition, in-theme 36.6% vs off-theme 30.6%. Off-scope patents account for only 12.1% of all noise docs. If contamination were the driver, off-scope docs would show up *disproportionately* in the noise — they show up *less*.
- **Noise is a uniform 35.4% for papers AND patents separately** (54,289/153,352 and 11,874/33,578) — a global geometric property of the embedding/UMAP/HDBSCAN pipeline, not a contaminated subpopulation. Random samples of 25 noise papers and 25 noise patents are all clearly on-topic, technically legitimate documents (e.g. *"Very high efficiency optical coupler for silicon nanophotonic waveguide"*, *"Paradigm of Magnetic Domain Wall-Based In-Memory Computing"*).

**Conclusion: do not spend further effort cleaning scope to fix clustering quality — the noise is intrinsic diffuseness in real, on-topic research, not junk data.** This line of investigation is closed. One minor, separate finding survives: OpenAlex topics T10502/T10299 are broad enough to pull in neural-network *application* papers (speech recognition, image classification — ~245 hits) that are more about software than the chip itself. This is a scope-precision/"on-brand for the atlas" question inherited from the Part 0 topic choice, not a noise driver (those papers cluster normally) — worth a future editorial look, not an urgent fix.

---

## Part 5 re-run executed (2026-07-05): NULL-abstract fix confirmed, empty-title bug found and fixed for next time

**Ran all three ML assets + `dbt build` end to end** (`document_embeddings`+`excluded_documents` as one multi_asset select, then `document_clusters`, then `cluster_labels`) to close the pending item from the `excluded_documents`/NULL-abstract fix above. `document_embeddings` is a `multi_asset` — `dagster asset materialize --select document_embeddings` alone fails with `DagsterInvalidSubsetError` ("does not support subsetting"); must select both outputs together: `--select "document_embeddings,excluded_documents"`. Runtime: embedding step alone took ~66 minutes CPU-bound for 186,932 docs (no progress bar logged during the encode call — confirmed via `wmic process ... get UserModeTime` that the worker was actively multi-threaded, not hung, before concluding it was safe to keep waiting); `document_clusters` ~14 min; `cluster_labels` ~9 min (232 sequential Haiku calls, 0.5s delay between).

**Result: `excluded_documents` = 119 rows, all `doc_type='paper'`, all `exclusion_reason='non_english_content'`, zero patents.** This exactly matches the "119 genuinely non-English" figure isolated in the investigation above — confirming the 9 previously-mis-excluded papers (dropped by the NULL-abstract SQL bug, not genuinely non-English) are now correctly resolved. `dim_paper.cluster_id IS NULL` dropped from 128 to 7 — better than the ~119 predicted, because 9 of the 128 were the now-fixed bug, not 128 minus 119 landing on a residual 9; the actual residual of 7 is a **different, newly surfaced bug** (see below), not leftover from the fixed one. New live cluster snapshot: 232 clusters + noise, paper noise 40.2% (61,589/153,354), patent noise 27.5% (9,246/33,578), doc-weighted purity 97.3% — consistent with the run-to-run noise variance and stable purity already characterized in the UMAP non-determinism section above. `dbt build`: PASS=142, ERROR=0.

**New bug found during verification, same failure shape as the NULL-abstract bug: `title = ''` (empty string, not NULL) silently drops a paper from both the embedding corpus and `excluded_documents`.** `load_corpus()`'s SQL gate was `WHERE title IS NOT NULL AND length(title) > 0` — an empty string passes `IS NOT NULL` but fails `length > 0`, so the row never reaches `resolve_paper_text()` at all, even when the paper has a real, substantial abstract (all 7 live cases had 656–1,718 char English abstracts and would have embedded cleanly via abstract fallback if given the chance). Live consequence verified: 6 of the 7 already appear in `fact_publication` with a resolved `family_id` (e.g. `W2948384395` → `lasers`), counting toward mart totals while absent from `fact_document_cluster` and the map — the identical "invisible third state" the `excluded_documents` mechanism was built to eliminate, just triggered from the opposite field. Patents were unaffected this run (`dim_patent.cluster_id IS NULL` = 0) only because none currently have an empty title, not because the same gate couldn't produce the same bug — patent titles are the *only* text source PatentsView provides (no abstract field), so a patent with empty title genuinely has zero usable text, but the old `WHERE title IS NOT NULL AND length(title) > 0` on `patent_rows` would have dropped such a row from `patent_rows` entirely, silently, exactly like the paper case.

**Fix applied to `load_corpus()` (`pipelines/nexus/assets/ml/embeddings.py`), NOT yet re-run:** the paper query now admits a row if *either* title or abstract has content (`WHERE length(COALESCE(title,'')) > 0 OR length(COALESCE(abstract,'')) > 0`), coalescing both to `''` and letting `resolve_paper_text()` — which already handles an empty title by falling through to the abstract — make the real decision. The patent query drops its `WHERE` filter entirely; the loop now explicitly excludes a patent with no title under a new reason code `no_usable_text` rather than silently omitting it from `patent_rows`. 4 new tests added to `test_embeddings.py` (`test_load_corpus_falls_back_on_empty_title_paper_with_good_abstract`, `test_load_corpus_excludes_patent_with_no_title`), all 245 project tests pass, ruff and pyright strict both clean.

**Deliberately not re-run this session** — user chose "fix code now, defer the rerun" given the cost (another ~90 min cycle: CPU embed + UMAP/HDBSCAN reshuffling all 232 clusters again + re-running Haiku labelling on all of them) against the negligible blast radius (7 docs, 0.004% of the 186,932-doc corpus). **Known accepted state of the current live warehouse:** those 7 papers remain invisible on the map and absent from `fact_document_cluster`, while still counting toward `fact_publication`/`mart_family` totals for 6 of them. The fix is live in code for the *next* Part 5 re-run (whenever one next happens for any other reason), which will close this to zero. Do not treat the current 128→7 number as the final state of this bug class — it is a known, tiny, accepted gap, not a resolved one.

---

## Architecture pivot to MotherDuck (2026-07-05): served warehouse is now MotherDuck, not R2 gold Parquet

**Decision (user-directed).** Replace the R2 gold-Parquet serving layer with **MotherDuck** (managed DuckDB). New workflow: ingest → R2 raw → `dbt build --target prod` materialises staging→intermediate→marts **directly into MotherDuck** (`md:paper_to_patent`), reading raw Parquet from R2 via httpfs → ML assets read the corpus from MotherDuck → Streamlit app reads `main_marts.*` from MotherDuck. R2 stays as the raw/intermediate lake only. The `gold_export`→R2 step is gone.

**Design fork resolved via AskUserQuestion — user chose "Build the whole warehouse in MotherDuck"** (over the smaller "publish only the gold marts to MotherDuck, keep dbt→dev.duckdb" option). The fork existed because the ML assets (embeddings/clustering/cluster_labels/npl_matcher) read their input (`main_marts.dim_paper`/`dim_patent`, `main_staging.*`) from the local `dev.duckdb`, so moving the dbt build to MotherDuck strands them unless they too read MotherDuck. Chosen path rewires all four.

**Changes made (all code green: ruff + pyright strict + 244 pytest pass):**
- `models/profiles.yml`: added `prod` target (`path: md:{{env_var MOTHERDUCK_DATABASE, paper_to_patent}}`), keeps the r2 secret + httpfs (prod build still reads R2 raw). `dev` target unchanged.
- New `pipelines/nexus/resources/warehouse.py`: `warehouse_target()` / `connect_warehouse()` — one shared dev/prod switch (MotherDuck when `MOTHERDUCK_TOKEN` set, else `dev.duckdb`). Mirrors `apps/ui/data.py`.
- `dbt_assets.py`: Dagster runs `dbt build --target ${DBT_TARGET:-prod}` (defaults to MotherDuck; set `DBT_TARGET=dev` to build local from Dagster).
- 4 ML/transform assets use `connect_warehouse()` instead of a hardcoded `dev.duckdb` connect (`import duckdb as _duckdb_lib` removed from clustering.py + cluster_labels.py where it became unused; npl_matcher uses `read_only=False` since it writes `ref_npl_gold_eval`).
- `gold_export.py` + `test_gold_export.py` **deleted**; removed from `__init__.py`. `DuckDBR2Resource` kept — it is core infra used by every ingest/ER/ML asset, only gold_export was removed. Added `test_warehouse.py` (5 tests).
- `apps/ui/data.py`: `_r2_mode`/`_make_r2_conn`/`_R2_SUBDIRS` → `_md_mode`/`_make_md_conn` (`md:paper_to_patent`). App reads MotherDuck when `MOTHERDUCK_TOKEN` set, else local `dev.duckdb`.
- `.env.example`: R2 read-only block → `MOTHERDUCK_TOKEN` (+ optional `MOTHERDUCK_DATABASE`, `DBT_TARGET`).
- Docs (mandatory doc-maintenance): CLAUDE.md, README.md, ARCHITECTURE.md (§3/§5/§9 + deliberately-not + secrets + 2 new Known Limitations), SETUP.md (C1/C2 + new C3 MotherDuck + F1 + out-of-scope + env block), docs/data_source_manifest.md (5 mart storage annotations + credentials line), ROADMAP.md (Part 7 arch note/steps + v2 backlog item 6 marked done), docs/findings.md. **Left as historical:** ROADMAP completed-Part goal statements ("gold layer to R2", ~lines 202/233/310/422).

**Credential split (mirrors the old R2 split):** pipeline uses a read-write `MOTHERDUCK_TOKEN`; the app must use a separate **read-only (read-scaling)** MotherDuck token. Same env-var name, different value per environment.

**VERIFIED END-TO-END 2026-07-05** (user supplied a read-write `MOTHERDUCK_TOKEN`; MotherDuck region `aws-eu-central-1`, DuckDB 1.5.4):
1. **Required fix found — R2 secret needs `region: auto`.** The #1 risk (R2 read from a MotherDuck session) first failed with `InvalidRegionName: 'eu-central-1'` — MotherDuck's cloud passes its own AWS region to R2, which R2 rejects (valid: wnam/enam/weur/eeur/apac/oc/**auto**). Fix: added `region: auto` to the **prod** target's r2 secret in `models/profiles.yml` (the dev target reads R2 on the laptop, where the default resolves, so it does NOT need it). After the fix MotherDuck read 153,490 raw OpenAlex rows from R2.
2. **`dbt build --target prod` = PASS=142 WARN=0 ERROR=0 in 66s** — 22 table models + 118 tests + 1 view built into MotherDuck `main_marts.*` / `main_staging.*`, reading raw straight from R2. Matches the dev.duckdb build.
3. **App read path verified** — with `MOTHERDUCK_TOKEN` set, `apps/ui/data.py` `_md_mode()`=True and `load_family_scorecard` / `load_cluster_bubble` / `load_family_top_orgs` return correct 3-way data from MotherDuck (euv/silicon_photonics/neuromorphic_in_memory; 232 clusters).

**STILL PENDING (lower risk now — the `md:` connect + R2-read pattern is proven):**
- The Dagster ML assets (`embeddings`/`clustering`/`cluster_labels`) and `npl_matcher` reading/writing MotherDuck via `connect_warehouse()` have NOT been executed against MotherDuck (embeddings alone is a ~90-min CPU job). Same connection pattern as verified; inputs now exist in MotherDuck; should work; not yet run.
- No new PyPI dep — MotherDuck is the auto-installed DuckDB `motherduck` extension; `duckdb>=1.1.0` / `dbt-duckdb>=1.8.0` already support it.

**Read-only app token — RESOLVED as "not possible on free tier" (2026-07-05).** MotherDuck's free tier cannot issue read-scaling (read-only) tokens — user confirmed while trying to create one. Decision: the app runs on the same read-write `MOTHERDUCK_TOKEN` as the build pipeline. This is a conscious departure from the credential-split note above and from the CLAUDE.md hard rule, accepted because the warehouse is fully derived and rebuildable from R2 via `dbt build --target prod` in ~1 min — a leaked token risks downtime, not data loss. Mitigations: keep the Streamlit app **private** while on this token; rotate + redeploy if it ever leaks; move to a genuine read-only token on a paid MotherDuck tier. Docs updated same-session to reflect this as the accepted default, not a TODO: `CLAUDE.md` hard rule reworded, `SETUP.md` (intro token note, C3 steps, F1 steps), `ARCHITECTURE.md` (§9 serving rationale, secrets & security, new Known Limitations bullet).

---

## Checkpoint-review follow-up (2026-07-06): 3 issues closed against live verification, not memory

Re-verified the 2026-07-04 Part 0-7 checkpoint review's 6 issues against the live warehouse (dev.duckdb + R2), rather than trusting prior session notes. Three were addressed this session:

**Issue 1 permanent guard added.** New singular dbt test `models/tests/assert_fact_document_cluster_no_orphans.sql` — fails if any `fact_document_cluster` row's `doc_id` is absent from `dim_paper`/`dim_patent`. Passes on live data (0 orphans, confirmed both directions). This is the guard the checkpoint review asked for after the original 1,103-orphan bug; the `fact_document_cluster` inner-join fix (Issue 3, 2026-07-04) already makes orphans structurally impossible, but nothing previously caught a regression if that join were weakened.

**The 7 null-cluster papers — root cause was already found and fixed in code (2026-07-05), just not yet re-run.** Independently re-derived the same diagnosis live rather than trusting the prior write-up: all 7 have a genuinely empty (`''`, not `NULL`) `title` in raw OpenAlex data with a real 656–1,718 char English abstract; `load_corpus()`'s old SQL gate (`WHERE title IS NOT NULL AND length(title) > 0`) dropped them before `resolve_paper_text()` ever ran, so they're absent from `excluded_documents` too — invisible on the map, still counted in `fact_publication`/`mart_family` for 6 of them. Confirmed via `embeddings.py`: the fix (admit a row if *either* title or abstract is non-empty) and its tests (`test_load_corpus_falls_back_on_empty_title_paper_with_good_abstract`, `test_load_corpus_excludes_patent_with_no_title`) are already present and passing. Only the actual Part 5 re-run to apply the fix to the live warehouse remains outstanding — deferred given cost (~90 min, full re-cluster) vs. blast radius (7/186,932 docs). Added a manifest note (`docs/data_source_manifest.md`) documenting this as a known, accepted gap, not a resolved one.

**Issue 4 (apps/ui outside CI) — closed.** Fixed all 39 ruff errors in `apps/ui/` (18 auto-fixed, 21 manual — mostly line-length wraps, one `E402` from a misplaced module-level dict between two import blocks in `3_Org.py`). Pyright strict on `apps/ui/` was ~500 errors, ~91% `reportUnknown(Variable/Argument/Member)Type` cascades from Streamlit/Plotly/streamlit-searchbox's incomplete type stubs — not real bugs, strict mode fighting duck-typed third-party APIs. User chose (via AskUserQuestion): fix real import-resolution errors, run `apps/ui/` at `basic` mode, skip the stub-cascade noise. `executionEnvironments` in `pyproject.toml`'s `[tool.pyright]` table does **not** take effect for CLI-targeted runs (`pyright apps/ui/`) in this pyright-python version — verified empirically (setting `typeCheckingMode = "off"` in the execution environment had zero effect on error count). Switched to the per-file `# pyright: basic` pragma comment instead (guaranteed to work regardless of CLI invocation), plus a top-level `extraPaths = ["apps/ui"]` in `[tool.pyright]` to resolve the `pages/*.py → data.py/render.py` `sys.path.insert` import pattern. Result: 538 → 0 errors. Fixed the ~15 genuine remaining issues along the way (not suppressed): `PlotlyState` TypedDict subscript access (`.selection` → `["selection"]`), `StyleOverrides` TypedDict annotations for the searchbox style dicts (3 places), a `max(dict, key=dict.get)` overload ambiguity, and a real (if currently unreachable, since `dim_paper.publication_date` is `not_null`) `Optional[date].isoformat()` risk in `4_Trace.py` — added an explicit guard + `assert` chain (pyright's narrowing doesn't cross `for`-loop boundaries at module scope, needed 3 separate asserts). CI (`ci.yml`) now runs ruff + pyright on `apps/ui/` alongside `pipelines/nexus/`. `apps/ui/` still has no pytest suite — out of scope for this pass, noted in `ARCHITECTURE.md`.

**Issue 5 (stale ER docs) — the "growth" was a units mismatch, not new data.** The live crosswalk's `fuzzy_high` = 1,818 rows looked like 658 new matches needing re-validation beyond the 2026-06-22 precision record (1,160 rows). Verified directly against R2: `fuzzy_org_bridge` has **not been re-run since 2026-06-22** — still exactly 1,160 pairs, still 100% at score=100. The discrepancy is `assemble.py`'s `build_org_crosswalk()` emitting *two* crosswalk rows per fuzzy-matched pair (one `openalex`-source, one `patentsview`-source) when the PV side isn't already seeded: 1,160 pairs + 661 non-seeded PV assignees ≈ 1,818 rows (predicted 1,821; 3-row gap explained by a few institutions already claimed by an earlier seed/ROR-bridge layer). No new precision measurement was possible or needed — the entire live universe of fuzzy matches is still the same 1,160 pairs already validated. Live regression spot-check (not a full re-validation): Samsung Electronics/Samsung Display and KLA/Tencent still resolve to different `org_id`s in the current crosswalk snapshot — no merge regressions. Documented in `docs/er_eval_set.md` (new dated record) and `docs/data_source_manifest.md` (corrected the misleading "worth a follow-up run" note, which was based on the false premise that new matches existed).

---

## CI failure after push (2026-07-06): a local top-level `data/` directory silently masked a real ruff isort bug

Pushed the checkpoint-review fixes commit; GitHub Actions CI failed on `ruff check pipelines/nexus/ apps/ui/` with 5 `I001` (import-block-unsorted) errors in `apps/ui/{app,1_Map,2_Family,3_Org,4_Trace}.py` — despite `uv run ruff check apps/ui/` passing cleanly on this machine immediately before pushing, including with `--no-cache`.

**Root cause: ruff's isort classifies unconfigured local modules by scanning the filesystem for a same-named file/directory relative to the project root, not by static analysis of the import graph.** `apps/ui/data.py` is imported everywhere as `from data import ...`. This repo also has a **top-level `data/` directory** (gitignored, holds manually-downloaded raw PatentsView TSVs per the D1 setup step) sitting right next to `apps/`. Debug output (`ruff check -v`) showed `'data'` categorized `Known(FirstParty) (SourceMatch(...))` — ruff found the top-level `data/` dir and used it as proof `data` is a first-party module — while `'render'` (no top-level `render/` exists) fell through to `Known(ThirdParty) (NoMatch)`. Because the existing code happened to already group `render` with `streamlit` and separate `data` into its own block, this *accidental* two-category split matched what ruff computed on my machine and reported "all checks passed" — a false negative caused entirely by an untracked directory that will never exist on a clean checkout (CI, or any other contributor's fresh clone). **Reproduced and confirmed by cloning the exact pushed commit into a scratch directory** (`git clone` + `uv sync --all-extras`, no top-level `data/` present there) — the same 5 errors appeared, proving this was not a caching artifact.

**Fix:** added `[tool.ruff.lint.isort]` `known-first-party = ["data", "render", "tour"]` to `pyproject.toml`, pinning the classification explicitly instead of relying on ruff's filesystem heuristic. This makes the categorization identical on every machine regardless of what happens to sit at the repo root. Verified via the `-v` debug log that all three now report `Known(FirstParty) (KnownFirstParty)` consistently. Re-ran `ruff --fix` to correct the now-consistent ordering (merges `data`/`render` into one first-party block, alphabetical) — 5 files changed, purely import-line reordering. Full pyright + pytest suite still green after the fix.

**Lesson: a clean local check is not proof of a clean CI check when the working directory contains anything outside git's view that could influence a tool's heuristics** (stray top-level dirs, local config files, environment variables). Where a linter's behavior can depend on ambient filesystem/environment state, pin the config explicitly rather than trusting whatever the tool infers — and when in doubt, verify against a genuinely clean clone before treating a local "all checks passed" as final.

---

## Full pipeline refresh, 2026-07-06: OpenAlex re-ingest → ER → NPL → ML → prod, plus two new operational bugs found and fixed

**Scope:** re-ran the entire chain from OpenAlex ingest through dbt docs generation in one session — `openalex_works_raw` (with the `type:article|preprint|review` ingest filter, coded 2026-06-27 but never yet exercised) → full ER crosswalk chain → `npl_links_raw` → Part 5 ML (embeddings/clusters/labels) → `dbt build --target prod` → `dbt docs generate`. Triggered by a user request to re-ingest OpenAlex; expanded to include the ER and NPL reruns after discovering `openalex_institutions_staging` has a real Dagster `deps=["openalex_works_raw"]` edge, and `npl_links_raw` matches against OpenAlex works by DOI/title — both were stale relative to the corpus that had already existed since 2026-07-04.

**Finding 0 — the OpenAlex re-ingest was already partially done and undocumented as such.** Before touching anything, found `r2://p2p-lake/raw/openalex/v2026-07-04/works.parquet` (153,490 rows, `type` populated) already existed — a prior session had re-ingested with the new filter but never logged the *ingest event* itself in `MEMORY.md` (only its downstream effects, e.g. the `mart_family` "Verified 2026-07-04" figures in `docs/data_source_manifest.md`). **Lesson: when a memory file's narrative log doesn't mention an action, check the actual data/artifacts before assuming the action never happened** — the manifest's "Verified 2026-07-04" annotations were the tell. Re-ran the ingest anyway (`v2026-07-06`, 153,490 rows — identical count, confirming no corpus drift in 2 days) since the user asked for it explicitly and it's cheap/safe.

**Dagster's `+` selection suffix is 1-hop, not unlimited depth — `*` is unlimited.** `dagster asset materialize --select "openalex_works_raw+"` only pulled in `openalex_institutions_staging` (1 hop downstream), not the further chain (`seed_crosswalk_oa_matched`, `fuzzy_org_bridge`, `ror_bridge`, `org_crosswalk`). Had to re-select the remaining assets explicitly by name. Use `asset_name*` for "and everything downstream, unlimited depth."

**Bug found and fixed (this session) — a self-referential staleness gap in the `excluded_documents` mechanism, distinct from (but same failure class as) the empty-title/NULL-abstract bugs found 2026-07-05.** After the first ML pass this session, `dim_paper`/`dim_patent` null-`cluster_id` count came back as **120**, not the expected ~0-1. Root cause, confirmed by exact doc_id overlap with the prior run's `excluded_documents` snapshot (119/120 matched exactly): `document_embeddings` read `dim_paper` as it stood after the pass-2 dbt build, which still excluded those 119 known-bad papers via the *stale* (2026-07-05) exclusion snapshot. The fresh embedding run therefore never saw them, correctly found nothing new to exclude, and wrote an *empty* `excluded_documents` snapshot. The next dbt build then rebuilt `stg_openalex_works` against that new, empty snapshot — which no longer blacklists the old 119 — so they flowed back into `dim_paper`, arriving too late to be embedded/clustered that cycle. **This is structural, not a one-off:** `excluded_documents` only ever reflects what its own run's *input* contained; a document already filtered out upstream is invisible to the gate and silently drops off the exclusion list the next time it runs, unless the corpus it reads from is fully unfiltered first.

**Fix applied: ran the ML cycle a second time.** Once the pass-3 dbt build had (correctly, if temporarily) reintroduced all 153,480 papers into `dim_paper` with the empty exclusion snapshot, re-running `document_embeddings` against that now-complete `dim_paper` let the gate correctly re-decide on every candidate paper: found 118 to exclude (non-English, matching the historical ~119 within natural drift), and this time nothing was invisible to it. Re-ran `document_clusters` + `cluster_labels` + `dbt build` + re-triggered `dbt-docs.yml` on top of that. Final: **186,940 docs (153,362 papers + 33,578 patents), 240 named clusters + noise, `dim_paper`/`dim_patent` null-cluster count = 0 both, confirmed.**

**Operational rule for next time:** when re-running Part 5 as part of a larger refresh (not in isolation), either delete the previous `excluded_documents` R2 snapshot *before* the first embeddings pass (so the gate always sees a fully unfiltered `dim_paper`), or budget for running the ML cycle twice and check `dim_paper.cluster_id IS NULL` after the first post-ML dbt build before declaring the refresh done. Don't trust "0 excluded this run" as good news without checking whether `dim_paper`'s input was itself already filtered.

**New operational gotcha — a killed `dbt build` in the background leaves a corrupting `dev.duckdb.wal`.** Three times this session, a *backgrounded* `dbt build --target dev` process was killed (status `killed`, not `completed`/`failed`) partway through, always around the same point (the long-running `stg_npl`/`stg_patent_citations` staging models). Each kill left a large uncommitted `models/dev.duckdb.wal` (12–32 MB) next to `dev.duckdb`; the *next* backgrounded attempt against the same file also got killed, at the same relative point, with no error message — consistent with the writer stalling on WAL recovery/lock contention and getting killed by an idle-output watchdog rather than genuinely crashing (no orphaned `python.exe`/`dbt.exe` processes were ever found via `tasklist`). **Fix that worked every time:** delete `dev.duckdb` + `dev.duckdb.wal` (both fully regenerable from R2 — confirmed gitignored, `*.duckdb` / `*.duckdb.wal`) and retry. **Second fix that avoided the problem entirely:** running the same `dbt build --target dev` command in the **foreground** (not backgrounded) completed cleanly every time it was tried — the build only takes ~85s, comfortably under the Bash tool's default synchronous timeout, so foregrounding it sidesteps whatever kills long-idle-output backgrounded jobs. **Rule: prefer foreground execution for the dev-target `dbt build` steps specifically** (they're fast); reserve backgrounding for the genuinely long steps (OpenAlex ingest, embeddings, clustering, Haiku labelling).

**ER crosswalk re-run, 2026-07-06:** `org_crosswalk` → 16,235 rows / 14,198 distinct org_ids (was 16,215/14,179 on 2026-07-04, itself stale since 06-22 — the ER chain had never been re-run against the corpus that's existed since 07-04 until this session). `fuzzy_org_bridge` found 2,320 fuzzy_high pairs this run vs. the 1,160 that had been sitting unchanged since 2026-06-22 — a genuine fresh re-match against the current (larger, post-type-filter) OpenAlex institution set, not just re-stating old numbers. No fuzzy_review band, same as always.

**NPL matcher re-run, 2026-07-06:** conditional precision 0.847 at threshold=90 (was 0.831 on 2026-06-22's stale matcher run) — 6,139 total links (1,092 DOI/high + 5,047 fuzzy/medium after dedup). Threshold=90 remains the chosen operating point (lowest clearing the ≥0.80 floor); 95 and 100 were re-evaluated too and still don't beat it on recall for a similar precision.

**Final corpus/mart state after the full refresh:** 186,940 docs (153,362 papers + 33,578 patents), 240 named clusters + noise (39.7%/40.3% paper/patent noise — within the already-characterized UMAP run-to-run variance band, not a regression), org_crosswalk 16,235 rows/14,198 org_ids, NPL links 6,139 (1,076 high + 4,719 medium post date-filter in `fact_npl_link`). `dbt build --target prod` (via `dbt-docs.yml`, triggered twice — once before and once after the ML gap-fix cycle) both green, docs republished to GitHub Pages both times. pytest 244/244, ruff clean, pyright 0 errors (pyright not re-run after the second ML cycle since no source files changed, only data).

---

## Patent-scope tightening: any-position → top-5 CPC rule (2026-07-08)

**Decision + why.** Investigated the persistent generic-ML noise cluster (`c_15`→`c_70`, ~6,895 docs, a plausible tagline hiding off-domain content). **Root cause, finally identified:** the patent-scope filter (`filter_patents_to_scope` / the `patents_scoped` asset, `patentsview.py`) admitted a patent if a scope CPC code appeared at **any** position among its codes. A patent carries ~12 CPC codes spanning ~2.7 subclasses on average, so a logistics / biometric / medical / animation patent that tagged a neural-net or memory code deep in its list still passed. **38% of the old 33,578-patent corpus had a *primary* CPC outside the six scope subclasses (G03F/H01S/G02B/G06N/G11C/H10N)** — and those off-domain patents share generic-ML vocabulary and collapse into one embedding cluster. The paper side was already clean on this axis (OpenAlex filter is on `primary_topic.id` only; residual off-topic papers are OpenAlex's own primary-topic misclassifications, high-confidence, not fixable by extra fields — empirically checked 12 known-bad papers via the API).

**Options weighed (all measured on the corpus, see the analysis in the 2026-07-08 chat / scratch scripts):**
- any-position (old): 33,578 patents.
- top-5 on the 10 narrow scope codes (**chosen**): 23,397 (−30.3%). Strict subset of the old corpus — only drops, never adds.
- primary-CPC-only, broad 6 subclasses: 20,706 (−38.3%). Cleanest ("primarily about the tech") and would kill the noise entirely, BUT drops ~21% of genuine in-domain patents whose scope code is prominent-but-not-primary (e.g. real neuromorphic patents with primary `G06N3/08`, a sibling of our listed `G06N3/049`). Rejected as too aggressive.
- top-5 on the broad 6 subclasses: only −9.5%, and would *gain* patents (broadening codes) incl. generic software-ML (`G06N20`) — rejected.

**Implemented:** added `SCOPE_CPC_MAX_SEQUENCE = 4`; both `filter_patents_to_scope` and the `patents_scoped` asset SQL now require `TRY_CAST(cpc.cpc_sequence AS INTEGER) <= 4`. No re-download needed — `load_bulk_tsv` keeps all TSV columns, so the raw R2 CPC parquet already had `cpc_sequence`; the `patents_scoped` asset re-reads raw and re-filters. Fixture test extended with boundary cases (scope code at seq 4 kept / seq 5 dropped); 11/11 pass, ruff + pyright clean.

**Execution (full re-cluster, user chose this over mart-level-only):** re-ran `patents_scoped` (→ 23,397, exact match to the warehouse prediction) → **deleted the stale v2026-06-21 `patents_scoped` snapshot** (critical: `patentsview_orgs_staging` reads `patents_scoped/*/*.parquet` as an all-dates glob, so leaving the old snapshot would have unioned the loose corpus back in) → re-ran ER (orgs_staging/fuzzy/ror/crosswalk; note fuzzy_org_bridge also unions all orgs_staging snapshots so the crosswalk came out a superset = same 16,235/14,198 — harmless, marts only join surviving assignees) → **cleared the `excluded_documents` snapshots before the pre-embedding dbt build** (applied the 2026-07-06 operational rule the right way, so the orphan bug did NOT recur — one ML cycle, not two) → re-embed (176,759 docs, 118 excluded) → re-cluster (**227 named clusters**, 41.1% noise) → re-label (Haiku, 227/227) → final `dbt build` → `dbt-docs.yml` prod promotion (2m57s, green). `dim_paper`/`dim_patent` null-cluster = **0/0** on dev and MotherDuck prod.

**Outcome — honest.** The tightening reduced the noise ~76% but did **not** eliminate it: it reformed as **`c_77` "Machine Learning Signal Processing Methods"** (1,654 docs, 1,564 patents, 68% off-family primary CPC — biometrics/finance/analytics patents that carry a *prominent* neural-net code in their top-5). This is the exact, disclosed limit of top-5 vs primary-only, communicated to the user before they chose. After tightening, ~44% of the 23,397 patents have a NULL `family_id` (up from 38%), because top-5 also drops some genuine patents whose scope code was buried while keeping off-family patents whose scope code is prominent — the "caught in the middle" property. Accepted as a deliberate trade (keep breadth, tolerate a shrunken residual noise cluster) rather than the −38% primary-only cut.

**New headline numbers (2026-07-08):** corpus 176,759 (153,362 papers + 23,397 patents), 227 clusters. Fastest NPL lag c_71 "Neural Networks and Reinforcement Learning" 2.05yr N=129 (broad; fastest *specific* is c_68 2.19yr). Slowest c_117 "Memristor-Based True Random Number Generation" 6.23yr N=24 (same value/topic as prior cycle — stable). **Highest HHI: c_2 "Lithographic Apparatus" = 1.0, one assignee holds all 161 patents — a true monopoly this cycle (prior best was 0.96).** Breadth-vs-concentration c_155 "Memristor-Based Logic and Computing" 478 institutions / 5 assignees / HHI 0.32 / 10 patents. Family patent shares: EUV 44.3% (4,145 pat, top TSMC), Silicon Photonics 5.1% (2,518, top IBM), Neuromorphic & In-Memory 19.8% (6,492, top Micron) — neuromorphic lost the most patents (~41%) since that's where the generic-ML noise was concentrated. Docs updated: ROADMAP Part 0 scope contract, findings.md, cluster_label_review.md, data_source_manifest.md, this file. README unchanged (no count claims; CPC *codes* unchanged, only the matching rule).

**Env/run notes for next time:** Dagster CLI works from repo root as `set -a; source .env.local; set +a; unset MOTHERDUCK_TOKEN; PYTHONPATH=pipelines uv run dagster asset materialize -m nexus --select <sel>` (unset MOTHERDUCK_TOKEN → dev/`dev.duckdb`; keep it set only for prod reads). dbt: `uv run dbt build --target dev --project-dir models --profiles-dir models`. Foreground dbt (fast ~86s); background the long ML steps. R2 object delete via Cloudflare API uses `CLOUDFLARE_API_TOKEN` (distinct from the R2 S3 key/secret). `DBT_DUCKDB_PATH` = `models/dev.duckdb` (absolute), shared by dbt and `connect_warehouse()`.

---

## Clustering-quality deep-dive → 'Mixed' family floor + clustering freeze (2026-07-08, session 2)

**Context: user challenged the ML foundations** (41% noise, 33% clusters <90% purity). Ran a controlled, *un-confounded* dimensionality sweep on the CACHED embeddings (176,759×384, pulled once from R2 `intermediate/embeddings/v2026-07-08`, cached to a local `.npz`; UMAP+HDBSCAN on cached vectors is minutes/arm, no re-embed). Baseline nc=2/md=0.1/ms=50 = 38.8% noise, purity 0.980. **Every 5D/10D arm was WORSE on noise (42–45%), not better** — even with min_samples dropped to 5–15 (the correction the 2026-07-05 sweep lacked; that one held ms=50 fixed and was therefore confounded). Purity stayed rock-stable 0.974–0.980 across ALL arms. **Verdict: clustering dimensionality is not the lever — higher-D increases noise (curse of dimensionality flattens HDBSCAN density; 2D concentrates it), and the ~40% noise is intrinsic to the embedding geometry, now confirmed by a clean test.** Also: the noise number itself is unstable run-to-run (UMAP non-determinism; MEMORY 2026-07-05 recorded 27.5–44% on identical input), which matters more than the level.

**KEY DISCOVERY — the live "map" is NOT a UMAP scatter.** `apps/ui/pages/1_Map.py` ("Technology Landscape") is a bubble chart: one dot per cluster, X=granted US patents (log), Y=research papers (log), colour=family. It never uses `umap_x`/`umap_y`. `load_umap_points()` in `data.py` (the UMAP scatter) has **zero callers** — dead code. So (a) the "cluster in 2D for map coherence" constraint the user and I both assumed was moot, and (b) the headline claims (lag/HHI/share) run on each doc's own `family_id`, not on cluster membership — so noise touches map *coverage*, not analytical integrity.

**Two fixes shipped (dev only; NOT yet committed/promoted to prod):**

**1. 'Mixed' family confidence floor (`seed_cluster_family.sql`).** The old majority-vote assigned EVERY cluster a family with no floor (0 `adjacent` clusters ever), so a 37%-plurality off-scope cluster (e.g. "Transformer Models for Vision and Language") got a confident colour. NEW rule: a cluster gets a real family only if **purity ≥ 0.80** (dominant family / family-RESOLVABLE docs) **AND coverage ≥ 0.50** (resolvable docs / all docs); else `family_id='mixed'` (renamed from `adjacent`; display label "Mixed"). **Two thresholds, not one — this was the crux:** the user first specified "NULL patents count as Mixed in the denominator" (single 0.80 floor over ALL docs). Implemented and measured → it demoted **24 clean single-technology clusters** (e.g. c_41 "Cross-Point Memory Arrays", 99% in-memory among real docs) to Mixed purely because they're patent-heavy and ~30% of patents have off-scope PRIMARY CPCs. Surfaced this with data; user chose the refined two-threshold version ("genuinely-mixed only"). Result: **19 Mixed** (was 41 under the single floor), all genuinely multi-family (c_32 EUV-FEL, c_26/c_29 RRAM split silicon/memory) or off-scope (c_45 Transformer, c_77 residual-noise, c_30 Academic Publishing, c_47 Power System). `adjacent`→`mixed` renamed across `render.py`, `app.py`, `data.py`, `1_Map.py`, `2_Family.py`, `_schema.yml`, `mart_family.sql`. New singular test `assert_seed_cluster_family_floor.sql` re-derives both thresholds from source. **This is a DISPLAY-label change only** — `fact_*.family_id` (per-doc, authoritative for counting) is untouched. New `mart_family`: EUV 25 clu/5,159 pap/3,558 pat; Silicon Photonics 125/45,798/2,267; Neuromorphic&In-Memory 58/26,092/4,289; Mixed 19/927/3,041 (excluded from headline charts, same as adjacent was).

**Why NULL family exists at all** (asked, verified live): a doc has a family only if its PRIMARY code maps to a scope prefix. Patents: 6,975/23,397 (29.8%) NULL — all have a primary CPC, it's just off-scope (G06F/G06Q/G06T/H04L…); they entered via the top-5 rule on a secondary scope code. Papers: 6,889 (4.5%) NULL, ALL T10502 keyword-misses — but at the **3-way** grain T10502→neuromorphic_in_memory directly, so papers are never NULL in `seed_cluster_family` (only in the finer 5-way `fact_publication`). Rejected the user's "assign patent family via first-in-top-5 CPC" idea after measuring it: rescues all 6,975 NULL but **doubles neuromorphic** (2,692→5,556) with software-AI/business-method patents — off-brand contamination for a hardware atlas.

**2. Clustering freeze (`clustering.py`).** UMAP non-determinism means every `document_clusters` run reshuffles cluster IDs/noise/coords, invalidating Haiku taglines + `cluster_label_review.md` + `findings.md` citations (CLAUDE.md #8 violation, was "pending" in ARCHITECTURE §8). **Design (user-chosen): freeze when corpus unchanged, re-cut when documents onboarded** — NOT the model-freeze/`approximate_predict` option (Option B), because emerging tech genuinely needs new clusters. New pure helper `corpus_signature(doc_ids)` = 16-char sha256 of the sorted-deduped doc-id set (order/duplicate independent; 6 unit tests). Asset now: locate embeddings → compute current signature → compare to the `corpus_signature` column stamped on the latest clusters snapshot → identical = reuse (skip, log `frozen=True`); different/absent = re-cut a new dated snapshot. Added `corpus_signature` column to `clusters.parquet` (safe: `create_external_sources` does `SELECT *`, `fact_document_cluster` selects named cols only — verified with a build). **One-time backfill** (`scratchpad/backfill_signature.py`, stage-then-promote) stamped the existing v2026-07-08 snapshot (sig `93e1ad8ccf8265e6`, computed from the EMBEDDINGS doc-ids so it matches what the asset computes) — adopts the current realization as frozen WITHOUT re-clustering. Verified: freeze check returns REUSE. **Gotcha:** DuckDB `DESCRIBE SELECT` returns column NAME in field [0], TYPE in [1] — I initially checked [1] and the backfill aborted (safely, before promote). To force a deliberate re-cluster in future: it happens automatically when the corpus changes; there is no manual flag (by design).

**Completed (2026-07-10):** doc updates finished (data_source_manifest.md schema+freeze, ARCHITECTURE.md §8 freeze-decided, cluster_label_review.md Mixed note), full gate green (`dbt build --target dev` PASS=174, `ruff` clean, `pyright` 0 errors, `pytest` 252 passed), committed as two feature commits (freeze; Mixed floor + rename) plus a shared-docs commit on `feat/part-8-fixes_and_enhancements`. Prod (MotherDuck) still NOT rebuilt as of this commit — the UI `adjacent`→`mixed` rename and the `seed_cluster_family` change must deploy together (merging to main triggers `dbt-docs.yml`'s prod build since `models/**` changed; Streamlit redeploys from git). Deployment ordering still matters at merge time: prod mart + UI must land together.

---

## dbt↔ML cycle broken → one acyclic graph (2026-07-11)

**Weakness #4's structural half (the deeper fix, user-approved).** The pipeline was NOT a clean single-pass DAG: the honest dependency graph had two cycles, worked around by the empty-relation bootstrap + a manual two-pass. User designed the two fixes with me, I implemented.

**Two feedback edges, both cut:**
1. **staging depended on the embedding asset's `excluded_documents`.** The quality gate (langdetect + title heuristics) never needed embeddings, so it moved UPSTREAM into a new **`document_exclusions`** asset (`exclusions.py`) that reads the RAW corpus (openalex works + patents_scoped parquet) and writes `excluded_documents` BEFORE staging applies it. work_id extracted with the same `regexp_extract(openalex_id,'W([0-9]+)',0)` staging uses → exclusion set byte-for-byte identical. `document_embeddings` is now a plain `@asset` (was `multi_asset`), reads the already-clean dims, only embeds. `load_corpus()` returns corpus only (was `(corpus, excluded)`); new pure `compute_exclusions()` holds the gate logic (tested in `test_exclusions.py`).
2. **`dim_paper`/`dim_patent` back-filled `cluster_id` from `fact_document_cluster` while embeddings read the dims.** Dims now drop `cluster_id`; the bridge `fact_document_cluster` (already one-row-per-doc) is the sole doc→cluster source. **4 readers rerouted to the bridge:** `seed_cluster_family` paper-votes, `assert_seed_cluster_family_floor.sql` (both slipped past `dbt compile` — only caught at `dbt build`, binder error; compile does NOT bind columns), `mart_gap.npl_lag`, `apps/ui/data.py::load_trace_paper`.

**Orchestration:** single `@dbt_assets` split into `paper_to_patent_dbt_pre` (`exclude=POST_SELECT`) and `paper_to_patent_dbt_post` (`select=POST_SELECT`) over the same manifest, disjoint + exhaustive (12 + 11 = 23). `POST_SELECT` = `source:er_intermediate.npl_links+ source:er_intermediate.mf_npl_links+ source:ml_intermediate.clusters+ source:ml_intermediate.cluster_labels+` (NOT excluded_documents — it feeds staging=PRE). `_NexusDbtTranslator.get_asset_key` maps the 5 mid-pipeline sources → Python asset keys. Python assets gained honest `deps` (note dbt model keys are FOLDER-PREFIXED: `AssetKey(["marts","dim_paper"])`, `["staging","stg_npl"]` — Python asset keys are single-segment). `create_external_sources` KEPT (still the R2→dbt-source view bridge; Dagster deps don't create the DuckDB views); its excluded_documents empty-relation is now defensive-only.

**Verified:** `dagster definitions validate -m nexus` loads acyclically (the honest deps that previously would have formed a cycle — the real proof; a clean load = topological sort succeeded). Confirmed the wired edges via `defs.resolve_asset_graph()` (`dim_paper <- staging/stg_openalex_works` only; `document_embeddings <- marts/dim_paper,dim_patent`; `stg_openalex_works <- document_exclusions`). `dbt build --target dev` of the changed models + `mart_gap` → all tests PASS. ruff clean, pyright 0 errors, pytest 272. Committed CODE as `refactor(pipeline): break the dbt<->ML cycle into one acyclic graph` (da93214), docs in a follow-up.

**Env note:** the Dagster `@dbt_assets` reads `models/target/manifest.json` at import — after any model dependency change, regenerate it (`dbt parse --project-dir models --profiles-dir models --target dev`) BEFORE `dagster definitions validate`, or Dagster sees the stale (cyclic) graph. `models/target/` is gitignored (CI/deploy regenerates the manifest). **Not done:** full prod (MotherDuck) rebuild via a real `materialize all` — left to the user (OpenAlex once-a-day rate limit, embedding compute).

---

## Acyclic graph: live end-to-end verification surfaced a real concurrency bug (2026-07-11/12)

**User asked to actually run the refactored pipeline** (skip raw ingest — already had OpenAlex/PatentsView raw snapshots — run every downstream step + `org_crosswalk` into `dev.duckdb`, background, notify on completion). Two env switches needed aligning: `DBT_TARGET=dev` (controls the dbt CLI target, defaults to `prod` otherwise) AND `unset MOTHERDUCK_TOKEN` (controls `resources/warehouse.py::connect_warehouse()`'s dev/prod pick independently) — the two are NOT tied together in code, easy to get half-right.

**Smoke-tested before committing to the ~2h run:** `document_exclusions` alone (confirmed it reads the LATEST existing raw R2 snapshot via `glob(...) ORDER BY file DESC`, not a today-scoped path, so it correctly skipped a fresh OpenAlex/PatentsView pull — 127 papers excluded, in the historical ~118-127 ballpark); then a 2-model dbt subset to confirm dagster-dbt's documented `context=context` passthrough really does auto-translate a Dagster asset-key selection into a scoped `dbt build --select <fqns>` (confirmed via the logged command) rather than silently running the whole 23-model project unfiltered every time either `@dbt_assets` op fires.

**First full run FAILED** after ~50 min, but only one step: `npl_links_raw` lost a race for `dev.duckdb`. Root cause: once `paper_to_patent_dbt_pre` finished, Dagster's multiprocess executor correctly launched `document_embeddings`, `mf_npl_links`, and `npl_links_raw` CONCURRENTLY (no data dependency between them — that's the acyclic graph working as designed). But local DuckDB permits ONE writer XOR multiple readers, never a mix. `npl_links_raw` opens `connect_warehouse(read_only=False)` (it writes `ref_npl_gold_eval`); `mf_npl_links` grabbed a read-only handle a few seconds earlier, and `npl_links_raw`'s exclusive-mode open failed outright with `_duckdb.IOException: ... file already open in another process`. **This bug was structurally impossible to hit before the refactor** — these three assets had no real Dagster `deps` before (only docstring-level "depends on ... in dev.duckdb" claims), so the user always ran them as separate, manually-sequenced CLI invocations, one at a time. Making the graph honestly acyclic is exactly what let Dagster parallelize them for the first time — and exposed the latent single-writer limitation of a local DuckDB file (MotherDuck/prod is a proper concurrent-connection service and wouldn't hit this).

**Good news buried in the failure:** everything else in that first run succeeded — `document_embeddings` (176,759 docs, 38 min), and `document_clusters` correctly detected **the exact same corpus_signature as the pre-refactor frozen clustering** and reused it (skip, no re-cluster) — strong, independent, live confirmation that the new `document_exclusions` asset (reading raw, upstream of staging) produces a byte-for-byte identical exclusion set to the old in-embedding gate it replaced. `cluster_labels` also completed (227 fresh Haiku calls, real cost already spent).

**Fix:** explicit "resource-serialization" deps chaining `mf_npl_links -> npl_links_raw -> document_embeddings` (already `-> document_clusters -> cluster_labels`), each edge commented in code as NOT a data dependency (so a future reader doesn't mistake it for real lineage and delete it). Committed separately as `fix(pipeline): serialize dev.duckdb-touching Python assets to avoid a local-file race` (2d9aedc), after `da93214`/`7575dc4`.

**Recovery avoided re-paying the sunk cost.** The wall clock crossed midnight mid-run, and `document_exclusions`/`org_crosswalk`/`mf_npl_links`/`document_embeddings`/`cluster_labels` all gate idempotency on `datetime.date.today()` — a blind rerun of the same full selector would have silently redone the 38-min embedding pass and re-billed Haiku for labels that were already correct and unchanged, purely because the date rolled over. Instead: selected exactly the two things still outstanding — `npl_links_raw` + the 11 individual `dbt_post` model asset keys (had to look up `marts/idea_journey`'s actual key by hand; a naive guess of `queries/idea_journey` silently resolved to nothing since dagster-dbt keys by dbt schema, not by the models/ subdirectory on disk). Recovery run: 4m39s total, `npl_links_raw` succeeded alone (no concurrent asset this time), `dbt_post` → PASS=114 ERROR=0.

**Live data verification (queried `dev.duckdb` directly, not just "tests passed"):** `dim_paper`/`dim_patent` = 153,362/23,397 with **zero orphans** against the bridge `fact_document_cluster` on both sides (the number that actually matters for this refactor — confirms dropping `cluster_id` from the dims and routing everything through the bridge didn't silently drop or orphan a single document). `fact_document_cluster` = 176,759 rows / 228 clusters (227 + noise) / 72,573 noise — matches the frozen clustering exactly. `fact_npl_link` = 9,025 (7,032 marx_fuegi + 480 doi + 1,513 fuzzy_title). `mart_family` and `seed_cluster_family` cluster counts agree exactly (25/125/58/19 across the 4 buckets), confirming the bridge-routed paper votes replaced the old `dim_paper.cluster_id` denormalization without changing behavior.

**Still open:** prod (MotherDuck) still not rebuilt from this refactor — `dev.duckdb` is now ahead of it. Promote when ready via a real `dagster asset materialize -m nexus` with `DBT_TARGET` unset/`prod` and `MOTHERDUCK_TOKEN` set (the concurrency fix applies identically there, just shouldn't ever trigger in practice since MotherDuck allows real concurrent connections).

---

## UI analytics-integrity review: 8 critical/moderate + 3 minor findings closed (2026-07-12)

Full analytics-quality audit of the Streamlit atlas (`apps/ui/`). Every fix shipped with a fixture test and same-commit doc updates. **PR #11 = the 8 critical/moderate (squash-merged `c674b77`); PR #12 = the minor cleanup (branch `fix/minor-findings-cleanup`, open).** The CI-cleanup commit (`fix(ci): clear pre-existing ruff/pyright`) is not itself a finding, just the unblock.

**Critical (wrong numbers, hard-rule, or metric misuse):**
1. **Family counts ran on the wrong grain.** Every family number used `seed_cluster_family` (3-way cluster *label*) instead of each document's own 5-way `family_id` — undercounted all families and produced a live, visible contradiction (TSMC metric card = 844 patents while the filing-year chart below it summed to 1,575). Rebuilt `mart_family`/`mart_competitive` on the doc-level grain; the Map deliberately stays 3-way (a cluster ≠ one family). Both paths now read 1,575.
2. **`patent_share` overclaimed.** Was `n_patents/(n_patents+n_papers)`, described as "research captured as US patents" — a causal claim the data doesn't support. Redefined as a family's share of the *total US patent pool* (papers out of the formula); rewrote the front-door + tour copy.
3. **Confidence/match-method never surfaced (hard-rule-3 violation).** `confidence_badge()`/`method_badge()` were fully built but uncalled, so a `fuzzy_title` link rendered identically to a gold Marx & Fuegi one. Wired badges into Org + Trace pages (solid vs hollow markers by confidence).
4. **Velocity "still-pending" shading used citation lag** — a metric with no link to USPTO grant time; it under-shaded every family (missed neuromorphic's real 49% 2021 filing drop). Added `mart_family.avg_grant_lag_years` and shaded on real grant lag. This is the change that **amended CLAUDE.md rule 2** to allow grant lag as a narrow, separately-labelled data-completeness diagnostic.

**Moderate (disclosure / honesty gaps):**
5. Dead "Frontier / Unclustered" map chip (unreachable — `load_cluster_bubble` already excludes `c_noise`) removed; the real ~41% HDBSCAN noise share now disclosed in a footer.
6. NPL link count now shown alongside every headline citation-lag number (lag was a narrow 2.5–3.3 yr but the evidence behind each ranged 448–2,963 links — presented as equally solid before).
7. Tour step-3 copy promised HHI in the Family Deepdive metrics strip, where it has never appeared; re-attributed to the cluster table.
8. Hybrid NPL linkage + its lower-bound basis disclosed in the methodology footer.

**Minor (PR #12):**
- Removed the `idea_journey` dbt view — an unused cartesian-product bug (independent LEFT JOINs on org → ~19.5M rows from ~9K real NPL links). 0 UI callers.
- Surfaced cluster `top_terms` (the c-TF-IDF evidence the Haiku tagline/summary were written from) in the Map cluster card and as the far-right column of the Family Deepdive cluster table.
- **Skipped, with rationale:** normalizing USPTO all-caps org display names. 90% of all-caps names (799/887) come from `native_id` matches (real legal records); the cure breaks true acronyms (ASML, TSMC, IBM) — worse than the symptom.

**One correction made after the fact:** an early write-up framed the NPL matcher's 0.32 recall as *the* linkage weakness. It isn't — post-hybrid, ~78% of `fact_npl_link` edges (7,032/9,025) come straight from Marx & Fuegi gold; the 0.32 is our own matcher's standalone recall and now governs only the recent-grant tail M&F can't reach. "Lower bound" still holds; "recall ≈ 0.32 across the whole linkage" does not.

---

## Family Deepdive cluster table: existence-based membership + family-scoped metrics + Other Families column, nav reorder (2026-07-14)

**Bug 1 (fixed then reverted, correct fix landed on the second pass):** the sidebar cluster filter on Family Deepdive was existence-based (`load_family_clusters` returned any cluster with >=1 doc of the selected family), so a cluster that's 96% Neuromorphic (e.g. `c_77`, "Machine Learning Signal Processing Systems") still showed up under the EUV pill for its 2% stray EUV patents. First attempt changed membership to plurality-vote (cluster's dominant family only) — user rejected this: existence-based is the wanted behavior, a cluster genuinely can belong to more than one family's view. **Real bug was elsewhere:** the bottom table's Papers/Patents/Lag/HHI columns pulled whole-cluster totals from `mart_gap` regardless of which family pill was active, while the top metric cards did a real family+cluster intersection — so selecting `c_77` under EUV showed 33 patents/14 papers up top but 1,564/47 in the table row for the same cluster. Fixed by rewriting `load_family_clusters` to compute every metric column live, scoped to (family, cluster) — same HHI/NPL-lag methodology and reportability floors as `mart_gap`, just filtered by `family_id` first. Verified: `load_family_clusters('euv')` row for `c_77` now equals `load_family_metrics('euv', cluster_ids=('c_77',))` exactly. Regression test encodes this equality directly, not just the individual numbers.

**New column: "Other Families".** Lists every other (of the 5) family with >=1 doc in that cluster, ordered by doc count — lets a reader see where the rest of a spillover cluster's documents actually live (e.g. `c_77` under EUV shows "Neuromorphic, In-Memory Compute, Lasers, Silicon Photonics"). Computed live in the same query via an unfiltered per-cluster family vote, joined back in. Implementation gotcha: `pl.col(...).map_elements()` on a `List`-dtype column passes each row as a `polars.Series`, not a plain list (`if not ids` raises "truth value of a Series is ambiguous") — and separately, `map_elements` skips calling the function on null rows entirely (returns null straight through), so the "pure cluster, no spillover" case needed `.fill_null("—")` chained after `map_elements`, not just an in-function `None` check.

**Nav reorder:** swapped Family Deepdive before Technology Landscape (user judged it the more logical entry point). Renamed `1_Map.py`→`2_Map.py` and `2_Family.py`→`1_Family.py` via `git mv` (worked fine despite uncommitted in-flight edits on both files). The tab strip order lives in `render.py::render_nav`'s `_tabs` list — independent of file-prefix numbers, since links are hrefs (`/Map`, `/Family`), not `st.page_link` — but the hidden native Streamlit sidebar nav and `TOUR_STEPS` order (`tour.py`) both DO depend on file naming/list order, so both needed updating too: swapped the two `TourStep` entries and their `page_file` paths, and each page's `render_tour_banner(N)` call (Family is now step 1, Map step 2). `render_nav`'s `_nav_labels` list (used to resolve the tour's return page) updated to match.

---

## Part 8 — Documentation, deploy, portfolio integration ✅ COMPLETE (2026-07-15)

**The app is live and public**: https://paper-to-patent-a7iiegantbeucyxxwegpyz.streamlit.app/ (deployed
2026-07-14, Streamlit Community Cloud, from `main`, entrypoint `apps/ui/app.py`). dbt docs are live at
https://rm3006.github.io/paper-to-patent/. Repo was already public — Part 0's "flip to public in Part 8"
had been done earlier.

**`apps/ui/requirements.txt` is a SECOND, independent dependency manifest — and it was missing a dep that
would have crashed the first deploy.** `streamlit-searchbox` is imported in 3 UI files
(`render.py`, `pages/3_Org.py`, `pages/4_Trace.py`) and pinned in `pyproject.toml`, but was absent from
`apps/ui/requirements.txt`. **Streamlit Community Cloud builds its container from `requirements.txt`, not
`pyproject.toml`** — so local runs (which use the uv env) were fine and CI was green, while the very first
cloud deploy would have died on import. Found by grepping every runtime import in `apps/ui/` against the
file rather than trusting either manifest. **Rule: any new UI dependency must be added in BOTH
`pyproject.toml` and `apps/ui/requirements.txt`.** Nothing enforces this — no test, no CI check covers it.

**`int_organization_crosswalk` never existed — the real model is `int_org_crosswalk`.** The wrong name was
in 12 places across 9 files, including **CLAUDE.md hard rule #1**, ARCHITECTURE.md (×2), ROADMAP.md (×2),
the data manifest, ui_story, workflow.md, this file, and 3 docstrings in `assemble.py`. Every one of them
had been copied forward from a name that was never real. Caught only by running a live query
(`main_intermediate.int_organization_crosswalk` → `CatalogException: Did you mean "int_org_crosswalk"?`)
while trying to verify the crosswalk row count. **Lesson: a name repeated across nine documents is not
evidence it exists — the warehouse is the only authority.** Fixed everywhere 2026-07-15.

**The "prod (MotherDuck) still NOT rebuilt" notes above (2026-07-10 / 07-11 / 07-12) are SUPERSEDED — do not
act on them.** They were true when written, but `dbt-docs.yml`'s `deploy-prod` job rebuilds prod on every
push to `main` touching `models/**`, so the PR merges (#9/#11/#12/#13/#15) each promoted prod automatically.
Verified live 2026-07-14: prod carries the 5-way `mart_family` with `avg_grant_lag_years`, `mart_competitive`
with `family_id`/`family_id_key`, `seed_cluster_family` with `mixed` (not `adjacent`), and matching corpus
counts (153,362 papers / 23,397 patents / 228 clusters / 9,025 NPL links). **The generalizable lesson: once
an automation starts doing a manual step, the memory notes tracking that manual step silently rot.** Check
the live system before believing a "still pending" note.

**`dbt-docs.yml` couples prod promotion to docs publishing — including for pure doc edits.** One workflow,
three sequential jobs: `deploy-prod` (`dbt build --target prod` → rebuilds the live MotherDuck warehouse the
app reads) → `docs-build` (`dbt docs generate --target prod`) → `deploy` (GitHub Pages). It fires on push to
`main` under `models/**`. **Consequence worth knowing: editing only a comment in `models/**/_schema.yml` or
`_docs.md` triggers a full production warehouse rebuild.** Cheap (~3 min, warehouse fully derived from R2)
and deliberate, but surprising. Changes outside `models/**` (e.g. README, `apps/ui/`) do not trigger it at all.

**`findings.md`'s family table had gone stale against its own mart.** PR #11 (2026-07-12) rebuilt `mart_family`
onto the 5-way document-level `family_id` grain and redefined `patent_share` as a share of the total US patent
pool — but `findings.md` still carried the old 3-way + Mixed table and the old
`n_pat/(n_pat+n_pap)` definition. The cluster-level Findings 1–4 were fine (they read `mart_gap`, whose
formulas and frozen clustering hadn't changed — re-verified live, all four still hold, only a cosmetic Haiku
tagline drift on `c_147`). Rebuilt the family table from live prod. Note the "Top assignee" column is **not** a
`mart_family` column — it has to be derived from `fact_patent_filing` ⋈ `dim_organization`. Detecting the
`patent_share` redefinition was easy from the data itself: the 5 shares now sum to ~1.0.

**Streamlit Community Cloud serves the app inside an iframe — browser automation needs frame-aware locators.**
The real app lives at `<app-url>/~/+/`, not the top-level page, so `page.waitForSelector('[data-testid=
"stAppViewContainer"]')` against the top frame times out even though the app renders perfectly. Use
`page.frames().find(f => f.url().includes('/~/+/'))`. Two follow-on gotchas: (1) the nav tabs are plain
`<a href>` anchors, so clicking one does a **full browser navigation that detaches the frame handle** — it must
be re-acquired after every tab click; (2) `page.title()` on the *top* frame does work and returns
`"The Chips Behind AI · Streamlit"`, which is what `ping-app.yml`'s liveness check relies on.

**Known cosmetic issue, accepted not fixed: two console 404s per page navigation.** Every tab click emits
`404 /<Page>/_stcore/health` and `/<Page>/_stcore/host-config`. Cause: `render_nav`'s tab links are plain
anchors → full reload onto a sub-path → Streamlit's frontend resolves its own internal health-check calls
relative to that sub-path instead of the app root. Invisible to users, no functional impact, reproduced on
both local and live. Left alone deliberately (plain anchors vs `st.page_link` is a design choice, not a
regression).

**Added the sibling project's two liveness workflows (ported from `human-protein-atlas`, 2026-07-15):**
`keep-app-alive.yml` (10-hourly) + its reusable `ping-app.yml`, and `repo-heartbeat.yml` (daily). They are a
**matched pair, and the dependency runs the non-obvious way**: Streamlit Cloud sleeps idle apps and only counts
real WebSocket sessions (an HTTP ping does *not* reset the timer — hence headless Chromium), while GitHub
disables scheduled workflows after 60 days of no pushes, which would silently kill the keep-alive cron. The
heartbeat exists to protect the keep-alive. Its `[skip ci]` commit message matters here: `ci.yml` triggers on
an unfiltered `push:`, so without it every heartbeat commit would fire a full CI run. Scheduled workflows only
run from the **default branch**, so these are inert until merged to `main`.

**Embedding the app in a third-party iframe needs the embed flag re-attached to every link (fixed
2026-07-15).** `?embed=true` tells Community Cloud to skip its login/host wrapper. `render_nav`'s plain
anchors navigate to bare sub-paths (`/Family`), dropping it — the frame then lands on the *non-embed* host
page, whose login redirect cannot complete cross-site (browsers withhold the `SameSite=Lax` session cookie
from a third-party frame), so it bounces `/Family → app?redirect_uri= → login?payload=` until
`ERR_TOO_MANY_REDIRECTS`. **Only reproduces embedded**; standalone the same redirect resolves against
first-party cookies, which is why the live app never showed it. Fix: `render.embed_url()` re-attaches the
flags at all five anchors (nav tabs, Overview "Explore family", both family pills, Family→Map). Streamlit
**reserves `embed` and withholds it from `st.query_params`**, so the app cannot detect its own embed state —
hence the companion non-reserved `e=1`, which it *can* read. **The iframe src must therefore be
`?embed=true&e=1`, not `?embed=true`** (documented in `SETUP.md` F2).

This is the **same root cause as the accepted 404s above**, so "plain anchors vs `st.page_link` is a design
choice, not a regression" is now only half true: the anchors have a functional cost, not just a cosmetic one.
`st.navigation` + `st.Page` + `st.page_link` (all present on the pinned Streamlit 1.58, and `page_link` /
`switch_page` both take `query_params`, so the pills' `?family=` survives) would delete the bug class *and*
the full-reload lag on every tab click. Deliberately **not** bundled into this fix — it restructures the
entrypoint and all 5 pages on a live app, and the 20-line patch unblocks the iframe today. Left unverified:
whether `st.page_link` keeps the flags in the address bar, which decides whether a mid-session refresh inside
the frame survives — the one place the anchor approach is *stronger*, since the flags stay in the URL.
Sibling `human-protein-atlas` is not a usable template here: it is smooth because it never navigates (one
1296-line `app.py`, no `pages/`, `st.tabs` as a widget), and `st.tabs` executes *every* tab body per run —
fine for its four tabs rendering one cached `card`, wrong for 5 pages each querying different marts.

**Part 8 descope (user decision):** the portfolio showcase card and the ~300-word LinkedIn writeup were
**cancelled, not deferred** — documentation + deploy shipped, distribution did not. Two exit criteria were
removed rather than left as permanently-unmeetable boxes (the portfolio/writeup one, and the README's
two-person cold-read test, which can't be self-certified). Recorded in `ROADMAP.md`'s Part 8 descope note.
The og:image was also skipped: Streamlit Cloud injects its own social card and a custom one needs a fragile
`<head>` meta hack.
