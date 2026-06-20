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

## 5. Column dictionary

> Stub — populated per source entity as Parts 2 (PatentsView staging) and 4 (OpenAlex staging, marts) land. Each table below will list column name, type, meaning, and any `match_method` / `confidence` semantics.

- **PatentsView** — `g_patent`, `g_assignee`, `g_cpc_current`, `g_us_patent_citation`, `g_other_reference`, `g_application` _(Part 2)_
- **OpenAlex** — `works` raw schema, reconstructed abstract _(Part 1 / Part 4)_
- **NPL matcher** — `fact_npl_link` (`match_method = npl_citation`, `confidence`), and the `ref_npl_gold_eval` reference table; NPL matcher precision/recall vs the Marx & Fuegi gold set _(Part 4)_
- **Entity resolution** — `int_organization_crosswalk` (`org_id`, source IDs, `match_method`, `confidence`); see `docs/er_eval_set.md` _(Part 3)_
