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
