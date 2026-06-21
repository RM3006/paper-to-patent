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

**Year windows:** papers (OpenAlex `publication_date`) **2012–2024**; patents (PatentsView `filing_date`) **2014–2024**.

**Topic-ID verification (2026-06-20):** the four scope topic IDs above resolve live and match the ROADMAP table — no update required. Several descriptive search terms collapse onto the same four canonical topics (e.g. "Memristors", "In-Memory Computing", "Spiking Neural Networks" all resolve to `T10502`); the search terms "EUV photomask / pellicle" and "Plasma-based EUV light source" return no dedicated topic and are covered by `T11338`.

---

## 2. Part 0 NPL feasibility spike — recorded counts

Produced by `notebooks/part0_npl_spike.py` and `notebooks/part0_openalex_count.py`.

> **Important caveat — these are CPC-only counts, with NO filing-date filter applied.**
> `g_patent.tsv` carries the grant date only; the `filing_date` filter (2014–2024) requires `g_application.tsv` and is applied in **Part 2**, not in the spike. The Part 2 `patents_scoped` corpus will therefore be **smaller** than the 68,800 below — the ROADMAP Part 2 "within 5% of the spike count" check must compare against a *re-run of this CPC filter*, not against the date-filtered corpus.

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
| Works in scope (4 topics, 2012–2024, `language:en`, `has_abstract:true`) | **150,984** | ≥ 10,000 | ✅ |

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

The build machine uses the **read-write** key; the Streamlit app uses a separate **read-only** token (least privilege). Credentials come from `.env.local` / Streamlit secrets — never hardcoded.

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

---

### OpenAlex raw schema (Part 1 / Part 4 — stub)

- `works` raw Parquet schema and reconstructed abstract — to be documented in Part 4 when dbt staging models are built.

---

### NPL matcher and entity resolution (Parts 3–4 — stub)

- **NPL matcher** — `fact_npl_link` (`match_method = npl_citation`, `confidence`), and `ref_npl_gold_eval`; precision/recall vs Marx & Fuegi gold set _(Part 4)_
- **Entity resolution** — `int_organization_crosswalk` (`org_id`, source IDs, `match_method`, `confidence`); see `docs/er_eval_set.md` _(Part 3)_
