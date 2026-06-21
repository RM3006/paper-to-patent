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
- R2 currently empty — rate-limited mid re-ingest on the 2025-cutoff run. Re-ingest pending after cooldown clears (~02:00 CEST 2026-06-22).
- PR open: `feat/part-1-foundation-openalex` → `main`.
