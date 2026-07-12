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
| Marx & Fuegi "Reliance on Science" `_pcs_oa.csv` (Zenodo 8278104) | Hybrid NPL link source (2026-07-10): primary source of `fact_npl_link` edges for any patent it covers (vintage caps ~early-2023 grants), and the gold eval set for measuring our own matcher's quality on the remaining patents | free download | CC-BY-4.0 |

**Files used in the Part 0 spike** (gitignored under `data/`): `g_patent.tsv`, `g_cpc_current.tsv`, `g_other_reference.tsv`, `data/reference/marx_fuegi_pcs.csv`. `g_application.tsv` (filing dates) and `g_assignee_disambiguated.tsv` are already downloaded for Part 2.

---

## 4a. External reference — sizing the US-only lens (not ingested)

Not a pipeline source. Cited only to quantify the US-only patent-coverage limitation disclosed in `README.md`, `ARCHITECTURE.md` (Known limitations), `docs/workflow.md` (weakness #4), and the UI methodology footer.

| Metric | Value | Source |
|---|---|---|
| Worldwide patent applications, 2024 | 3.7 million | WIPO, *World Intellectual Property Indicators 2025: Highlights*, accessed 2026-07-12 |
| USPTO applications, 2024 | 603,194 | same |
| USPTO share of world total | ≈16% (603,194 ÷ 3.7M) | derived — straight division of the two figures above, not a corpus-computed metric |
| CNIPA (China) share of world total, 2024 | 49.1% | same report |

**The offices this project cannot see at all, ranked by 2024 filing volume** (WIPO top-5, same report):

| Office | Country/region | 2024 applications | Share of world | In our data? |
|---|---|---|---|---|
| CNIPA | China | 1.8 million | 49.1% | **No** |
| USPTO | United States | 603,194 | ≈16% | Yes (our only source) |
| JPO | Japan | 306,855 | ≈8% | **No** |
| KIPO | South Korea | 246,245 | ≈7% | **No** |
| EPO | Europe (regional) | 199,402 | ≈5% | **No** |

These five offices together account for 85.5% of world filings. **Four of the five — including the single largest, CNIPA — are entirely absent from this project.** For semiconductors specifically this is not an abstract gap: ASML (EUV lithography) files primarily at the EPO; TSMC, Samsung, and SK Hynix primarily at KIPO/their home offices; Tokyo Electron, Canon, and Nikon primarily at the JPO. Naming these players is deliberate — it converts "US-only" from an abstract disclaimer into a concrete list of who the map cannot rank fairly.

Source: <https://www.wipo.int/web-publications/world-intellectual-property-indicators-2025-highlights/en/patents-highlights.html>

**Why this is exempt from CLAUDE.md rule 13** ("never hard-code metrics prone to change on every run"): these figures change on WIPO's annual publication cadence, not on our pipeline's runs — they are external, dated, cited constants, not corpus-derived statistics.

**Why ≈16% is a conservative *upper bound* for our specific domain:** semiconductor patenting is more non-US-concentrated than the all-technology average (ASML/EPO, TSMC/Samsung/SK Hynix, the Japanese lithography and tool makers). No free CPC-level worldwide breakdown was found, so the all-technology figure is what's cited — but the true US-only share for our four CPC families is plausibly lower than 16%, not higher.

**Refresh cadence:** WIPI publishes annually (~November). Re-verify these figures against the next edition before the ~2026 numbers go stale in visible copy.

**What closing this gap would take:** see `ROADMAP.md` → *Beyond v1* #2 for the v2 design sketch (source options, classification-coverage caveats per office, and why the citation-lag metric likely would not extend cleanly to non-US patents).

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

> Scope filter: a scope CPC code (prefix match on the 10 codes in the scope contract) must
> appear among the patent's **top-5 classifications** (`cpc_sequence` 0–4), + `filing_date`
> 2014–2025. See `pipelines/nexus/assets/ingest/patentsview.py::SCOPE_CPC_PREFIXES` and
> `SCOPE_CPC_MAX_SEQUENCE`.

> **Scope-rule change (2026-07-08): top-5 prominence.** The original filter matched a scope
> code at *any* CPC position among the ~12 codes a patent carries. Because a patent spans on
> average 2.7 CPC subclasses, that admitted "buried mention" patents whose headline invention
> is off-domain (e.g. a logistics, biometric, or animation patent that tags a neural-net code
> deep in its list). ~38% of the old corpus had a primary CPC outside the six scope
> subclasses, and those patents pooled into a single 6,895-doc generic-ML noise cluster
> (formerly `c_15`/`c_70`). Requiring the technology to be *prominent* (top-5) rather than
> merely *present* dropped the corpus from **33,578 → 23,397 patents (−30.3%)** and shrank the
> noise cluster ~76%. Papers were already filtered on OpenAlex's **primary** topic only, so no
> analogous change applies on the paper side. The narrower alternative (primary-CPC-only,
> −38%) would have removed the residual noise entirely but also dropped ~21% of genuine
> in-domain patents whose scope code is prominent-but-not-primary; the gentler top-5 rule was
> chosen. See `MEMORY.md` and `docs/cluster_label_review.md` (residual `c_77`) for the full
> analysis.

> **Verified 2026-07-08 (snapshot v2026-07-08):** `patents_scoped` = **23,397** rows under the
> top-5 rule (down from 33,578 under the any-position rule). The stale v2026-06-21 snapshot was
> deleted so the `patents_scoped/*/*.parquet` glob (used by `patentsview_orgs_staging`) resolves
> to the tightened corpus only.

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
>
> **Verified 2026-07-06 (post OpenAlex re-ingest with the `type:article|preprint|review` ingest-time filter):** full ER chain re-run (`openalex_institutions_staging` → `seed_crosswalk_oa_matched`/`fuzzy_org_bridge` → `ror_bridge` → `org_crosswalk`) against the fresh raw snapshot. 12,956 distinct OA institutions (was 12,936) → **16,235 crosswalk rows · 14,198 distinct org_ids**. `fuzzy_org_bridge` this time found 2,320 fuzzy_high pairs (up from 1,160 — this run genuinely re-matched from scratch against the new institution set, unlike the 2026-07-04 snapshot which was untouched since 06-22), 0 fuzzy_review. `ror_bridge`: 38 institution rows across 4 org_ids, unchanged shape. No new eval-set measurement taken this session — the score=100 exact/subset-match criterion is unchanged and structurally cannot admit a false positive differently than before; re-validate against `docs/er_eval_set.md` before citing a precision number for this specific snapshot.

---

### NPL linkage (Part 4 — complete; hybrid source since 2026-07-10)

**Approach**: `fact_npl_link` is a hybrid, partitioned per patent. For any patent the Marx &
Fuegi "Reliance on Science" dataset covers at all, ALL of that patent's edges come from Marx &
Fuegi (`link_source = 'marx_fuegi'`) — gold-standard, published citation data. For patents
outside that coverage (its vintage caps out around patents granted ~early 2023), edges come
from our own DOI + fuzzy-title matcher instead (`link_source = 'doi'` / `'fuzzy_title'`). No
patent draws edges from both sources (`models/tests/assert_fact_npl_link_single_source.sql`).

**Why hybrid, not matcher-only.** An offline, unconfounded comparison — joining the raw Marx &
Fuegi CSV against our own scope patents and OpenAlex corpus, independent of any matcher
threshold — measured, within the patents both sources can see: **7,125 Marx & Fuegi edges vs
4,619 matcher edges**, with only 2,292 in agreement. That gap means a large share of the
matcher's edges in that overlap were either misses Marx & Fuegi caught or matcher false
positives, and Marx & Fuegi's own published precision exceeds the matcher's self-graded ~0.85.
The matcher's genuine advantage is coverage of **recent grants** Marx & Fuegi structurally
cannot see: 29% of scope patents (6,813 of 23,397, as of 2026-07-10) were granted after Marx &
Fuegi's vintage ceiling (~patent 11,617,290, ~April 2023), and that share grows every year as
new patents grant. This is what the hybrid design captures — the best available source on each
side of the seam, rather than one matcher trying to do both jobs at a lower bar than either.

**Marx & Fuegi source** (`mf_npl_links` asset,
`pipelines/nexus/assets/transform/mf_matcher.py`): filters the CSV to scope patents ∩ OpenAlex
corpus, dedups multiple citation-location rows per (patent, paper) pair (preferring
`both` > `front` > `body`, then higher `confscore`), and maps `wherefound` to this project's
confidence tier (front/both → high, body-only → medium — front-page citations are the ones an
examiner/applicant explicitly listed; body-only came from Marx & Fuegi's separate, lower-
precision in-text extraction method). `confscore` (1–10) and the self-citation flag (`self`)
are carried through as-is, exposed but not used to gate inclusion.

**Verified 2026-07-10**: 7,125 Marx & Fuegi links in scope ∩ corpus (before the
publication-date-before-filing-date filter in `fact_npl_link.sql`).

**Custom matcher (two-route)**, `pipelines/nexus/assets/transform/npl_matcher.py` — now scoped
to patents Marx & Fuegi doesn't cover.

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

> **Re-run 2026-07-06 (against the fresh OpenAlex + org_crosswalk snapshots):** gold eval set now 8,558 pairs / 3,284 distinct patents (was 8,640/3,301 — minor drift from the OpenAlex re-ingest). DOI route: 1,092 high-confidence matches. Fuzzy route re-evaluated at all three candidate thresholds: 90 → cond. precision 0.847, recall 0.327, 6,139 total links; 95 → 0.864/0.114; 100 → 0.844/0.060. **Chosen threshold unchanged at 90** (still the lowest clearing the ≥0.80 floor). Final: **6,139 links (1,092 high/DOI + 5,047 medium/fuzzy after dedup)**. Conditional precision improved slightly (0.831 → 0.847) — within run-to-run noise given the corpus and eval-set sizes both shifted a little, not attributable to any matcher logic change.

> **Hybrid pivot 2026-07-10**: the matcher itself (`npl_links_raw`) is unchanged — it still runs against the full unmatched-NPL-string pool, and the precision/recall table above still accurately describes its own standalone quality. What changed is downstream: `fact_npl_link.sql` now keeps a matcher edge **only** for patents Marx & Fuegi has zero coverage of. Of the matcher's 6,139 raw links, only **1,993 (480 DOI + 1,513 fuzzy)** survive into `fact_npl_link` — the rest were on patents Marx & Fuegi already covers, where Marx & Fuegi's edges are used instead (see "Why hybrid, not matcher-only" above).

**`fact_npl_link`** — resolved paper↔patent edges (MotherDuck: `main_marts.fact_npl_link`)

| Column | Type | Meaning |
|---|---|---|
| `patent_id` | String | Citing patent (in scope) |
| `work_id` | String | Matched OpenAlex work ID (e.g. `W2741809807`) |
| `match_method` | String | Always `npl_citation` |
| `confidence` | String | `high` (Marx & Fuegi front/both, or matcher DOI route) or `medium` (Marx & Fuegi body-only, or matcher fuzzy-title route) |
| `link_source` | String | `marx_fuegi`, `doi`, or `fuzzy_title` — which source this edge came from (see hybrid seam above) |
| `doi_extracted` | String | Bare DOI, when `link_source = 'doi'`. NULL otherwise |
| `mf_confscore` | Integer | Marx & Fuegi's own match-confidence score (1–10), when `link_source = 'marx_fuegi'`. NULL otherwise |
| `mf_wherefound` | String | Marx & Fuegi's citation-location flag (`front`\|`body`\|`both`), when `link_source = 'marx_fuegi'`. NULL otherwise |
| `mf_self` | String | Marx & Fuegi's self-citation flag (`isself`\|`notself`\|`unkself`), when `link_source = 'marx_fuegi'`. NULL otherwise |
| `publication_date` | Date | Paper publication date — citation-lag anchor |
| `filing_date` | Date | Patent filing date — citation-lag anchor |
| `citation_lag_days` | Integer | Days from publication to filing |
| `citation_lag_years` | Float | Rounded to 2 decimal places; **never called "lead time"** |

> **Verified 2026-06-22**: 5,921 rows (after `publication_date < filing_date` filter in dbt), 2,973 distinct patents, 2,470 distinct works. Median citation lag ≈ 3.6 years. Top assignees by NPL links: GlobalFoundries (704), IBM (612), STMicroelectronics (177), ASML (99), MIT (95), Intel (95).
>
> **Verified 2026-07-04**: 5,749 rows (1,075 high/DOI + 4,674 medium/fuzzy), 2,896 distinct patents, 2,433 distinct works, median lag 3.13 years. Note: this reflects the *original* DOI/fuzzy-title matcher run intersected with the current (type-filtered, smaller) OpenAlex corpus via the inner joins in `fact_npl_link.sql` — the matcher itself (`npl_links_raw`) has not been re-run against the current corpus, so the precision/recall table above is not a fresh measurement. A re-run would be needed to confirm the 0.831 conditional precision still holds.
>
> **Verified 2026-07-06 (matcher actually re-run this time, closing the gap noted above):** `npl_links_raw` re-executed against the fresh OpenAlex + org_crosswalk snapshots (see NPL matcher section above for the fresh precision/recall table). `fact_npl_link`: 1,076 rows high/DOI + 4,719 rows medium/fuzzy after the `publication_date < filing_date` dbt filter (6,139 raw matcher output → this many survive the date-ordering check).
>
> **Verified 2026-07-10 (hybrid Marx & Fuegi + matcher source, post `mf_npl_links` asset run):** **9,025 rows** total — 7,032 `marx_fuegi` + 480 `doi` + 1,513 `fuzzy_title` (after the `publication_date < filing_date` dbt filter). 3,528 distinct patents, 3,879 distinct works. Median citation lag 3.06 years. Confidence split: 7,376 high, 1,649 medium. Rose from the prior matcher-only 6,139 total / 2,973 distinct patents.

---

### ML pipeline intermediate tables (Part 5)

**`clusters`** — UMAP + HDBSCAN document assignments (R2: `intermediate/clusters/v{date}/clusters.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `doc_id` | String | OpenAlex `work_id` for papers; USPTO `patent_id` for patents |
| `doc_type` | String | `paper` or `patent` |
| `cluster_id` | String | Cluster identifier — `c_{label}` for named clusters, `c_noise` for HDBSCAN noise points |
| `umap_x` | Float32 | 2D UMAP x-coordinate (not currently rendered — the live "map" is a per-cluster patents×papers bubble chart, not a UMAP scatter) |
| `umap_y` | Float32 | 2D UMAP y-coordinate (see `umap_x`) |
| `model_version` | String | Embedding model used: `all-MiniLM-L6-v2` |
| `corpus_signature` | String | 16-char sha256 of the sorted-deduped doc-id set this realization was cut from. The clustering **freeze** key (added 2026-07-08): `document_clusters` reuses the frozen snapshot when the current corpus signature matches this, and re-cuts only when it differs (documents onboarded). Same value on every row. See ARCHITECTURE.md §8. |

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
> **Empty-string title bug — RESOLVED 2026-07-06.** Fixed in code 2026-07-05 (see prior paragraph), the fix finally took effect in the 2026-07-06 re-run: `dim_paper.cluster_id IS NULL` / `dim_patent.cluster_id IS NULL` both confirmed at **0** after the rebuild below.
>
> **Full pipeline re-run, 2026-07-06 (OpenAlex re-ingest with the `type:article|preprint|review` filter + ER crosswalk + NPL matcher + Part 5 ML, all in sequence):** first pass embedded 186,939 docs (153,361 papers + 33,578 patents), 0 newly excluded — because `dim_paper` at that moment still had the *prior* run's 119-doc exclusion list baked in via the staging filter, so the fresh gate never got a chance to see them. That produced an empty `excluded_documents` snapshot, which (correctly, mechanically) stopped blacklisting those 119 docs on the next dbt build — reintroducing them into `dim_paper` with no cluster assignment (**120** null-cluster papers surfaced: the 119 historical ones + 1 new). This is a **self-referential staleness gap in the exclusion mechanism**, not a code bug: `excluded_documents` only ever reflects what its *own* run's input contained, so a document already filtered out upstream is invisible to it and silently drops off the exclusion list the next time the gate runs. **Fix applied: re-ran the ML cycle a second time** now that `dim_paper` (post the empty-snapshot dbt rebuild) was genuinely complete/unfiltered — the gate correctly re-decided on all 153,480 candidate papers, found **118** to exclude (non-English, matching the historical ~119 count within natural corpus drift), and this time nothing was invisible to it. **Final corpus: 186,940 docs (153,362 papers + 33,578 patents), 240 named clusters + noise (39.7% paper noise / 40.3% patent noise), `dim_paper`/`dim_patent` null-cluster count = 0 both.** **Operational lesson for the next full re-run:** when re-running Part 5 as part of a larger pipeline refresh (not in isolation), either clear the previous `excluded_documents` R2 snapshot *before* the first embeddings pass so the gate always sees a fully unfiltered `dim_paper`, or simply expect to run the ML cycle twice and check `dim_paper.cluster_id IS NULL` after the first dbt fold-in before declaring done.
>
> **Patent-scope tightening + full re-cluster, 2026-07-08 (top-5 CPC rule):** the patent filter was changed from any-position to top-5 (see the `patents_scoped` scope-rule note above), dropping the patent corpus 33,578 → **23,397**. Papers unchanged. The re-cluster applied the **operational lesson above the right way**: the old `excluded_documents` snapshots (v07-05, v07-06) were **deleted before** the pre-embedding dbt build so `dim_paper` was fully complete (153,480) when the gate ran — so the orphan bug did **not** recur, and only **one** ML cycle was needed. Embeddings: **176,759 docs (153,362 papers + 23,397 patents), 118 excluded** (same non-English set as before, papers unchanged). Clustering: **227 named clusters**, 41.1% noise (72,573 docs). `dim_paper`/`dim_patent` null-cluster = **0 / 0** confirmed on both dev and MotherDuck prod. **Residual noise (expected, disclosed):** the top-5 rule reduced but did not eliminate the generic-ML noise cluster — it reformed as **`c_77` "Machine Learning Signal Processing Methods"** (1,564 patents, 68% off-family primary CPC: biometrics, finance, audio-recommendation, form-extraction patents that carry a prominent neural-net code). This is the known limit of the top-5 (vs primary-only) rule; see `docs/cluster_label_review.md`. Also note ~10.2k of the 23,397 patents (44%) have a `NULL` `family_id` (primary CPC outside the six scope subclasses) — up from 38% pre-tightening, because top-5 also drops some genuine patents whose scope code was buried while keeping off-family patents whose scope code is prominent.

> **Acyclic refactor — the two-pass operational lessons above are now OBSOLETE (2026-07-11).** The staging↔ML cycle that forced "run the ML cycle twice / clear the `excluded_documents` snapshot before the pre-embedding build" is gone: exclusions are computed upstream by `document_exclusions` (which reads the raw corpus, not `dim_paper`), and the dims no longer carry `cluster_id`. A single `materialize all` now runs in topological order — no second ML pass, no snapshot-clearing dance, no null-cluster orphan risk from a stale exclusion snapshot. The 2026-07-05/06/08 notes above are kept as the historical record of the problem that motivated the fix. See ARCHITECTURE.md §5 and `docs/workflow.md` Stages 4a/4/9.

**`excluded_documents`** — documents the pre-staging quality gate screened out entirely (R2: `intermediate/excluded_documents/v{date}/excluded_documents.parquet`)

| Column | Type | Meaning |
|---|---|---|
| `doc_id` | String | OpenAlex `work_id` for papers; USPTO `patent_id` for patents |
| `doc_type` | String | `paper` or `patent` |
| `exclusion_reason` | String | `version_style_title`, `non_english_content`, or `no_usable_text` |
| `model_version` | String | Gate version tag: `quality-gate-v1` (langdetect + title heuristics; not an ML model) |

> Written by the **`document_exclusions`** asset (since 2026-07-11), which reads the raw scope corpus (openalex works + patents_scoped) and runs the quality gate **upstream** of staging; `stg_openalex_works`/`stg_patents_scoped` then apply the list via a `NOT IN` filter. This is what makes the pipeline acyclic: the gate needs only title/abstract text, not embeddings, so it runs before staging rather than inside the embedding step (previously `document_embeddings` was a `multi_asset` that produced this alongside embeddings, which created the staging↔ML cycle — see ARCHITECTURE.md §5). `ml_intermediate.excluded_documents` always exists as a dbt source (unlike `clusters`/`cluster_labels`) — `create_external_sources()` resolves it to an empty relation before `document_exclusions` has ever produced a snapshot, a defensive no-op for a standalone `dbt build`.

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
| `seed_cluster_family` | `main_marts` | One row per cluster; `family_id` (`euv` / `silicon_photonics` / `neuromorphic_in_memory` / `mixed`), `family_name`, `family_sort_order`. A real family is assigned only when it is **≥ 80% of the cluster's family-resolvable documents AND those resolvable docs are ≥ 50% of the cluster** (confidence floor, added 2026-07-08); clusters that genuinely span families or are mostly off-scope get `mixed`. Computed fresh each run from CPC/topic votes — **display label only**, not used for counting (see ARCHITECTURE.md §Data model). `mixed` is excluded from UI headline charts. |

`cluster_id` is denormalised onto `fact_publication` and `fact_patent_filing` (left join from `fact_document_cluster`) to support cluster-filtered analytical queries without an extra join. `dim_paper`/`dim_patent` deliberately do **not** carry it — the bridge `fact_document_cluster` is the sole doc→cluster source, keeping the dims independent of the ML step that reads them (the old cycle; see ARCHITECTURE.md §5). Consumers that need a paper's/patent's cluster join the bridge on `doc_id` (e.g. `seed_cluster_family`, `mart_gap`, `apps/ui/data.py`).

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

Grain: `(cluster_id, side, org_id_key, family_id_key)` — widened 2026-07-12 to add the document-level family dimension (previously `(cluster_id, side, org_id_key)`).

| Column | Type | Meaning |
|---|---|---|
| `cluster_id` | String | FK → `dim_technology_cluster` |
| `side` | String | `'patent'` or `'paper'` |
| `org_id_key` | String | `coalesce(org_id, 'unresolved')` — never NULL |
| `org_id` | String | Nullable canonical org ID |
| `family_id_key` | String | `coalesce(family_id, 'unattributed')` — never NULL |
| `family_id` | String | Nullable document-level family (5-way: `euv`/`lasers`/`si_photonics`/`neuromorphic`/`in_memory`) — each document's own direct family, not the cluster's label |
| `canonical_name` | String | Human-readable org name; `'Unresolved'` for no-crosswalk orgs |
| `match_method` | String | ER match method from crosswalk; `'none'` for unresolved |
| `confidence` | String | ER confidence from crosswalk; `'low'` for unresolved |
| `doc_count` | Integer | Distinct patents (patent side) or distinct papers (paper side) for this org+cluster+family slice |
| `share` | Float | `doc_count / cluster_total` — denominator is the WHOLE cluster (all families combined), unaffected by the family split. Paper-side shares sum to >100% per cluster (co-attribution, not partitioned). Each individual row's share is in [0, 1]. |
| `cluster_total` | Integer | Distinct documents in this cluster for this side (all families combined) |
| `rank_in_cluster` | Integer | Rank by the org's TOTAL `doc_count` across all its family slices within `(cluster_id, side)` — the same value repeats on every family-sliced row belonging to that org, not a per-family rank |

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

Grain: `family_id` — one row per one of the **5 document-level families** (`euv` / `lasers` / `si_photonics` / `neuromorphic` / `in_memory`; see the two-tier family tagging note in ARCHITECTURE.md §Data model). Rebuilt 2026-07-12 to aggregate `fact_patent_filing` / `fact_publication` directly by their own `family_id` — the authoritative doc-level column — instead of `mart_gap` via `seed_cluster_family` (the prior cluster-label basis under-counted every family; see ARCHITECTURE.md and `MEMORY.md` for the full rationale). No `mixed` row: documents with no resolvable `family_id` are not a row here — the UI discloses that count separately (`load_unattributed_counts`) rather than folding it into one of the 5.

| Column | Type | Meaning |
|---|---|---|
| `family_id` | String | PK: `euv` / `lasers` / `si_photonics` / `neuromorphic` / `in_memory` |
| `family_name`, `family_sort_order` | String, Integer | Display name and fixed ordering |
| `n_papers`, `n_patents` | Integer | Distinct documents whose own `family_id` is this family |
| `patent_share` | Float | `n_patents / (total n_patents across all 5 families)` (redefined 2026-07-12; was `n_patents / (n_patents + n_papers)`). This family's slice of the US patent pool — a composition ratio over patents alone, not a research-to-patent capture rate. Papers are not part of the formula. |
| `n_research_orgs_sum`, `n_assignees_sum` | Integer | Exact distinct-org counts (paper side / patent side respectively) for this family. Column names kept for continuity with the prior cluster-rollup version, which was a cross-cluster approximation; this is now exact. |
| `median_lag_years_weighted` | Float | TRUE median of `citation_lag_years` over every NPL-linked pair whose citing patent's own `family_id` is this family — not a weighted average of cluster medians, despite the legacy column name (kept to avoid a UI-wide rename mid-refactor). NULL when `total_npl_links < 20`. |
| `total_npl_links` | Integer | Count of NPL-linked pairs backing `median_lag_years_weighted` |
| `avg_grant_lag_years` | Float | Mean of (`grant_date - filing_date`) in years for this family's patents. The one narrow, explicitly authorised exception to "grant date is never used for a time metric" (CLAUDE.md rule 2, 2026-07 amendment) — a data-completeness diagnostic, not an R&D-velocity claim, used solely to shade recent filing years on the Family Deepdive velocity chart that are under-counted because those patents haven't yet cleared USPTO examination. Never blended with `median_lag_years_weighted`. |
