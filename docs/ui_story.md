# Part 7 UI Design Spec — "The Chips Behind AI"

**Status:** Design locked (2026-06-27). Ready for implementation.

---

## The one-sentence thesis

> Broad science, narrow ownership, measurable lag: the research behind AI chips is global and academic; the patents are few, American, and clustered in a handful of industrial giants — and you can measure exactly how long the journey takes.

---

## Data foundations (Part 6 final numbers)

| Metric | Value |
|---|---|
| Papers in scope | 162,787 (2012–2025, English, OpenAlex) |
| Patents in scope | 33,578 (US only, CPC-matched, filing 2014–2025) |
| NPL citation links | 5,921 (1,091 high/DOI + 4,830 medium/fuzzy) |
| Organisations resolved | 14,209 distinct org_ids |
| Technology clusters | 303 non-noise + c_noise bucket |
| Technology families | 5 headline + 1 adjacent |

---

## Five technology families (presentation rollup)

Source: `mart_family` (aggregates `mart_gap` via `seed_cluster_family`).

| Family | Papers | Patents | Pat% | Med. Lag | Top Patenter | Top Researcher |
|---|---|---|---|---|---|---|
| EUV Lithography | 4,965 | 5,390 | **52%** | 3.03 yr | TSMC | IMEC |
| Silicon Photonics & Optical I/O | 35,389 | 2,396 | 6% | 3.59 yr | GlobalFoundries | Chinese Academy of Sciences |
| Lasers & Light Sources | 8,714 | 388 | 4% | 3.00 yr | Intel | Chinese Academy of Sciences |
| Neuromorphic / Brain-inspired | 13,009 | 1,696 | 11.5% | 2.94 yr | IBM | University of California |
| In-Memory & Emerging Memory | 12,003 | 3,520 | 23% | 2.91 yr | Micron Technology | Tsinghua University |

**Pat%** = n_patents / (n_patents + n_papers). Comparison point: EUV is more patent than paper; Silicon Photonics is the opposite.

**Lag** = weighted median citation lag (paper pub_date → citing patent filing_date, via NPL links). US patents only.

---

## Navigation funnel (4 surfaces)

### Surface 1 — Family overview (front door)
- **Five scorecard tiles** (headline families only; "adjacent" excluded).
- Each tile: family name, paper count, patent count, top patenter, median lag.
- **Primary call-to-action:** "Explore [family]" → Surface 2.
- Secondary CTAs: "Find an organisation" → Surface 3; "Technology map" → Surface 4.
- **Honesty rail:** "US patents only (PatentsView). Links are NPL citations, not causal."
- Source marts: `mart_family`.

### Surface 2 — Family detail
Entered from Surface 1 (one family selected).
- **Asymmetry panel**: research breadth (n_research_orgs) vs patent concentration (n_assignees, HHI). The key contrast: Silicon Photonics has ~4,000 research orgs vs ~400 assignees; EUV has ~1,000 vs ~230. EUV HHI is high (ASML dominance in c_53 = 1.0).
- **Top 10 patenters** (bar chart, doc_count + share). Source: `mart_competitive` side='patent', filtered to family clusters.
- **Top 10 research orgs** (bar chart). Source: `mart_competitive` side='paper'.
- **Citation lag spectrum**: scatter of cluster-level `npl_median_lag_years` (x) vs `npl_n_links` (y), coloured by cluster. Only `npl_reportable = true` clusters shown. Tooltip: cluster tagline, HHI, n_papers, n_patents.
- **Cluster list**: expandable table of all non-noise clusters in family, sorted by doc count. Each row: tagline, n_papers, n_patents, median_lag_years, top patenter.
- Source marts: `mart_gap`, `mart_competitive`, `seed_cluster_family`.

### Surface 3 — Org profile (search/entry)
Entered from search box (any surface) or from Surface 2 leaderboard.
- **Search**: type an org name → fuzzy match against `dim_organization.canonical_name`. Return top 5 matches.
- **Org card**: org name, match_method (shown as badge: "Verified ROR" / "Fuzzy match" / "Seed"), primary_confidence.
- **Output (patents they file)**: patent count per family, top 5 patent clusters, filing year histogram.
- **Intake (papers they cite)**: top 5 cited institutions (via `fact_npl_link`: patents → works → fact_publication → org). Split self-citations vs external.
- **Influence (who cites their papers)**: top 5 orgs filing patents that cite this org's papers.
- **Flagship document**: highest-NPL-link paper (most cited by patents) + highest-patent-count patent.
- Source: `idea_journey` (view), `fact_npl_link`, `mart_competitive`, `dim_organization`.
- **Confidence note**: "Links are NPL citations only — co-occurrence links are not shown here."

### Surface 4 — Technology map (UMAP)
Entered from front door or Surface 2.
- **scattergl** of all 162k+ papers + 33k patents in 2D UMAP space.
- Colour by: family (default) | cluster | doc_type (paper/patent).
- Click a cluster → mini-card: tagline, summary_friendly, n_papers, n_patents, top terms.
- Filter controls: family selector, doc_type toggle, year slider (publication/filing year).
- Noise bucket ("Frontier / Unclustered"): shown as grey dots, labelable separately.
- Source: `fact_document_cluster`, `dim_technology_cluster`, `seed_cluster_family`.

---

## The "trace one idea" narrative (guided tour)

Entry point: Surface 1 footer "See a paper become a patent →"

Story beats (hard-coded to validated high-NPL clusters):
1. **Pick a flagship paper** (e.g. IBM TrueNorth W2138913040, 55 citing patents; or top EUV photoresist paper).
2. Show paper metadata + abstract.
3. Show 5 patents that cited it (from `fact_npl_link`, high confidence), with citation lag.
4. Show assignees of those patents.
5. Show where those assignees sit on the family scorecard.
6. End with: "Across [family], the median journey from paper to patent filing is [X] years."

This is a static/semi-static page backed by `fact_npl_link`, `dim_paper`, `dim_patent`, `dim_organization`.

---

## Key contrasts for the story

| Contrast | EUV | Neuromorphic |
|---|---|---|
| Papers | 4,965 | 13,009 |
| Patents | 5,390 | 1,696 |
| Pat% | **52%** | 11.5% |
| Top patenter HHI | High (ASML, c_53 HHI=1.0) | IBM |
| Median lag | 3.03 yr | **2.94 yr** (fastest) |
| Story | Industrial lock-in; research IS the patent | Open academic frontier catching up quickly |

---

## Data-quality honesty rails (embedded in UI)

- **US patents only**: "PatentsView covers US patents issued by USPTO. EPO/WIPO/CN filings are not represented."
- **NPL links**: "Citation links are extracted from USPTO non-patent-literature reference strings. High-confidence links used a DOI match; medium-confidence used fuzzy title matching. Precision vs Marx & Fuegi gold set: 0.831."
- **Patent filing-year truncation**: "Filing counts after 2019 appear lower because recently filed patents take 2–4 years to be granted and enter PatentsView. The drop does not reflect real decline in activity."
- **Confidence badges on all org matches**: shown in Surface 3 org card.

---

## Mart → UI panel mapping

| UI Surface / Element | Source mart(s) |
|---|---|
| Family scorecard tiles | `mart_family` |
| Family asymmetry panel | `mart_gap` + `seed_cluster_family` |
| Family leaderboard (patenters / researchers) | `mart_competitive` filtered to family |
| Cluster lag spectrum scatter | `mart_gap` (`npl_median_lag_years`, `npl_n_links`, `npl_reportable`) |
| Org profile output/intake/influence | `idea_journey` + `fact_npl_link` + `mart_competitive` |
| Technology map (UMAP scattergl) | `fact_document_cluster` + `dim_technology_cluster` + `seed_cluster_family` |
| Cluster mini-card | `dim_technology_cluster` (tagline, summary_friendly, top_terms) |
| Trace-one-idea page | `fact_npl_link` + `dim_paper` + `dim_patent` + `dim_organization` |

---

## Build order (vertical slice recommendation)

1. **Family scorecard tiles** (Surface 1, read-only, `mart_family`) — tests the full data path from mart to UI.
2. **Technology map** (Surface 4, scattergl, `fact_document_cluster`) — visual hook.
3. **Org search + profile** (Surface 3, `idea_journey`) — highest user interest, differentiator.
4. **Family detail + lag spectrum** (Surface 2) — analytical depth layer.
5. **Trace-one-idea** narrative (guided tour, mostly static) — storytelling capstone.

---

## Open items before UI ships

- [ ] Validate `seed_cluster_family` against Part 0 CPC scope (confirm EUV clusters contain G03F 7/20, SiPhotonics contain G02B/H01S, Neuro contain G06N 3/049).
- [ ] Push rebuilt `mart_family` + `seed_cluster_family` to production R2 Parquet.
- [ ] Investigate c_114 (Samsung Display) in "adjacent" — ensure it doesn't contaminate Lasers family charts.
- [ ] Write Streamlit `apps/ui/` scaffold with `.env.local` R2 read-only credentials.
