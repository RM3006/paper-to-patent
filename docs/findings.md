# findings.md — Headline numbers for "The Chips Behind AI"

All numbers here are reproducible by querying the marts in MotherDuck (or a local `dev.duckdb` build).
Exact queries are shown under each finding.

**Snapshot**: 2026-07-04 (post embedding-quality-gate re-cluster; 238 clusters, 3-way
cluster family scheme). Cluster IDs are not stable across re-clustering runs — every
finding below cites the cluster's current tagline alongside its ID, and if this doc is
refreshed after a future re-cluster, cite fresh IDs rather than assuming these persist.

**Caveats applying to all findings:**
- Patent data is US-only (PatentsView). Findings describe US patenting, not global IP capture.
- Paper data is English-language OpenAlex works (topics T11338, T10299, T11429, T10502, 2012–2025).
- "Citation lag" = days from a paper's `publication_date` to the citing patent's `filing_date`
  (from `fact_npl_link`). It is NOT "time to market" or "R&D-to-commercialisation time" — it
  measures how long before published research appears cited in a filed patent.
- HHI is Herfindahl-Hirschman Index over primary assignees of US patents. It is a descriptive
  concentration metric, not a causal or competitive-strategy claim.

---

## Finding 1 — Fastest NPL citation lag: In-Memory Computing with Resistive Devices

**Cluster:** `c_121` — In-Memory Computing with Resistive Devices
**Metric:** Median NPL-linked citation lag
**Value:** **1.92 years** (median publication-to-filing interval across 21 confirmed NPL-linked paper→patent pairs — at the minimum reportable threshold, N ≥ 20)

> Research on resistive in-memory computing devices takes a median of 1.92 years from
> publication before it is cited in a US patent filing — the fastest confirmed lag among
> the 32 clusters with enough NPL-linked pairs to report. Anchored on the citing patent's
> filing date, not its grant date. N is at the minimum reportable threshold; read this as
> indicative rather than definitive.

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links,
       n_oa_institutions, n_research_orgs, n_assignees, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_121';
-- Returns: c_121 | In-Memory Computing with Resistive Devices | 1.92 | 21 | 110 | 102 | 8 | 91
```

---

## Finding 2 — Slowest NPL citation lag: Photonic Logic Gates and Optical Computing

**Cluster:** `c_188` — Photonic Logic Gates and Optical Computing
**Metric:** Median NPL-linked citation lag
**Value:** **6.77 years** (N = 52 NPL-linked pairs)

> Photonic logic and optical-computing research takes a median of 6.77 years from
> publication to appear cited in a US patent filing — more than 3x the lag seen in the
> fastest cluster (c_121, 1.92 yr). This variation across families suggests meaningful
> differences in research-to-patent cycle time between sub-domains, though the NPL
> citation mechanism (a patent examiner or applicant citing a paper) is not equivalent
> to proof of causation.

**Reproducible query:**
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links
FROM main_marts.mart_gap
WHERE cluster_id = 'c_188';
-- Returns: c_188 | Photonic Logic Gates and Optical Computing | 6.77 | 52
```

---

## Finding 3 — IP concentration: Exposure Apparatus and Movable Device Manufacturing

**Cluster:** `c_10` — Exposure Apparatus and Movable Device Manufacturing
**Metric:** HHI over primary US patent assignees
**Value:** **HHI = 1.0** (1 assignee holds all 11 patents in this cluster; monopoly concentration)

> A single assignee holds 100% of US patents in this lithography-exposure-apparatus
> cluster (HHI = 1.0, N = 11 patents) — the extreme end of US patent concentration
> within the three scope technology families. Unlike a prior version of this finding,
> this cluster does have co-located paper activity (24 papers, 32 institutions), so the
> concentration is not simply an artifact of a patent-only cluster.

**Reproducible query:**
```sql
SELECT cluster_id, tagline, hhi, n_assignees, n_patents, n_oa_institutions, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_10';
-- Returns: c_10 | Exposure Apparatus and Movable Device Manufacturing | 1.0 | 1 | 11 | 32 | 24
```

**Caveat:** N = 11 patents is just above the ≥10 reportability floor — read as indicative, not conclusive, same caution as the prior version of this finding.

---

## Finding 4 — Concentration gap: Neuromorphic Synaptic Devices

**Cluster:** `c_141` — Neuromorphic Synaptic Devices
**Metric:** Institution breadth (paper side) vs assignee concentration (patent side)
**Value:** Research spans **850 distinct research institutions** (sub-org level, 1,148 papers);
US patenting concentrates in **6 assignees** (11 patents, **HHI = 0.34**)

> Research on neuromorphic synaptic devices is produced by 850 distinct research
> institutions globally (sub-org level — e.g. IBM Research Almaden and IBM Research
> Zürich are counted separately; 1,148 English-language papers, 2012–2025). Yet US
> patent filings in this cluster are concentrated in just 6 assignees, with a
> Herfindahl-Hirschman Index of 0.34 — above the 0.25 threshold typically considered
> "highly concentrated." The gap between breadth of research activity and narrowness
> of US patent ownership illustrates the core dynamic this atlas tracks.

**Reproducible query:**
```sql
SELECT cluster_id, tagline, hhi, n_assignees, n_patents,
       n_oa_institutions, n_research_orgs, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_141';
-- Returns: c_141 | Neuromorphic Synaptic Devices | 0.34 | 6 | 11 | 850 | 778 | 1148
```

**Caveat:** N = 11 patents is just above the ≥10 reportability floor — read as indicative, not conclusive.

---

## Family-level headline numbers (`mart_family`, 3 families — see ARCHITECTURE.md §Data model)

| Family | Papers | Patents | Patent share | Weighted median lag |
|---|---|---|---|---|
| EUV Lithography | 5,830 | 5,230 | 47.3% | 4.24 yr |
| Silicon Photonics | 47,595 | 3,362 | 6.6% | 3.76 yr |
| Neuromorphic & In-Memory Compute | 31,570 | 13,112 | 29.3% | 2.76 yr |

Note: these 3 families are the original Part 0 scope families (Silicon Photonics includes
lasers; Neuromorphic & In-Memory Compute is merged) — not the 5-way split used in an
earlier version of this project's UI design. See `MEMORY.md` for why.

---

## Summary table

| Finding | Cluster | Metric | Value | N |
|---|---|---|---|---|
| Fastest NPL lag | c_121 In-Memory Computing with Resistive Devices | citation lag | **1.92 yr** | 21 |
| Slowest NPL lag | c_188 Photonic Logic Gates and Optical Computing | citation lag | **6.77 yr** | 52 |
| Extreme concentration | c_10 Exposure Apparatus and Movable Device Mfg | HHI | **1.00** (1 assignee) | 11 patents |
| Broad research, narrow patent | c_141 Neuromorphic Synaptic Devices | gap | **850 institutions / 6 assignees / HHI=0.34** | 11 patents |
