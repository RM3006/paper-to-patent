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
(Findings 1–2, and the family table's median lag) moved; Findings 3–4 (HHI-based) are
unaffected.

**Family-level rebuild (2026-07-12)**: `mart_family` and `mart_competitive` were rebuilt off
each document's own 5-way `family_id` (`euv` / `lasers` / `si_photonics` / `neuromorphic` /
`in_memory`, from `fact_patent_filing.family_id` / `fact_publication.family_id`) rather than
the 3-way cluster-label rollup (`seed_cluster_family`) the original Part 6 build used. The
3-way scheme still exists and still colours the Technology Landscape map — a cluster is a
group of documents that need not share one family — but every family-level count, share, and
leaderboard now reads the document-level column instead. `patent_share` was redefined at the
same time: it is a family's share of the *total US patent pool* (patents only; papers do not
appear in the ratio), not a research-to-patent conversion rate. See `mart_family.sql` and
`ARCHITECTURE.md` §Data model ("two-tier family tagging"). The **cluster-level** Findings 1–4
below are unaffected — they read `mart_gap`, whose clustering realization and formulas have
not changed since the 2026-07-08 snapshot (re-verified against live MotherDuck prod on
2026-07-14: all four findings' numbers hold).

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

**Cluster:** `c_147` — In-Memory Computing with Resistive Devices
**Metric:** Median NPL-linked citation lag
**Value:** **1.47 years** (median publication-to-filing interval across 49 confirmed NPL-linked paper→patent pairs)

> Research linked to resistive-memory in-memory-computing patents appears cited in a US
> patent filing a median of 1.47 years after publication — the fastest confirmed lag among
> the clusters with enough NPL-linked pairs to report (N ≥ 20), after the 2026-07-10 hybrid
> NPL-linkage refresh (see snapshot note above). Anchored on the citing patent's filing date,
> not its grant date. The cluster has 311 co-located research institutions against 45
> patents and 23 assignees — a broad research base feeding a comparatively narrow patent
> footprint. The next-closest reportable clusters are `c_67` "Deep Learning Neural Network
> Processing" (1.90 years, N = 20 — right at the reportability floor) and `c_144` "Memristor
> Devices and Circuit Modeling" (1.91 years, N = 33).

**Reproducible query** (from `main_marts.mart_gap`):
```sql
SELECT cluster_id, tagline, npl_median_lag_years, npl_n_links,
       n_oa_institutions, n_assignees, n_patents, n_papers
FROM main_marts.mart_gap
WHERE npl_n_links >= 20
ORDER BY npl_median_lag_years ASC
LIMIT 3;
-- Top row: c_147 | In-Memory Computing with Resistive Devices | 1.47 | 49 | 311 | 23 | 45 | 356
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

## Family-level headline numbers (`mart_family`, 5 document-level families — see ARCHITECTURE.md §Data model)

| Family | Papers | Patents | Patent share | Median NPL lag | NPL links | Top assignee (by patents) |
|---|---|---|---|---|---|---|
| EUV Lithography | 8,411 | 5,623 | 34.2% | 2.97 yr | 553 | ASML (1,435 patents) |
| Lasers | 17,041 | 697 | 4.2% | 3.34 yr | 448 | Gigaphoton (40 patents) |
| Silicon Photonics | 62,294 | 3,382 | 20.6% | 3.23 yr | 2,963 | GlobalFoundries (210 patents) |
| Neuromorphic | 19,620 | 2,692 | 16.4% | 2.55 yr | 1,707 | IBM (368 patents) |
| In-Memory Compute | 17,447 | 4,028 | 24.5% | 2.72 yr | 1,293 | Micron Technology (681 patents) |

*(Verified against live MotherDuck prod, 2026-07-14. Patent share = family `n_patents` / total
US patents across the 5 families (patents only — papers do not appear in the ratio; see
`mart_family.sql`). Median NPL lag is a TRUE median over every NPL-linked citation in the
family, not a weighted average of per-cluster medians (the mart's `median_lag_years_weighted`
column name is a legacy holdover from the prior cluster-rollup version). "Top assignee" is
computed directly from `fact_patent_filing` joined to `dim_organization`, grouped by family —
it is not a `mart_family` column.)*

Note: this is the **document-level, 5-way** family scheme (`euv` / `lasers` / `si_photonics` /
`neuromorphic` / `in_memory`), each document classified directly from its own CPC prefix
(patents) or OpenAlex topic + keyword tiebreak (papers) — independent of whichever cluster it
algorithmically landed in. It is distinct from the **cluster-level, 3-way** display scheme
(`seed_cluster_family`: `euv` / `silicon_photonics` (includes lasers) / `neuromorphic_in_memory`
(merged) / `mixed`) that colours the Technology Landscape map only. See "Family-level rebuild"
in the snapshot note above and `ARCHITECTURE.md`'s "two-tier family tagging" section for why
both grains coexist.

**Unattributed documents** (no resolvable `family_id`, disclosed separately — never
redistributed into one of the 5): **6,975 of 23,397 patents (29.8%)** — patents whose *primary*
CPC code is outside the six scope subclasses; they entered the corpus via a secondary scope
code in their top-5 classifications. **5,611 of 130,424 institution-resolved papers (4.3%)** —
papers whose primary topic is `T10502` but whose title/abstract keyword tiebreak matched
neither the neuromorphic nor in-memory pattern. (Note `fact_publication`'s grain is
(paper, institution) — its 130,424 distinct papers is smaller than `dim_paper`'s 153,362
because roughly 18% of papers have no OpenAlex-resolved institution at all, consistent with
the ~82% institution-coverage figure recorded at Part 1 ingest; this is a pre-existing data
coverage limit, not new to this family scheme.)

---

## Summary table

| Finding | Cluster | Metric | Value | N |
|---|---|---|---|---|
| Fastest NPL lag | c_147 In-Memory Computing with Resistive Devices | citation lag | **1.47 yr** | 49 |
| Slowest NPL lag | c_117 Memristor-Based True Random Number Generation | citation lag | **5.41 yr** | 31 |
| Extreme concentration | c_2 Lithographic Apparatus and Device Manufacturing | HHI | **1.0** (1 assignee) | 161 patents |
| Broad research, narrow patent | c_155 Memristor-Based Logic and Computing | gap | **478 institutions / 5 assignees / HHI=0.32** | 10 patents |
