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
- `org_crosswalk` asset (assemble.py): long-format `int_organization_crosswalk` (source, source_id, org_id, canonical_name, match_method, confidence). Seed org_ids inherited by OA side via fuzzy bridge; fallback org_ids generated as `org_pv_*` / `org_oa_*`. 15 tests.
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
