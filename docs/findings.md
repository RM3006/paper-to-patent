# findings.md — Headline numbers for "The Chips Behind AI"

All numbers here are reproducible by querying the marts in MotherDuck (or a local `dev.duckdb` build).
Exact queries are shown under each finding.

**Snapshot**: 2026-07-08 (post patent-scope tightening — the patent filter now requires a
scope CPC code among a patent's **top-5 classifications** (`cpc_sequence` 0–4) rather than at
any position; see `ROADMAP.md` Part 0 and `docs/data_source_manifest.md`. This dropped the
patent corpus from 33,578 to **23,397** (−30.3%) and triggered a full Part 5 re-cluster.
Corpus is now **176,759 docs** (153,362 papers + 23,397 patents), **227 named clusters**,
3-way cluster family scheme). Cluster IDs are not stable across re-clustering runs — every
finding below cites the cluster's current tagline alongside its ID; if this doc is refreshed
after a future re-cluster, cite fresh IDs rather than assuming these persist.

**NPL linkage refresh (2026-07-10)**: `fact_npl_link` moved to a hybrid source — the Marx &
Fuegi "Reliance on Science" dataset (CC-BY-4.0) now supplies edges for any patent it covers at
all (vintage caps ~early-2023 grants), with our own DOI + fuzzy-title matcher filling only the
patents M&F has zero coverage of (`link_source` column; see `ARCHITECTURE.md` §7 and
`docs/data_source_manifest.md`). Total links rose from ~6,139 to **9,025** and distinct linked
patents from ~2,973 to **3,528**. Clustering itself is unchanged — only NPL-lag numbers below
(Findings 1–2, and the family table's weighted median lag) moved; Findings 3–4 (HHI-based) are
unaffected.

**Caveats applying to all findings:**
- Patent data is US-only (PatentsView). Findings describe US patenting, not global IP capture.
- Paper data is English-language OpenAlex works (topics T11338, T10299, T11429, T10502, 2012–2025).
- "Citation lag" = days from a paper's `publication_date` to the citing patent's `filing_date`
  (from `fact_npl_link`). It is NOT "time to market" or "R&D-to-commercialisation time" — it
  measures how long before published research appears cited in a filed patent.
- HHI is Herfindahl-Hirschman Index over primary assignees of US patents. It is a descriptive
  concentration metric, not a causal or competitive-strategy claim.

---

## Finding 1 — Fastest NPL citation lag: In-Memory Computing with Resistive Memory

**Cluster:** `c_147` — In-Memory Computing with Resistive Memory
**Metric:** Median NPL-linked citation lag
**Value:** **1.47 years** (median publication-to-filing interval across 49 confirmed NPL-linked paper→patent pairs)

> Research linked to resistive-memory in-memory-computing patents appears cited in a US
> patent filing a median of 1.47 years after publication — the fastest confirmed lag among
> the clusters with enough NPL-linked pairs to report (N ≥ 20), after the 2026-07-10 hybrid
> NPL-linkage refresh (see snapshot note above). Anchored on the citing patent's filing date,
> not its grant date. The cluster has 311 co-located research institutions against 45
> patents and 23 assignees — a broad research base feeding a comparatively narrow patent
> footprint. Under the prior (matcher-only) NPL source this cluster did not clear the N ≥ 20
> reportability floor at all; `c_71` "Neural Networks and Reinforcement Learning" held this
> spot before (now 2.04 years, N = 213 — still fast, but no longer fastest) and `c_68`
> "Neuromorphic Synapses and Neural Devices" (now 2.12 years, N = 67) is close behind.

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links,
       n_oa_institutions, n_assignees, n_patents, n_papers
FROM main_marts.mart_gap
WHERE npl_n_links >= 20
ORDER BY npl_median_lag_years ASC
LIMIT 3;
-- Top row: c_147 | In-Memory Computing with Resistive Memory | 1.47 | 49 | 311 | 23 | 45 | 356
```

---

## Finding 2 — Slowest NPL citation lag: Memristor-Based True Random Number Generation

**Cluster:** `c_117` — Memristor-Based True Random Number Generation
**Metric:** Median NPL-linked citation lag
**Value:** **5.41 years** (N = 31 NPL-linked pairs)

> Memristor-based random-number-generation research takes a median of 5.41 years from
> publication to appear cited in a US patent filing — still the slowest reportable cluster
> after the 2026-07-10 hybrid NPL-linkage refresh (down from 6.23 years / N = 24 under the
> prior matcher-only source — more confirmed links pulled the median in, but this cluster
> remains the clear outlier: roughly 3.7x the lag of the fastest cluster). This same
> cluster (same tagline) has now topped the "slowest" finding across three consecutive
> snapshots under different cluster IDs and NPL sources — a reassuring sign that the
> slowest-moving sub-domain is stable, not an artifact of any one clustering or matching
> run. The NPL citation mechanism (an examiner or applicant citing a paper) is not proof of
> causation.

**Reproducible query:**
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links
FROM main_marts.mart_gap
WHERE npl_n_links >= 20
ORDER BY npl_median_lag_years DESC
LIMIT 1;
-- Returns: c_117 | Memristor-Based True Random Number Generation | 5.41 | 31
```

---

## Finding 3 — Extreme IP concentration: Lithographic Apparatus and Device Manufacturing

**Cluster:** `c_2` — Lithographic Apparatus and Device Manufacturing
**Metric:** HHI over primary US patent assignees
**Value:** **HHI = 1.0** (a single assignee holds all 161 patents in this cluster — a true monopoly)

> A single assignee holds **every** US patent in this lithographic-apparatus cluster
> (HHI = 1.0, N = 161 patents) — the most concentrated reportable cluster in the snapshot,
> and a genuine monopoly (unlike the prior cycle, whose top cluster reached only HHI = 0.96).
> This is a patent-dominant cluster with no co-located paper activity (0 papers, 0 mapped
> research institutions) — read it as a captured patent thicket, not a "broad research,
> narrow patent" case. That contrast is Finding 4 below.

**Reproducible query:**
```sql
SELECT cluster_id, tagline, hhi, n_assignees, n_patents, n_oa_institutions, n_papers
FROM main_marts.mart_gap
WHERE n_patents >= 10
ORDER BY hhi DESC
LIMIT 1;
-- Returns: c_2 | Lithographic Apparatus and Device Manufacturing | 1.0 | 1 | 161 | 0 | 0
```

---

## Finding 4 — Concentration gap: Memristor-Based Logic and Computing

**Cluster:** `c_155` — Memristor-Based Logic and Computing
**Metric:** Institution breadth (paper side) vs assignee concentration (patent side)
**Value:** Research spans **478 distinct research institutions** (634 papers);
US patenting concentrates in **5 assignees** (10 patents, **HHI = 0.32**)

> Research on memristor-based logic and computing is produced by 478 distinct research
> institutions globally (sub-org level — e.g. IBM Research divisions counted separately;
> 634 English-language papers, 2012–2025). Yet US patent filings in this cluster concentrate
> in just 5 assignees, with a Herfindahl-Hirschman Index of 0.32 — above the 0.25 threshold
> typically considered "highly concentrated." The gap between the breadth of research
> activity and the narrowness of US patent ownership illustrates the core dynamic this atlas
> tracks.

**Reproducible query:**
```sql
SELECT cluster_id, tagline, hhi, n_assignees, n_patents,
       n_oa_institutions, n_research_orgs, n_papers
FROM main_marts.mart_gap
WHERE cluster_id = 'c_155';
-- Returns: c_155 | Memristor-Based Logic and Computing | 0.32 | 5 | 10 | 478 | 446 | 634
```

**Caveat:** N = 10 patents is exactly at the ≥10 reportability floor — read as indicative,
not conclusive. `c_180` "Quantum Photon Sources and Entanglement" shows an even wider gap
(715 institutions / 7 assignees / 14 patents / HHI 0.36) but sits at the tangential edge of
the scope, so the on-domain memristor cluster is used here as the headline.

---

## Family-level headline numbers (`mart_family`, 3 headline families + Mixed — see ARCHITECTURE.md §Data model)

| Family | Clusters | Papers | Patents | Patent share | Weighted median lag | Top assignee |
|---|---|---|---|---|---|---|
| EUV Lithography | 25 | 5,159 | 3,558 | 40.8% | 2.70 yr | TSMC |
| Silicon Photonics | 125 | 45,798 | 2,267 | 4.7% | 3.49 yr | IBM |
| Neuromorphic & In-Memory Compute | 58 | 26,092 | 4,289 | 14.1% | 2.61 yr | Micron Technology |
| Mixed *(excluded from headline charts)* | 19 | 927 | 3,041 | 76.6% | 3.12 yr | ASML |

*(2026-07-10 snapshot. Patent share = family n_patents / (family n_papers + family n_patents).
Clustering realization unchanged from the 2026-07-08 build (paper/patent counts and shares are
identical) — only the weighted median lag moved, following the hybrid NPL-linkage refresh
described in the snapshot note above.)*

Note: each cluster is assigned to a family by `seed_cluster_family` only when a single family
is **>= 80% of the cluster's family-resolvable documents AND those resolvable documents are
>= 50% of the cluster** (a confidence floor, added 2026-07-08). Clusters that genuinely span
two families or are mostly off-scope go to **Mixed** — it holds the 19 such clusters, which is
why its patent count (3,041) is high relative to its papers (mostly patent-heavy off-primary-CPC
clusters like semiconductor-fabrication and IC-testing). The four rows sum to 13,155 patents
(the non-noise clustered patents); the remaining ~10.2k of `dim_patent` (23,397) sit in
`c_noise` (unclustered). The three headline families hold 10,114; Mixed separates out 3,041 that
were previously force-attributed to a headline family. See `docs/cluster_label_review.md`.

Note: these 3 families are the original Part 0 scope families (Silicon Photonics includes
lasers; Neuromorphic & In-Memory Compute is merged) — not the 5-way split used in an
earlier version of this project's UI design. See `MEMORY.md` for why.

---

## Summary table

| Finding | Cluster | Metric | Value | N |
|---|---|---|---|---|
| Fastest NPL lag | c_147 In-Memory Computing with Resistive Memory | citation lag | **1.47 yr** | 49 |
| Slowest NPL lag | c_117 Memristor-Based True Random Number Generation | citation lag | **5.41 yr** | 31 |
| Extreme concentration | c_2 Lithographic Apparatus and Device Manufacturing | HHI | **1.0** (1 assignee) | 161 patents |
| Broad research, narrow patent | c_155 Memristor-Based Logic and Computing | gap | **478 institutions / 5 assignees / HHI=0.32** | 10 patents |
