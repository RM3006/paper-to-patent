# Data Source Manifest — Paper → Patent

The reference for **what each source provides, what each column means, and the confirmed scope row counts**. Started as a Part 0 stub (scope counts + R2 secret syntax + licenses); the per-table column dictionaries are filled in as Parts 2 and 4 land their schemas.

**Snapshot date of the counts below:** `2026-06-20` (PatentsView bulk grant data + Marx & Fuegi `_pcs_oa.csv` + OpenAlex live `/works`).

---

## 1. Scope contract (mirror of `ROADMAP.md` Part 0)

Theme: **"The Chips Behind AI"** — three science-adjacent microchip sub-families.

| Family | Patent CPC codes (prefix match) | OpenAlex topic ID(s) |
|---|---|---|
| EUV Lithography | `G03F7/20`, `G03F7/70` | `T11338` "Advancements in Photolithography Techniques" |
| Silicon Photonics | `G02B6/12`, `G02B6/122`, `H01S5/0224`, `H01S5/10` | `T10299` "Photonic and Optical Devices", `T11429` "Semiconductor Lasers and Optical Devices" |
| Neuromorphic & In-Memory Compute | `G06N3/049`, `G11C11/54`, `G11C13/00`, `H10N70/00` | `T10502` "Advanced Memory and Neural Computing" |

**Year windows:** papers (OpenAlex `publication_date`) **2012–2025**; patents (PatentsView `filing_date`) **2014–2025**.

**Topic-ID verification (2026-06-20):** the four scope topic IDs above resolve live and match the ROADMAP table — no update required. Several descriptive search terms collapse onto the same four canonical topics (e.g. "Memristors", "In-Memory Computing", "Spiking Neural Networks" all resolve to `T10502`); the search terms "EUV photomask / pellicle" and "Plasma-based EUV light source" return no dedicated topic and are covered by `T11338`.

---

## 2. Part 0 NPL feasibility spike — recorded counts

Produced by `notebooks/part0_npl_spike.py` and `notebooks/part0_openalex_count.py`.

> **Important caveat — these are CPC-only counts, with NO filing-date filter applied.**
> `g_patent.tsv` carries the grant date only; the `filing_date` filter (2014–2025) requires `g_application.tsv` and is applied in **Part 2**, not in the spike. The Part 2 `patents_scoped` corpus will therefore be **smaller** than the 68,800 below — the ROADMAP Part 2 "within 5% of the spike count" check must compare against a *re-run of this CPC filter*, not against the date-filtered corpus.

### Patent side (PatentsView bulk, all grant years)

| Metric | Value | Kill criterion | Status |
|---|---|---|---|
| Scope patents (CPC match, no date filter) | **68,800** | ≥ 5,000 | ✅ |
| NPL reference rows for scope patents | **656,347** | ≥ 2,000 | ✅ |
| Scope patents with ≥1 NPL reference | 47,300 | — | — |

### NPL gold eval (Marx & Fuegi `_pcs_oa.csv`, joined to scope patents)

| Metric | Value | Kill criterion | Status |
|---|---|---|---|
| Gold pairs in scope (total) | **291,378** | ≥ 300 | ✅ |
| Distinct OpenAlex papers in gold pairs | 92,585 | — | — |

### Per-family breakdown

| Family | Scope patents | NPL refs | MF gold pairs | ≥ 50 pairs? |
|---|---|---|---|---|
| EUV Lithography | 30,253 | 199,298 | 62,946 | ✅ |
| Silicon Photonics | 14,982 | 139,782 | 86,816 | ✅ |
| Neuromorphic & In-Memory Compute | 23,709 | 318,917 | 143,037 | ✅ |

### Paper side (OpenAlex live `/works`)

| Metric | Value | Kill criterion | Status |
|---|---|---|---|
| Works in scope (4 topics, 2012–2025, `language:en`, `has_abstract:true`) | **164,072** *(verified 2026-06-22 after 2025 extension re-ingest)* | ≥ 10,000 | ✅ |

**Verdict: all six kill criteria pass with wide margins. No family dropped; no CPC widening required. Part 0 feasibility confirmed.**

---

## 3. DuckDB → R2 access (canonical secret syntax)

DuckDB reads/writes R2 Parquet via `httpfs`. Configure the secret **once** in the shared helper (`pipelines/nexus/resources/duckdb.py`); never re-declare credentials per query (per `CLAUDE.md`). Verified working in `notebooks/part0_r2_check.py` (write + read round-trip against `r2://p2p-lake/`).

```sql
CREATE OR REPLACE SECRET r2 (
    TYPE r2,
    ACCOUNT_ID '<CLOUDFLARE_ACCOUNT_ID>',
    KEY_ID     '<CLOUDFLARE_R2_ACCESS_KEY_ID>',
    SECRET     '<CLOUDFLARE_R2_SECRET_ACCESS_KEY>'
);
-- then address objects as: r2://p2p-lake/<path>
SELECT * FROM read_parquet('r2://p2p-lake/raw/...');
```

The build machine uses the **read-write** R2 key and a read-write MotherDuck token; the Streamlit app uses a separate **read-only** MotherDuck token (least privilege). Credentials come from `.env.local` / Streamlit secrets — never hardcoded.

---

## 4. Sources & licenses

| Source | Role | Access | License |
|---|---|---|---|
| PatentsView bulk TSV (data.uspto.gov) | Primary US patent data (filings, assignees, CPC, citations, NPL "other references") | bulk download, no key | CC-BY-4.0 |
| PatentSearch API (`search.patentsview.org`) | Supplementary targeted lookups only | `X-Api-Key` header (optional) | CC-BY-4.0 |
| OpenAlex (`api.openalex.org`) | Global research output (abstracts, institutions/ROR, topics) | polite pool via `mailto` | CC0 |
| Marx & Fuegi "Reliance on Science" `_pcs_oa.csv` (Zenodo 8278104) | NPL gold eval set (quality benchmark only, never pipeline output) | free download | CC-BY-4.0 |

**Files used in the Part 0 spike** (gitignored under `data/`): `g_patent.tsv`, `g_cpc_current.tsv`, `g_other_reference.tsv`, `data/reference/marx_fuegi_pcs.csv`. `g_application.tsv` (filing dates) and `g_assignee_disambiguated.tsv` are already downloaded for Part 2.

---

## 5. Part 2 row-count verification queries

Run these after materializing the PatentsView assets to verify counts. The DuckDB R2 secret must be configured (see section 3).

```sql
-- Raw entity row counts (full corpus, no scope filter)
SELECT 'patents'      AS entity, COUNT(*) AS rows FROM read_parquet('r2://p2p-lake/raw/patentsview/patents/*/*.parquet')
UNION ALL
SELECT 'applications',           COUNT(*)         FROM read_parquet('r2://p2p-lake/raw/patentsview/applications/*/*.parquet')
UNION ALL
SELECT 'assignees',              COUNT(*)         FROM read_parquet('r2://p2p-lake/raw/patentsview/assignees/*/*.parquet')
UNION ALL
SELECT 'cpc',                    COUNT(*)         FROM read_parquet('r2://p2p-lake/raw/patentsview/cpc/*/*.parquet')
UNION ALL
SELECT 'npl',                    COUNT(*)         FROM read_parquet('r2://p2p-lake/raw/patentsview/npl/*/*.parquet')
UNION ALL
SELECT 'citations',              COUNT(*)         FROM read_parquet('r2://p2p-lake/raw/patentsview/citations/*/*.parquet');

-- Scoped patent count — must be within 5% of 68,800 (Part 0 CPC-only spike, no date filter).
-- The date filter (2014–2025) will produce a smaller number; this is expected.
SELECT COUNT(*) AS scoped_patents FROM read_parquet('r2://p2p-lake/raw/patentsview/patents_scoped/*/*.parquet');

-- NPL references for scoped patents — must be non-empty (exit criterion)
SELECT COUNT(*) AS scoped_npl_refs
FROM read_parquet('r2://p2p-lake/raw/patentsview/npl/*/*.parquet') npl
JOIN read_parquet('r2://p2p-lake/raw/patentsview/patents_scoped/*/*.parquet') s
  ON npl.patent_id = s.patent_id;

-- Sample NPL strings — confirm parseable (DOIs, titles, journal refs)
SELECT other_reference_text
FROM read_parquet('r2://p2p-lake/raw/patentsview/npl/*/*.parquet') npl
JOIN read_parquet('r2://p2p-lake/raw/patentsview/patents_scoped/*/*.parquet') s
  ON npl.patent_id = s.patent_id
LIMIT 20;
```

> **Part 0 reference counts** (CPC-only, no filing-date filter): 68,800 patents · 656,347 NPL refs.
> The `patents_scoped` count is smaller due to the 2014–2025 filing-date filter — expected and correct.

**Verified 2026-06-21 (snapshot v2026-06-21):**

| Entity | Actual rows | Notes |
|---|---|---|
| `patents` (full) | 9,454,161 | All US granted patents |
| `applications` (full) | 9,451,902 | One row per patent; no duplicates |
| `assignees` (full) | 8,751,310 | Disambiguated; includes multi-assignee rows |
| `cpc` (full) | 59,805,669 | Multiple CPC codes per patent |
| `npl` (full) | 65,161,274 | All NPL "other reference" strings |
| `citations` (full) | 152,631,929 | Patent-to-patent citation edges |
| `inventors` (full) | 24,037,380 | Disambiguated inventor rows |
| **`patents_scoped`** | **33,578** | CPC match + filing_date 2014–2025 |
| CPC-only scope count (no date) | 68,800 | Matches Part 0 spike exactly (0% drift) |
| Scoped NPL refs | 365,932 | Non-empty; parseable DOIs, titles, journal refs ✅ |

---

## 6. Column dictionary

### PatentsView raw tables (Part 2)

**`g_patent`** — core patent metadata (R2: `raw/patentsview/patents/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | USPTO patent number — may be numeric (`9999999`) or prefixed (`D123456` design, `RE12345` reissue, `PP12345` plant). Always String. |
| `patent_type` | String | `utility`, `design`, `plant`, `reissue`, `defensive_publication` |
| `patent_date` | String | Grant date (YYYY-MM-DD). **Never used for time metrics** — grant date carries years of administrative lag. Metadata only. |
| `patent_title` | String | Title as granted |
| `wipo_kind` | String | WIPO kind code (B1, B2, etc.) |
| `num_claims` | Int64 | Number of claims |
| `withdrawn` | Int64 | 1 if the patent was withdrawn |

**`g_application`** — application / filing metadata (R2: `raw/patentsview/applications/`)

| Column | Type | Meaning |
|---|---|---|
| `application_id` | String | USPTO application serial number |
| `patent_id` | String | Links to `g_patent.patent_id`. One row per patent (no duplicates confirmed). |
| `patent_application_type` | String | Application type code |
| `filing_date` | String | **The time-metric anchor** (YYYY-MM-DD). Used for `citation lag = publication_date → filing_date`. |
| `series_code` | String | Application series code |
| `rule_47_flag` | Int64 | 37 CFR 1.47 flag |

**`g_assignee_disambiguated`** — disambiguated patent assignees (R2: `raw/patentsview/assignees/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Links to `g_patent.patent_id` |
| `assignee_sequence` | Int64 | Order among co-assignees (0-indexed) |
| `assignee_id` | String | Disambiguated assignee UUID — the patent-side identity for entity resolution (Part 3) |
| `disambig_assignee_organization` | String | Disambiguated organisation name (nullable if individual inventor) |
| `disambig_assignee_individual_name_first` | String | First name if individual assignee |
| `disambig_assignee_individual_name_last` | String | Last name if individual assignee |
| `assignee_type` | String | `2`=US company, `3`=foreign company, `4`=US individual, `5`=foreign individual, `6`=US government, `7`=foreign government |
| `location_id` | String | Location UUID |

**`g_cpc_current`** — CPC classification assignments (R2: `raw/patentsview/cpc/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Links to `g_patent.patent_id`. Multiple rows per patent (one per CPC code). |
| `cpc_sequence` | Int64 | Order among CPC codes for this patent |
| `cpc_section` | String | Top-level section (e.g. `G`) |
| `cpc_class` | String | Class (e.g. `G03`) |
| `cpc_subclass` | String | Subclass (e.g. `G03F`) |
| `cpc_group` | String | Full group code (e.g. `G03F7/2004`). **Scope filter uses prefix match on this column.** |
| `cpc_type` | String | `inventional` or `additional` |

**`g_other_reference`** — non-patent literature citations (R2: `raw/patentsview/npl/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Links to `g_patent.patent_id` |
| `other_reference_sequence` | Int64 | Order among NPL references for this patent |
| `other_reference_text` | String | Free-text citation string. May contain DOI, title, author, journal, URL. **Raw input for the Part 4 NPL matcher.** |

**`g_us_patent_citation`** — patent-to-patent citation edges (R2: `raw/patentsview/citations/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Citing patent |
| `citation_patent_id` | String | Cited patent. Always String (may be prefixed). |
| _(remaining columns)_ | — | Sequence, category, citation date — schema to be confirmed on first use in Part 6 |

**`g_inventor_disambiguated`** — inventor metadata (R2: `raw/patentsview/inventors/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Links to `g_patent.patent_id` |
| `inventor_id` | String | Disambiguated inventor UUID. Person-level ER is out of scope for v1. |
| _(remaining columns)_ | — | Name, location, sequence — metadata only until v2 |

**`patents_scoped`** — scope-filtered corpus (R2: `raw/patentsview/patents_scoped/`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Scope-matched patent. All downstream assets join against this set. |
| `patent_title` | String | Title as granted |
| `patent_date` | String | Grant date — metadata only |
| `patent_type` | String | Patent type |
| `filing_date` | String | **Filing date from `g_application`** — the time-metric anchor for citation lag |

> Scope filter: CPC prefix match on the 10 codes in the scope contract + `filing_date` 2014–2025. See `pipelines/nexus/assets/ingest/patentsview.py::SCOPE_CPC_PREFIXES`.

> **Patent abstracts note (Part 5):** `g_patent.tsv` does not ship abstract text — it contains only `patent_id`, `patent_type`, `patent_date`, `patent_title`, `wipo_kind`, `num_claims`, `withdrawn`. The Part 5 embedding asset therefore uses `title` (from `dim_patent`) as the text source for patents, and `abstract` (from `dim_paper`) for papers. Patent titles in this corpus are descriptive enough for domain clustering; both sources share the same embedding model (`all-MiniLM-L6-v2`).

---

### OpenAlex raw schema (Part 1 / Part 4 — stub)

`works` raw Parquet at `r2://p2p-lake/raw/openalex/v{snapshot_date}/works.parquet`. Key columns (full column dictionary deferred to Part 4 when dbt staging models are built):

| Column | Type | Meaning |
|---|---|---|
| `openalex_id` | String | OpenAlex work URL (e.g. `https://openalex.org/W…`) |
| `doi` | String | DOI URL — primary join key for NPL matcher (Part 4) |
| `title` | String | Paper title |
| `publication_date` | String | Publication date (YYYY-MM-DD) — **time-metric anchor** for citation lag |
| `publication_year` | Int64 | Year (redundant with date; kept for fast filtering) |
| `language` | String | Language code (`en` only in scope) |
| `abstract` | String | Reconstructed from `abstract_inverted_index`; NULL if absent |
| `primary_topic_id` | String | OpenAlex topic URL (one of the 4 scope topic IDs) |
| `primary_topic_name` | String | Human-readable topic name |
| `institution_ids` | List[String] | OpenAlex institution URLs from all authorships |
| `institution_rors` | List[String] | ROR URLs from all authorships — paper-side identity for ER (Part 3) |
| `institution_display_names` | List[String] | Institution display names from all authorships — used in `openalex_institutions_staging` (Part 3) |

---

### Entity resolution intermediate tables (Part 3)

**`patentsview_orgs_staging`** — deduped PatentsView assignees in scope (R2: `intermediate/er/patentsview_orgs_staging/`)

| Column | Type | Meaning |
|---|---|---|
| `assignee_id` | String | PatentsView disambiguated assignee UUID — patent-side identity |
| `display_name` | String | Original disambiguated organisation name |
| `normalized_name` | String | Lower-cased, legal-suffix-stripped, punctuation-cleaned name (see `normalize_org_name()`) |
| `match_method` | String | Always `native_id` — within-source disambiguation, no cross-source link yet |
| `confidence` | String | Always `high` |

**`openalex_institutions_staging`** — deduped OA institutions from scoped works (R2: `intermediate/er/openalex_institutions_staging/`)

| Column | Type | Meaning |
|---|---|---|
| `institution_id` | String | OpenAlex institution URL (e.g. `https://openalex.org/I…`) — paper-side identity |
| `display_name` | String | Original institution display name |
| `normalized_name` | String | Same normalizer as PV side |
| `match_method` | String | Always `ror` |
| `confidence` | String | Always `high` |

**`seed_crosswalk_matched`** — PV side of the seed crosswalk (R2: `intermediate/er/seed_crosswalk_matched/`)

| Column | Type | Meaning |
|---|---|---|
| `org_id` | String | Canonical identifier (slug, e.g. `org_tsmc`) |
| `canonical_name` | String | Human-readable name |
| `assignee_id` | String | Matched PV assignee UUID |
| `display_name` | String | PV display name |
| `match_method` | String | `seed_crosswalk` |
| `confidence` | String | `high` |

**`seed_crosswalk_oa_matched`** — OA side of the seed crosswalk, matched by `openalex_institution_id` (R2: `intermediate/er/seed_crosswalk_oa_matched/`)

| Column | Type | Meaning |
|---|---|---|
| `org_id` | String | Same `org_id` as the PV seed entry |
| `canonical_name` | String | Human-readable name |
| `institution_id` | String | Matched OA institution URL |
| `display_name` | String | OA display name |
| `match_method` | String | `seed_crosswalk` |
| `confidence` | String | `high` |

**`fuzzy_org_bridge`** — cross-source links via `rapidfuzz` token-set ratio = 100 (R2: `intermediate/er/fuzzy_org_bridge/`)

| Column | Type | Meaning |
|---|---|---|
| `institution_id` | String | OA institution URL |
| `assignee_id` | String | PV assignee UUID |
| `similarity` | Float64 | `token_set_ratio` score — always exactly 100.0 at the accepted threshold |
| `match_method` | String | `fuzzy_high` only (no `fuzzy_review` band at score=100 threshold) |
| `confidence` | String | `high` |

**`org_crosswalk`** — final `int_organization_crosswalk` (R2: `intermediate/er/org_crosswalk/`)

One row per (source, source_id). Every org in both sources gets exactly one row. Cross-source links share an `org_id`; unlinked orgs get a unique slug.

| Column | Type | Meaning |
|---|---|---|
| `org_id` | String | Canonical identifier. Prefix: `org_{slug}` (seed), `org_pv_{slug}` (PV-only), `org_oa_{slug}` (OA-only) |
| `source` | String | `patentsview` or `openalex` |
| `source_id` | String | `assignee_id` (PV) or `institution_id` (OA) |
| `canonical_name` | String | Human-readable name |
| `match_method` | String | One of: `native_id`, `seed_crosswalk`, `ror_bridge`, `fuzzy_high`, `ror` |
| `confidence` | String | `high` (medium / low not present — `fuzzy_review` band was eliminated) |

> **Verified 2026-06-22 (pre-ror_bridge):** 3,262 PV assignees · 12,936 OA institutions → 16,198 crosswalk rows · 14,209 distinct org_ids. Fuzzy bridge: 1,160 fuzzy_high, 0 fuzzy_review. Seed: 43 PV matches (34 org_ids) · 3 OA explicit-ID matches (Stanford, MIT, IMEC). Precision = 1.00 on eval set. See `docs/er_eval_set.md` for the full quality record. ROR bridge (added 2026-06-26) extends OA coverage for ~2,521 PV-only seeded orgs (IBM, Samsung Display, Micron, Carl Zeiss, SK Hynix, …).
>
> **Verified 2026-07-04 (current):** 16,215 crosswalk rows · 14,179 distinct org_ids. Match method breakdown: `ror` 11,743 · `native_id` 2,559 · `fuzzy_high` 1,818 · `seed_crosswalk` 57 · `ror_bridge` 38. (A source-view bug briefly caused this table to silently union two snapshots, 32,413 rows with the June-22 snapshot's rows exactly duplicated plus 32 institutions — mostly UC campuses and IBM/Toshiba labs — carrying two conflicting `org_id`s; fixed by making the source macro resolve to the latest snapshot only, see `MEMORY.md`.)
>
> **`fuzzy_high` = 1,818 crosswalk rows is not 1,818 distinct matches (resolved 2026-07-06):** the `fuzzy_org_bridge` asset has not been re-run since 2026-06-22 — it is still exactly 1,160 matched (institution_id, assignee_id) pairs, all still at score=100. The crosswalk's higher row count is `assemble.py` emitting **two** rows per pair (one OpenAlex-source row, one PatentsView-source row) when the PatentsView side isn't already in the seed crosswalk: 1,160 pairs + 661 non-seeded PV assignees among them ≈ 1,818 rows. No new fuzzy matches exist, so the 2026-06-22 precision=1.00 record in `docs/er_eval_set.md` still covers the entire live universe of matches — no re-measurement was needed. Full arithmetic and the units-mismatch diagnosis are in `docs/er_eval_set.md`'s 2026-07-06 record.

---

### NPL matcher (Part 4 — complete)

**Approach**: two-route matcher in `pipelines/nexus/assets/transform/npl_matcher.py`.

| Route | Mechanism | Confidence | Links |
|---|---|---|---|
| DOI | regex-extracted bare DOI (trailing punctuation stripped) → exact join on `doi_bare` | `high` | 1,107 |
| Fuzzy title | inverted-index candidate generation + `rapidfuzz.token_set_ratio` ≥ 90 | `medium` | 5,145 |
| **Total** | after deduplication on `(patent_id, work_id)` | — | **6,252** |

**Gold eval set** (`ref_npl_gold_eval` in `dev.duckdb`): Marx & Fuegi pairs filtered to scope patents (filing 2014–2025) **∩** OA corpus (163,890 works) → **8,640 measurable pairs**, 3,301 distinct patents.

**Precision/recall at threshold=90 (chosen threshold):**

| Threshold | Total links | Cond. precision* | Recall |
|---|---|---|---|
| 90 | 6,252 | **0.831** | 0.324 |
| 95 | 2,243 | 0.841 | 0.114 |
| 100 | 1,329 | 0.813 | 0.060 |

*Conditional precision: measured only over the 3,301 patents appearing in the gold set, to avoid penalising true links that the gold cannot confirm. Threshold=90 was the lowest achieving ≥ 0.80 conditional precision.

**Coverage note**: Marx & Fuegi is based on Microsoft Academic Graph (coverage ~2021). Our matcher extends coverage to 2025 via OpenAlex, producing links the gold set cannot confirm — this is a feature, not a gap. The DOI route operates at near-100% precision; the fuzzy route's 0.831 conditional precision is a conservative lower bound.

**`fact_npl_link`** — resolved paper↔patent edges (MotherDuck: `main_marts.fact_npl_link`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Citing patent (in scope) |
| `work_id` | String | Matched OpenAlex work ID (e.g. `W2741809807`) |
| `match_method` | String | `npl_citation` (DOI or fuzzy-title route) |
| `confidence` | String | `high` (DOI route) or `medium` (fuzzy-title route) |
| `doi_extracted` | String | Bare DOI if DOI route; NULL for fuzzy matches |
| `publication_date` | Date | Paper publication date — citation-lag anchor |
| `filing_date` | Date | Patent filing date — citation-lag anchor |
| `citation_lag_days` | Integer | Days from publication to filing |
| `citation_lag_years` | Float | Rounded to 2 decimal places; **never called "lead time"** |

> **Verified 2026-06-22**: 5,921 rows (after `publication_date < filing_date` filter in dbt), 2,973 distinct patents, 2,470 distinct works. Median citation lag ≈ 3.6 years. Top assignees by NPL links: GlobalFoundries (704), IBM (612), STMicroelectronics (177), ASML (99), MIT (95), Intel (95).
>
> **Verified 2026-07-04**: 5,749 rows (1,075 high/DOI + 4,674 medium/fuzzy), 2,896 distinct patents, 2,433 distinct works, median lag 3.13 years. Note: this reflects the *original* DOI/fuzzy-title matcher run intersected with the current (type-filtered, smaller) OpenAlex corpus via the inner joins in `fact_npl_link.sql` — the matcher itself (`npl_links_raw`) has not been re-run against the current corpus, so the precision/recall table above is not a fresh measurement. A re-run would be needed to confirm the 0.831 conditional precision still holds.

---

### ML pipeline intermediate tables (Part 5)

**`clusters`** — UMAP + HDBSCAN document assignments (R2: `intermediate/clusters/v{date}/clusters.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `doc_id` | String | OpenAlex `work_id` for papers; USPTO `patent_id` for patents |
| `doc_type` | String | `paper` or `patent` |
| `cluster_id` | String | Cluster identifier — `c_{label}` for named clusters, `c_noise` for HDBSCAN noise points |
| `umap_x` | Float32 | 2D UMAP x-coordinate for the technology map |
| `umap_y` | Float32 | 2D UMAP y-coordinate for the technology map |
| `model_version` | String | Embedding model used: `all-MiniLM-L6-v2` |

> Embedding model: `all-MiniLM-L6-v2` (384-dim, CPU, `normalize_embeddings=True`, max 256 tokens). Text source: paper `abstract` (from `dim_paper`) and patent `title` (from `dim_patent` — `g_patent.tsv` does not include abstract text). UMAP: `n_neighbors=15`, `min_dist=0.1`, `metric='cosine'`, `random_state=42`. HDBSCAN: `min_cluster_size=50`, `metric='euclidean'` (on 2D UMAP coords).
>
> **Embedding input quality gate (added 2026-07-04, `resolve_paper_text()` in `embeddings.py`):** before embedding, each paper is checked in order — (1) a version-style title ("libBigWig 0.1.5") excludes the document entirely, applied to patents too; (2) a placeholder abstract ("Abstract not provided.") or one under 50 characters falls back to the paper's title; (3) an abstract that `langdetect` detects as non-English falls back to title if the title itself is English, else excludes (OpenAlex's own `language` field was found unreliable — French/Italian/Catalan thesis abstracts were all tagged `en`); (4) otherwise the abstract is used as normal. Derived from inspecting three artifact clusters found by measuring cluster-family purity against each document's own CPC/topic tag.
>
> **Production run stats (2026-06-26, pre-quality-gate):** 197,456 docs embedded (22.9% truncated at 256 tokens); 303 named clusters produced; noise rate **42.1%** (83,182 docs).
>
> **Production run stats (2026-07-04, post-quality-gate, current):** 186,933 docs embedded (153,355 papers + 33,578 patents; 22.1% truncated); **237 named clusters** produced; noise rate **35.4%** (66,163 docs assigned `cluster_id = 'c_noise'`), down from 42.1% — the excluded/fallback text had been diffusing the whole embedding space, not just forming its own clusters. Mean cluster purity against each document's own CPC/topic-derived family: 94.2% (median 98.9%); the single worst cluster is 44.6%, and inspection confirms the remaining low-purity clusters are genuine technical overlap (e.g. resist chemistry shared between EUV and memory-device fabrication), not artifacts. `c_noise` remains labelled "Frontier / Unclustered" in the UI; noise docs retain UMAP coordinates and appear in the scatter map.
>
> **Issue 3 follow-up fix (2026-07-04):** the served corpus still contained OpenAlex works mistyped `type:article` that are really software release notes (e.g. "seL4: seL4 3.0.1", "IDBac v0.0.15") — the `type` filter alone can't catch these since OpenAlex's own field says "article". `stg_openalex_works` now also excludes titles matching a release-note pattern (name[: name] + version number), removing 9 records; `fact_document_cluster` now inner-joins the scoped staging models so any doc a staging filter removes drops out of the map/cluster fact instead of becoming an orphan point (closing the same failure class as the pre-quality-gate 1,103-orphan bug). Corpus post-fix: **186,930 docs (153,352 papers + 33,578 patents)**, 237 clusters unchanged. One residual case deliberately NOT filtered: "Refractiveindex.info database of optical constants" has a genuine, well-written 856-character abstract and is a real, citable dataset paper — it's a topic-relevance edge case (why did the Silicon Photonics topic classifier pick it up?), not a data-quality/junk-text problem, so no heuristic was invented to exclude it.
>
> **`excluded_documents` artifact + NULL-abstract fix (2026-07-05):** found a document state distinct from `c_noise` — 128 papers the gate excluded entirely (never embedded, no `fact_document_cluster` row, invisible on the map) were still counted in `dim_paper`/`mart_family`. 119 were genuinely non-English (confirmed: mostly French thesis abstracts); 9 were a separate bug — a `NULL` abstract was filtered out by `load_corpus()`'s SQL query before the gate ever ran, instead of being coalesced to `''` and falling back to title like a too-short abstract. Fixed: `load_corpus()` now coalesces `NULL` → `''`; `document_embeddings` is now a `multi_asset` that also writes `excluded_documents` (`doc_id`, `doc_type`, `exclusion_reason`) to `r2://p2p-lake/intermediate/excluded_documents/v{date}/excluded_documents.parquet` in the same pass that builds the corpus — one computation, not a separately-maintained SQL approximation. `stg_openalex_works`/`stg_patents_scoped` now exclude these same doc_ids. This is a new real dependency: dbt staging depends on Part 5 having run at least once; before it has, the source is an empty relation (see `create_external_sources()`), making the filter a no-op rather than a build error.
>
> **Known accepted gap — empty-string title bug (found 2026-07-05, fixed in code, not yet re-run):** the post-fix `dim_paper.cluster_id IS NULL` count dropped from 128 to 7, not to 0. Root cause, confirmed independently against the live warehouse on 2026-07-06: `load_corpus()`'s old SQL gate was `WHERE title IS NOT NULL AND length(title) > 0` — an empty string (`''`, not `NULL`) passes `IS NOT NULL` but fails `length > 0`, so the row never reached `resolve_paper_text()` at all, even with a real, substantial abstract (all 7 have 656–1,718 char English abstracts that would embed cleanly via title-empty abstract fallback). Consequence: these 7 are absent from `fact_document_cluster` (invisible on the map) yet 6 still count in `fact_publication`/`mart_family` with a resolved `family_id` — the same invisible-third-state failure class the `excluded_documents` mechanism exists to prevent, triggered from the opposite field. **Fixed in code** (`load_corpus()` now admits a row if *either* title or abstract is non-empty, letting `resolve_paper_text()` make the real decision; patents get an explicit `no_usable_text` exclusion reason instead of silent omission) but the fix only takes effect on the *next* Part 5 re-run — deferred given the negligible blast radius (7 / 186,932 docs) against the cost of a full re-cluster (~90 min + full cluster reshuffle + Haiku relabelling). Do not read `cluster_id IS NULL = 7` as fully resolved until Part 5 has been re-run since this fix landed.

**`excluded_documents`** — documents the embedding quality gate excluded entirely (R2: `intermediate/excluded_documents/v{date}/excluded_documents.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `doc_id` | String | OpenAlex `work_id` for papers; USPTO `patent_id` for patents |
| `doc_type` | String | `paper` or `patent` |
| `exclusion_reason` | String | `version_style_title` or `non_english_content` |
| `model_version` | String | Embedding model used: `all-MiniLM-L6-v2` |

> Written by `document_embeddings` (a `multi_asset`, alongside the `embeddings` output) in the same pass that decides the corpus — see the note above. Consumed by `stg_openalex_works`/`stg_patents_scoped` to exclude the same documents from the served corpus. `ml_intermediate.excluded_documents` always exists as a dbt source (unlike `clusters`/`cluster_labels`, which are only registered once Part 5 has run) — it resolves to an empty relation before Part 5's first run, so the staging exclusion is a no-op rather than a build error.

**`cluster_terms`** — c-TF-IDF top terms per cluster (R2: `intermediate/cluster_terms/v{date}/cluster_terms.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | String | Cluster identifier |
| `top_terms` | List[String] | Top 15 discriminating terms from BERTopic-style c-TF-IDF |
| `doc_count` | Int32 | Number of documents in this cluster |

**`cluster_labels`** — Claude Haiku-generated cluster names (R2: `intermediate/cluster_labels/v{date}/cluster_labels.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | String | Cluster identifier — PK |
| `tagline` | String | Short human-readable technology family name (2–6 words) |
| `summary_friendly` | String | 2–3 plain-English sentences describing the cluster |
| `top_terms` | List[String] | Top c-TF-IDF terms (carried through from cluster_terms) |

> Label generation: Claude `claude-haiku-4-5`, `max_tokens=256`. Prompt is grounded only in `top_terms` + 5 representative document titles — the model is explicitly forbidden from inventing information beyond the supplied evidence. `c_noise` receives a fixed label ("Frontier / Unclustered") with no API call. Spot-check quality target: ≥ 13/15 reviewed labels rated accurate — **current (2026-07-04, post-quality-gate) result: 13/15 (86.7%)**, passing but narrower than the pre-gate run's 14/15; see `docs/cluster_label_review.md` for the full breakdown, including one new confirmed failure (`c_15`, a generically-labelled cluster with off-domain content) not yet root-caused.

**dbt mart models (Part 5)**

| dbt model | Schema | Description |
|---|---|---|
| `dim_technology_cluster` | `main_marts` | One row per cluster; `cluster_id` PK, `tagline`, `summary_friendly`, `top_terms` |
| `fact_document_cluster` | `main_marts` | One row per document; `doc_id`, `doc_type`, `cluster_id`, `umap_x`, `umap_y`, `model_version` |
| `seed_cluster_family` | `main_marts` | One row per cluster; `family_id` (3-way: `euv` / `silicon_photonics` / `neuromorphic_in_memory`), `family_name`, `family_sort_order`. Computed fresh each run via CPC/topic majority vote — **display label only**, not used for counting (see ARCHITECTURE.md §Data model). |

`cluster_id` is denormalised onto `dim_paper`, `dim_patent`, `fact_publication`, and `fact_patent_filing` (left join from `fact_document_cluster`) to support cluster-filtered analytical queries without an extra join.

---

### Gold mart models (Part 6)

**`mart_velocity`** (MotherDuck: `main_marts.mart_velocity`)

Grain: `(cluster_id, year)`. Pure annual time series — paper and patent counts per cluster per year. Citation-lag metrics are in `mart_gap` (they are per-cluster scalars, not per-year). *(2026-06-26 figures: all 304 clusters × up to 14 years = 3,794 rows. Current, 2026-07-04: 238 clusters → 3,044 rows.)*

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | String | FK → `dim_technology_cluster` |
| `tagline` | String | Human-readable cluster name |
| `is_noise` | Boolean | True for `c_noise`; exclude from headline findings |
| `year` | Integer | Calendar year |
| `paper_count` | Integer | Distinct papers published in this cluster × year |
| `patent_count` | Integer | Distinct patents filed in this cluster × year |

**`mart_competitive`** (MotherDuck: `main_marts.mart_competitive`)

Grain: `(cluster_id, side, org_id_key)`. *(2026-06-26 figures: 8,216 patent-side rows + 62,963 paper-side rows across 248 / 284 clusters. Current, 2026-07-04: 7,491 patent-side rows + 60,949 paper-side rows.)*

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | String | FK → `dim_technology_cluster` |
| `side` | String | `'patent'` or `'paper'` |
| `org_id_key` | String | `coalesce(org_id, 'unresolved')` — never NULL |
| `org_id` | String | Nullable canonical org ID |
| `canonical_name` | String | Human-readable org name; `'Unresolved'` for no-crosswalk orgs |
| `match_method` | String | ER match method from crosswalk; `'none'` for unresolved |
| `confidence` | String | ER confidence from crosswalk; `'low'` for unresolved |
| `doc_count` | Integer | Distinct patents (patent side) or distinct papers (paper side) for this org+cluster |
| `share` | Float | `doc_count / cluster_total`. Paper-side shares sum to >100% per cluster (co-attribution, not partitioned). Each individual org's share is in [0, 1]. |
| `cluster_total` | Integer | Distinct documents in this cluster for this side |
| `rank_in_cluster` | Integer | Rank by `doc_count` desc within `(cluster_id, side)` |

**`mart_gap`** (MotherDuck: `main_marts.mart_gap`)

Grain: `cluster_id`. *(2026-06-26 figures: 304 rows, 161 `hhi_reportable`. Current, 2026-07-04: 238 rows, 135 `hhi_reportable`.)*

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | String | PK, FK → `dim_technology_cluster` |
| `tagline` | String | Human-readable cluster name |
| `is_noise` | Boolean | True for `c_noise` |
| `n_patents` | Integer | Distinct primary-assignee patents in cluster |
| `n_assignees` | Integer | Distinct resolved assignees in HHI computation |
| `pct_unresolved_patents` | Float | % of patents excluded from HHI (no resolved org); 1.6% across scope |
| `hhi` | Float | HHI ∈ [0, 1] over primary assignees. NULL when `resolved_patents < 10`. |
| `hhi_reportable` | Boolean | True when `resolved_patents ≥ 10` |
| `n_oa_institutions` | Integer | Distinct OpenAlex `institution_id`s contributing papers (sub-org level — IBM Research Almaden ≠ IBM Research Zürich) |
| `n_research_orgs` | Integer | Distinct `org_id`s post-ER contributing papers (org-level, comparable to `n_assignees`) |
| `n_papers` | Integer | Distinct papers in this cluster |
| `npl_median_lag_years` | Float | Median citation lag in years (paper pub date → patent filing date, via NPL links). **Patent's cluster is the anchor.** NULL when `npl_n_links < 20`. |
| `npl_n_links` | Integer | Number of NPL-linked pairs driving the lag estimate |
| `npl_reportable` | Boolean | True when `npl_n_links ≥ 20` |
| `cohort_med_pub_year` | Float | Median paper publication year for this cluster (soft cohort estimate) |
| `cohort_med_filing_year` | Float | Median patent filing year for this cluster (soft cohort estimate) |
| `cohort_lag_years` | Float | `cohort_med_filing_year − cohort_med_pub_year`. **SOFT ESTIMATE — not NPL-linked.** May be negative. |

HHI methodology: primary assignee = `assignee_sequence = 0` preferred; patents with no org-type assignee resolved to crosswalk are excluded from shares (pct_unresolved = 1.6%). HHI = Σ(share²). Framing: concentration within US patents only — not a global geography comparison.

*(2026-06-26 figures: 43 clusters `npl_reportable = true`. Fastest lag: c_158, 2.17 yr, N=96. Slowest: c_234, 5.27 yr, N=117.)*
**Current, 2026-07-04**: 32 clusters have `npl_reportable = true` (N ≥ 20 NPL links). Fastest: `c_121` "In-Memory Computing with Resistive Devices" (1.92 yr, N=21). Slowest: `c_188` "Photonic Logic Gates and Optical Computing" (6.77 yr, N=52). Cluster IDs are not stable across re-clustering runs, so `c_158`/`c_234` above no longer refer to the same content — always re-derive the fastest/slowest cluster from a live query rather than citing an ID from a prior run. Use `n_research_orgs` for breadth-vs-concentration comparisons; `n_oa_institutions` for fine-grained diversity counts.

**`mart_family`** (MotherDuck: `main_marts.mart_family`)

Grain: `family_id` — one row per one of the **3** headline families (`euv` / `silicon_photonics` / `neuromorphic_in_memory`; see the two-tier family tagging note in ARCHITECTURE.md §Data model). Aggregates `mart_gap` via `seed_cluster_family` for the map/cluster-browsing story — **not** the source of truth for per-document counts (those come from `fact_patent_filing.family_id` / `fact_publication.family_id` directly). Originally a 5-way split (adding `lasers` and splitting `in_memory` from `neuromorphic`); reverted 2026-07-04 after purity measurement showed the two extra seams were not real boundaries — see ARCHITECTURE.md and `MEMORY.md` for the full rationale.

| Column | Type | Meaning |
|---|---|---|
| `family_id` | String | PK: `euv` / `silicon_photonics` / `neuromorphic_in_memory` |
| `family_name`, `family_sort_order` | String, Integer | Display name and fixed ordering |
| `n_papers`, `n_patents` | Integer | Summed from `mart_gap` across the family's clusters |
| `patent_share` | Float | `n_patents / (n_patents + n_papers)` |
| `median_lag_years_weighted` | Float | NPL-linked citation lag, weighted by `npl_n_links` per contributing cluster |
| `top_assignee_name`, `top_researcher_name` | String | Mode of each cluster's #1-ranked org within the family — an approximation; the UI's actual leaderboards use a `SUM(doc_count)` query against `mart_competitive` instead (see `apps/ui/data.py::load_family_top_orgs`), which is more accurate than this column |

> **Verified 2026-07-04**: EUV — 5,830 papers, 5,230 patents, 47.3% patent share, 4.24 yr weighted lag. Silicon Photonics — 47,595 papers, 3,362 patents, 6.6% share, 3.76 yr lag. Neuromorphic & In-Memory — 31,570 papers, 13,112 patents, 29.3% share, 2.76 yr lag.
