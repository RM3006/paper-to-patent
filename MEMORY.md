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
