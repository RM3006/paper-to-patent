# findings.md — Headline numbers for "The Chips Behind AI"

All numbers here are reproducible by querying the gold marts in `dev.duckdb`.
Exact queries are shown under each finding.

**Caveats applying to all findings:**
- Patent data is US-only (PatentsView). Findings describe US patenting, not global IP capture.
- Paper data is English-language OpenAlex works (topics T11338, T10299, T11429, T10502, 2012–2025).
- "Citation lag" = days from a paper's `publication_date` to the citing patent's `filing_date`
  (from `fact_npl_link`). It is NOT "time to market" or "R&D-to-commercialisation time" — it
  measures how long before published research appears cited in a filed patent.
- HHI is Herfindahl-Hirschman Index over primary assignees of US patents. It is a descriptive
  concentration metric, not a causal or competitive-strategy claim.

---

## Finding 1 — NPL citation lag: Spiking Neuromorphic Neural Networks

**Cluster:** `c_152` — Spiking Neuromorphic Neural Networks
**Metric:** Median NPL-linked citation lag
**Value:** **2.75 years** (median publication-to-filing interval across 248 NPL-linked paper→patent pairs)

> Research on spiking neuromorphic neural networks takes a median of 2.75 years from publication
> before it is cited in a US patent filing. This is measured across 248 confirmed NPL links — papers
> in this cluster explicitly cited in patent references — anchored on each patent's filing date, not
> its grant date.

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links,
       n_oa_institutions, n_research_orgs, n_assignees, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_152';
-- Returns: c_152 | Spiking Neuromorphic Neural Networks | 2.75 | 248 | 2612 | ... | 96 | 5995
```

**Context from mart_gap:**
The same cluster spans 2,612 distinct research institutions globally (sub-org level, source: OpenAlex),
96 distinct US patent assignees, and 5,995 attributed papers. HHI = 0.06, indicating dispersed patent
ownership — the research-to-patent pipeline is distributed rather than captured by a handful of players.

---

## Finding 2 — IP concentration: EUV Lithography apparatus

**Cluster:** `c_53` — Lithographic Apparatus and Device Manufacturing
**Metric:** HHI over primary US patent assignees
**Value:** **HHI = 1.0** (1 assignee holds 155 patents; monopoly concentration)

> In the EUV lithographic apparatus cluster, a single assignee holds 100% of US patents
> (HHI = 1.0, N = 155). This cluster is at the extreme end of US patent concentration
> within the three scope technology families.

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, hhi, n_assignees, n_patents, n_oa_institutions, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_53';
-- Returns: c_53 | Lithographic Apparatus and Device Manufacturing | 1.0 | 1 | 155 | 0 | 0
```

**Note:** `n_oa_institutions = 0` and `n_papers = 0` for this cluster because the UMAP+HDBSCAN
embedding placed all papers about EUV apparatus into neighbouring clusters (e.g. `c_135`, `c_162`,
`c_173`, `c_174`) rather than here. The patents in this cluster have no co-located paper
counterpart in the same cluster — a valid and honest result of the unsupervised clustering.
The concentration finding is therefore stated without the institution-breadth comparison.

---

## Finding 3 — Concentration gap: Neuromorphic Computing with Synaptic Devices

**Cluster:** `c_228` — Neuromorphic Computing with Synaptic Devices
**Metric:** Institution breadth (paper side) vs assignee concentration (patent side)
**Value:** Research spans **610 distinct research institutions** (sub-org level, 762 papers);
US patenting concentrates in **5 assignees** (10 patents, **HHI = 0.40**)

> Research on neuromorphic computing with synaptic devices is produced by 610 distinct
> research institutions globally (sub-org level — IBM Research Almaden and IBM Research Zürich
> are counted separately; 762 English-language papers, 2012–2025). Yet US patent filings
> in this cluster are concentrated in just 5 assignees, with a Herfindahl-Hirschman Index
> of 0.40 — well above the 0.25 threshold typically considered "highly concentrated."
> The gap between breadth of research activity and narrowness of US patent ownership
> illustrates the core dynamic this atlas tracks.

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, hhi, n_assignees, n_patents,
       n_oa_institutions, n_research_orgs, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_228';
-- Returns: c_228 | Neuromorphic Computing with Synaptic Devices | 0.4 | 5 | 10 | 610 | ~580 | 762
```

**Caveat:** n_patents = 10 is at the minimum reportable threshold (≥10). This finding should be
read as indicative rather than conclusive; a larger patent sample would strengthen it.

---

## Finding 4 — Slow-to-patent technology: Optical Semiconductor Waveguide Devices

**Cluster:** `c_234` — Optical Semiconductor Waveguide Devices
**Metric:** Median NPL-linked citation lag
**Value:** **5.27 years** (N = 117 NPL-linked pairs)

> Optical semiconductor waveguide research takes a median of 5.27 years from publication
> to appear cited in a US patent filing — nearly twice the lag seen in neuromorphic computing
> (c_152: 2.75 yr). This variation across families suggests meaningful differences in
> research-to-patent cycle time between domains, though the NPL citation mechanism
> (a researcher citing a paper in a patent) is not equivalent to proof of causation.

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links
FROM main_marts.mart_gap
WHERE cluster_id = 'c_234';
-- Returns: c_234 | Optical Semiconductor Waveguide Devices | 5.27 | 117
```

---

## Summary table

| Finding | Cluster | Metric | Value | N |
|---|---|---|---|---|
| Fastest NPL lag | c_158 In-Memory Computing | citation lag | **2.17 yr** | 96 |
| Typical NPL lag | c_152 Spiking Neuromorphic | citation lag | **2.75 yr** | 248 |
| Slowest NPL lag | c_234 Optical Semiconductor Waveguide | citation lag | **5.27 yr** | 117 |
| Extreme concentration | c_53 EUV Apparatus | HHI | **1.00** (1 assignee) | 155 patents |
| Broad research, narrow patent | c_228 Neuromorphic Synaptic | gap | **610 research institutions (sub-org) / 5 assignees / HHI=0.40** | 10 patents |
