# Cluster Label Review — Part 5

Spot-check of Claude Haiku-generated technology cluster labels against their member documents.

**Current run date:** 2026-07-08 (patent-scope tightening: the patent filter now requires a scope CPC code among a patent's **top-5** classifications rather than at any position — patent corpus 33,578 → 23,397, −30.3% — followed by a from-scratch Part 5 re-cluster. Papers unchanged. See `ROADMAP.md` Part 0, `docs/data_source_manifest.md`, and `MEMORY.md`.)
**Current corpus:** 176,759 docs (153,362 papers + 23,397 patents). `dim_paper`/`dim_patent` null-`cluster_id` count = 0 for both, confirmed on dev and MotherDuck prod. The `excluded_documents` snapshots were cleared before the pre-embedding build this time, so the orphan bug from 2026-07-06 did not recur and only one ML cycle was needed.
**Current clusters produced:** 227 named clusters + `c_noise`
**Current noise rate:** 41.1% overall (72,573/176,759) — within the already-characterized UMAP/HDBSCAN run-to-run noise band (see MEMORY.md's "UMAP non-determinism confirmed" entry), not a regression.
**Model version:** 2026-07-08

**Family confidence floor + clustering freeze (added 2026-07-08, session 2).** Two changes on top of this same clustering realization (the clusters themselves are unchanged — only the family label and the recompute policy changed):
- **'Mixed' family floor** — `seed_cluster_family` now labels a cluster with a real family only when a single family is ≥ 80% of its family-resolvable documents AND those resolvable docs are ≥ 50% of the cluster; otherwise `family_id='mixed'`. **19 of 227 clusters** resolve to Mixed: genuinely two-family (e.g. `c_32` "EUV Free Electron Laser Systems", `c_26`/`c_29` RRAM split silicon/memory) or mostly off-scope (`c_45` "Transformer Models for Vision and Language", `c_77` "Machine Learning Signal Processing Methods", `c_30` "Academic Publishing and Conference Research", `c_47` "Power System Load and Distribution Control"). This replaces the old force-assignment where a 37%-plurality cluster still got a confident family colour. Clean single-technology clusters that are merely patent-heavy (e.g. `c_41` "Cross-Point Memory Arrays", 99% in-memory among its resolvable docs) correctly keep their family. `mixed` is excluded from UI headline charts.
- **Clustering freeze** — this realization is now stamped with a `corpus_signature` (`93e1ad8ccf8265e6`); re-running `document_clusters` on the same corpus reuses it rather than reshuffling every `cluster_id` (which is what previously invalidated this review on each rerun). See ARCHITECTURE.md §8.

**Exit criterion (ROADMAP Part 5):** ≥ 13 / 15 spot-checked labels rated accurate — i.e. a human reviewer agrees the tagline fits the dominant technology of the cluster.

**Rating scale:**
- ✅ Accurate — tagline clearly names the dominant technology in the cluster
- ⚠️ Partial — tagline is related but too broad or misses the dominant thread
- ❌ Inaccurate — tagline does not match the members

---

## How to reproduce this review

After the Part 5 ML assets have been materialised (`document_embeddings` → `document_clusters` → `cluster_labels`), run the following query in `dev.duckdb` to sample clusters for review:

```sql
-- Sample representative documents per cluster for spot-check
SELECT
    cl.cluster_id,
    cl.tagline,
    cl.summary_friendly,
    fdc.doc_id,
    fdc.doc_type,
    CASE fdc.doc_type
        WHEN 'paper'  THEN dp.title
        WHEN 'patent' THEN dpat.title
    END AS title
FROM main_marts.dim_technology_cluster cl
JOIN main_marts.fact_document_cluster fdc USING (cluster_id)
LEFT JOIN main_marts.dim_paper dp    ON fdc.doc_type = 'paper'  AND dp.work_id   = fdc.doc_id
LEFT JOIN main_marts.dim_patent dpat ON fdc.doc_type = 'patent' AND dpat.patent_id = fdc.doc_id
WHERE cl.cluster_id != 'c_noise'
QUALIFY ROW_NUMBER() OVER (PARTITION BY cl.cluster_id ORDER BY fdc.doc_id) <= 5
ORDER BY cl.cluster_id, fdc.doc_type, fdc.doc_id;
```

**Note on sampling:** ordering by `doc_id` tends to return patents before papers for mixed clusters (patent IDs are numeric, sort differently from OpenAlex `W...` IDs) — for two clusters below, the patent-only sample looked weaker than the cluster's real content until paper-side samples were pulled separately. Sample both `doc_type`s before rating a cluster, not just the first 5 rows.

---

## Spot-check results (current, 2026-07-08)

> **Status:** Complete — patent-scope tightening + full re-cluster, 2026-07-08. **Score: 14 / 15 (93.3%) ✅.**

Clusters selected: largest 13 non-noise clusters by `doc_count`, plus 2 mid-size picks (`c_1`, `c_100`, 300–900 docs) for size diversity. The residual generic-ML noise cluster (`c_77`) is the 11th-largest cluster this cycle, so it fell naturally into the largest-13 sample — not a cherry-picked failure.

| # | cluster_id | tagline | doc_count | Rating | Notes |
|---|---|---|---|---|---|
| 1 | c_102 | Spiking Neural Networks & Neuromorphic Computing | 8,344 | ✅ | Terms (spiking, snns, neurons, spike, neuromorphic, synaptic, brain, plasticity) tight; titles all genuine SNN/neuromorphic |
| 2 | c_175 | Resistive Random Access Memory Devices | 3,630 | ✅ | RRAM/resistive-switching/filament/oxygen-vacancy terms and titles consistent |
| 3 | c_96 | EUV Lithography Masks and Patterning | 3,070 | ✅ | EUV mask/OPC/ILT/absorber/defect terms; specific and accurate |
| 4 | c_128 | In-Memory Computing for Neural Networks | 3,020 | ✅ | CIM/PIM/ReRAM/MAC accelerator terms; titles (processing-in-sensor, ReRAM ML training) match cleanly |
| 5 | c_222 | Photonic Waveguide Biosensors | 2,859 | ✅ | RIU/SPR/refractive-index biosensor terms and titles throughout |
| 6 | c_107 | Vertical Cavity Surface Emitting Lasers | 2,567 | ✅ | Pure VCSEL cluster; terms and titles all VCSEL |
| 7 | c_83 | Strained GeSn Alloy Engineering | 2,101 | ✅ | GeSn/Ge/Sn/strain/tensile terms; titles all Ge–Sn alloy epitaxy/strain engineering |
| 8 | c_192 | Microring Resonator Photonic Devices | 2,069 | ✅ | Microring/ring-resonator/FSR terms; titles all silicon-photonic micro-ring devices |
| 9 | c_130 | Distributed Feedback Laser Systems | 2,021 | ✅ | DFB/DBR/external-cavity/linewidth terms; titles all tunable/DFB semiconductor lasers |
| 10 | c_34 | Event-Based Neuromorphic Vision Systems | 1,970 | ✅ | Event-camera/DVS terms; titles all event-based vision/sensing |
| 11 | c_77 | Machine Learning Signal Processing Methods | 1,654 | ❌ | **The residual generic-ML noise cluster** — 94.5% patents (1,564), 68% with an off-family primary CPC. Sample titles: *"Comparison of biometric identifiers in memory"*, *"Third-party analytics service with virtual assistant interface"*, *"Mini-lysimeter Hardware"*, generic *"Method for data processing and related products"*. Terms are pure boilerplate (learning, machine learning, systems methods, apparatus, storage medium). This is the reduced-but-persistent successor to the old `c_15`/`c_70` catch-all; see "Known issues" below. |
| 12 | c_219 | Whispering Gallery Mode Microresonators | 1,601 | ✅ | WGM/microsphere/gallery-mode terms; titles all WGM microresonators/microbottle sensors |
| 13 | c_98 | EUV Chemically Amplified Resist Materials | 1,570 | ✅ | EUV resist/PAG/LER/LWR terms; titles all EUV photoresist chemistry |
| 14 | c_1 | Silicon Photonic Integrated Circuits | 546 | ✅ | Titles genuinely silicon photonics (CMOS modulators, silicon photonics for exascale, microring lasers). **But** top terms are contaminated with publishing-webpage boilerplate (`citation`, `mendeley add`, `save article`, `share linkedin`, `bibtex endnote`) — tagline accurate, c-TF-IDF vocabulary polluted. See "Known issues". |
| 15 | c_100 | High-Speed Optical Receiver Amplifiers | 344 | ✅ | TIA/transimpedance/receiver/PAM-4 terms; titles all high-speed optical-receiver front-ends |

**Score: 14 / 15 (93.3%) ✅ — passes the ≥ 13/15 exit criterion. The single failure (`c_77`) is the residual, expected noise cluster; `c_1` passes on tagline but is flagged for term contamination.**

### What's different from the 2026-07-06 run

- **The generic-ML noise cluster is much reduced but not eliminated.** The 2026-07-06 catch-all `c_70` "Neural Network Learning Systems" (6,895 docs) has shrunk ~76% to `c_77` "Machine Learning Signal Processing Methods" (1,654 docs) after the patent-scope tightening. The worst offenders — buried-mention patents (music, gaming, VFX papers alongside off-domain patents) — were dropped from the corpus entirely by the top-5 CPC rule. What remains in `c_77` is off-domain *patents* (biometrics, finance, analytics, recommendation systems) that carry a prominent neural-net CPC code in their top-5, so the top-5 rule keeps them. This is the known, disclosed limit of the top-5 (vs primary-only) rule — see "Known issues carried forward".
- **New term-contamination instance (`c_1`):** publishing-webpage boilerplate (`citation`, `mendeley add`, `share linkedin`) leaked into the c-TF-IDF vocabulary for a silicon-photonics cluster. Same class as the prior run's XML-boilerplate contamination in `c_180`. Tagline unaffected; term list polluted.
- No cluster this cycle showed the placeholder-abstract/OCHRE-URL artifact pattern — the embedding quality gate continues to hold.

---

## Priority sanity checks (current, 2026-07-06)

| Technology family | Clusters found (of the 15 sampled) | Result |
|---|---|---|
| EUV Lithography | c_125 (EUV Lithography Mask Optimization), c_119 (EUV Chemically Amplified Resist Materials) | ✅ Present and correctly named among the largest clusters |
| Silicon Photonics | c_123 (Germanium Silicon Photodiode Technology), c_147 (Tunable Semiconductor Lasers), c_234 (Photonic Waveguide Biosensors), c_59 (VCSEL), c_78 (Terahertz Generation and Waveguide Technology), c_218 (Silicon Photonic Optical Modulators) | ✅ Broad, specific coverage across device sub-types, consistent with prior runs |
| Neuromorphic / In-Memory | c_131 (Spiking Neuromorphic Neural Networks, the largest cluster overall at 8,176 docs), c_181 (Resistive Switching Memory Devices), c_154 (In-Memory Computing for Neural Networks), c_112 (Event-Based Vision), c_180 (RRAM), c_188 (Memristor-Based Neural Networks) | ✅ Strong coverage; largest single cluster is neuromorphic, matching prior runs |

---

## Cluster purity distribution by family (2026-07-04 methodology snapshot — not re-run 2026-07-06)

**Not regenerated this cycle.** The numbers below are frozen from the 2026-07-04 analysis against that run's 237 clusters; cluster IDs referenced here (`c_5`, `c_8`, `c_9`, etc.) do **not** correspond to the current (2026-07-06) cluster set — re-clustering reassigns IDs every run (see the caveat at the top of this doc). The `seed_cluster_family.sql` voting logic these numbers validate is unchanged since 2026-07-04, so the *methodology* conclusions (distinct-patent voting, the two genuine EUV↔SiPhotonics and Neuro↔InMemory family blends) likely still hold directionally, but the specific purity percentages and lowest-purity cluster list below should not be cited against the current cluster set. Re-run the vote/purity SQL (see the reproducible-query note at the end of this section) against the fresh `fact_document_cluster` before citing fresh numbers.

Measures how cleanly each cluster's member documents agree with the 3-way family the cluster is tagged with in `seed_cluster_family`. For every non-noise cluster, each member document's own family signal (`primary_cpc` prefix for patents, `primary_topic_id` for papers — the same signal `seed_cluster_family`'s vote uses, not the 5-way `family_id` column, see methodology note below) is compared against the cluster's assigned tag. Purity = share of a cluster's resolvable documents that agree with the tag.

**Methodology fixes made while producing this analysis:**
1. **Voting was row-level, not document-level.** `seed_cluster_family.sql`'s `patent_votes` CTE voted once per row of `fact_patent_filing`, which is exploded one row per assignee — a 3-assignee patent cast 3 votes, a 1-assignee patent cast 1. Fixed to `select distinct patent_id, primary_cpc` before voting, so every patent counts once regardless of assignee count. **Verified impact: 0 / 237 cluster tags actually flip** between row-level and distinct-patent voting on the current corpus — the bug was real but not currently consequential. Fixed anyway since it's a latent correctness issue that could bite on a future re-cluster.
2. **Resolvability measurement bug (this analysis, not the mart):** the first pass of this purity check derived each document's 3-way family by collapsing the 5-way `family_id` column (`fact_publication`/`fact_patent_filing`), which requires a keyword tie-break to resolve `T10502` papers into neuromorphic vs. in-memory. At the 3-way level that tie-break is unnecessary — `T10502` maps unambiguously to `neuromorphic_in_memory` — so voting directly on `primary_topic_id`/`primary_cpc` instead raised resolvable-document coverage from 88.3% to **92.6%** and eliminated a 1/237 doc-majority-vs-tag mismatch (`c_0`, a 2-document cluster).

### Purity distribution (decile buckets, cluster counts)

| Tag family | 100% | 90-100% | 80-90% | 70-80% | 60-70% | 50-60% | 40-50% | Total |
|---|---|---|---|---|---|---|---|---|
| EUV Lithography | 6 | 22 | 5 | 2 | 5 | 3 | 1 | **44** |
| Silicon Photonics | 41 | 76 | 4 | 2 | 5 | 2 | 0 | **130** |
| Neuromorphic & In-Memory | 18 | 36 | 5 | 2 | 1 | 1 | 0 | **63** |
| Adjacent / Out of Headline | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |

No cluster falls below 40% purity and no cluster defaults to `adjacent` — every non-noise cluster resolves to one of the 3 families via majority vote. Mean purity: EUV 87.0%, Silicon Photonics 96.0%, Neuromorphic/In-Memory 95.5%.

### Doc-weighted confusion matrix (rows = cluster's tag, columns = document's own family, row %)

| Tag ↓ / Actual → | EUV | Silicon Photonics | Neuromorphic/In-Memory |
|---|---|---|---|
| **EUV** | 93.5% | 4.5% | 2.0% |
| **Silicon Photonics** | 0.9% | 98.1% | 1.0% |
| **Neuromorphic/In-Memory** | 1.5% | 1.9% | 96.5% |

Weighted by document count rather than averaged per cluster, overall purity is markedly higher than the per-cluster distribution suggests — most of the impurity concentrates in a small number of small-to-mid clusters, not spread thinly everywhere.

### Which family spills into which (genuine blends — both sides ≥15% share within a cluster)

| Pair | # clusters | Worst offenders |
|---|---|---|
| EUV ↔ Silicon Photonics | 16 | `c_5` "Positive Resist Composition and Patterning" (44.6% euv / 25.0% neuro/in-mem / 30.4% remainder split, lowest-purity cluster overall), `c_8` "EUV Immersion Lithography Manufacturing" (34.7% euv / 50.0% silicon_photonics — genuine plurality for silicon_photonics, not a near-tie), `c_73` "Free Electron Laser Accelerator Systems" (38.0% / 60.6%, N=274) |
| EUV ↔ Neuromorphic/In-Memory | 5 | `c_9` "Resistance Change Memory with Resist Materials" (55.0% / 45.0%), `c_5` (see above), `c_27` "Neuromorphic Processing and Substrate Manufacturing" (57.1% purity, N=210) |
| Silicon Photonics ↔ Neuromorphic/In-Memory | 8 | `c_81` "Organic Semiconductors and Photonic Sensing" (58.2% purity), `c_31` "Resistive Switching and Memory Devices" (56.2% purity), `c_37` "Semiconductor Device Structures and Materials" (73.0% purity) |

`c_5` and `c_8` are each genuine 3-way blends (all three families present at ≥15% share), and both carry EUV-process-chemistry taglines despite one being tagged outside `euv` — the tagline is still an accurate description of the cluster's dominant content (see spot-check row 14 above), the family *tag* is simply a coarser 3-way summary that necessarily loses some of that specificity.

### Lowest-purity clusters overall

| cluster_id | tagline | tag family | purity | N |
|---|---|---|---|---|
| c_5 | Positive Resist Composition and Patterning | euv | 44.6% | 56 |
| c_8 | EUV Immersion Lithography Manufacturing | silicon_photonics | 50.0% | 72 |
| c_9 | Resistance Change Memory with Resist Materials | euv | 55.0% | 40 |
| c_31 | Resistive Switching and Memory Devices | silicon_photonics | 56.2% | 73 |
| c_27 | Neuromorphic Processing and Substrate Manufacturing | euv | 57.1% | 210 |
| c_81 | Organic Semiconductors and Photonic Sensing | neuromorphic_in_memory | 58.2% | 55 |
| c_77 | Projection Exposure Apparatus and Optical Systems | euv | 58.6% | 70 |

**Reproducible query pattern:** vote/purity SQL lives in this doc's git history and job scratch files, not checked into `models/`; the durable artifact is the `seed_cluster_family.sql` fix itself (distinct-patent voting). Re-run by joining `fact_document_cluster` to per-document `primary_cpc`/`primary_topic_id` (not the 5-way `family_id` column) and comparing the per-cluster majority against `seed_cluster_family.family_id`.

---

## Noise cluster

`c_noise` receives the fixed label "Frontier / Unclustered" — not reviewed against members.

**Noise rate: 39.7% papers (60,902/153,362), 40.3% patents (13,548/33,578)** — up from 35.4% in the 2026-07-04 run. Per the confirmed UMAP non-determinism finding (`MEMORY.md`, 2026-07-05: noise swung 51,482–82,175 across repeated fits of *identical* embeddings), this is run-to-run variance in the UMAP/HDBSCAN fit, not a data-quality regression — doc-weighted cluster purity has stayed stable (0.97–0.98) across every arm of that prior investigation regardless of noise-rate swings. Still above the 30% warning threshold in the original template; the same causes likely remain (genuinely diffuse boundary documents between the three broad technology families; `min_cluster_size=50` is conservative for this corpus size).

**Recommendation, unchanged:** re-tuning (`min_cluster_size=30`/`min_samples` or UMAP init) remains a Part 7+ option if map density becomes a UX problem, not a blocker today.

---

## Known issues carried forward

**`c_77` "Machine Learning Signal Processing Methods" — residual generic-ML noise (root cause now identified; partially mitigated 2026-07-08)** (see spot-check row 11). This is the reduced successor to the `c_15`→`c_70` catch-all. **Root cause, now understood:** the old any-position patent-scope filter admitted ~38% of the patent corpus on a *buried* scope CPC code while the patent's headline invention was off-domain (a patent spans ~2.7 CPC subclasses on average; a logistics/biometric/animation patent that tags a neural-net code deep in its list still passed). Those off-domain patents share generic-ML vocabulary ("learning", "apparatus", "systems methods") and collapse into one embedding-space cluster. **Mitigation applied 2026-07-08:** the patent-scope filter now requires a scope code in the **top-5** CPC positions (see `ROADMAP.md` Part 0), which dropped the corpus 33,578 → 23,397 and shrank this cluster ~76% (6,895 → 1,654 docs). **Residual:** ~1,564 patents remain because their scope code *is* prominent (top-5) even though their primary class is off-domain (68% off-family). Fully removing them would require the stricter primary-CPC-only rule (−38% of patents), which was rejected because it would also drop ~21% of genuine in-domain patents whose scope code is prominent-but-not-primary. So `c_77` is an accepted, disclosed residual, not an open bug. `fact_document_cluster` still inner-joins the scoped staging models, so nothing here becomes a map orphan.

**`c_1` "Silicon Photonic Integrated Circuits" — publishing-webpage term contamination** (new, 2026-07-08) — top c-TF-IDF terms include `citation`, `mendeley add`, `save article`, `share linkedin`, `bibtex endnote` alongside genuine silicon-photonics vocabulary. The tagline and member documents are accurate (sampled titles are all real silicon photonics), so labelling correctness is unaffected, but journal-webpage scaffolding text is leaking into some abstracts fed to c-TF-IDF. Same class as the prior run's XML-boilerplate contamination (then `c_180`). Not investigated further — a candidate for an abstract-cleaning step in a future Part 5 pass if it recurs or grows.

**`c_5` / `c_8` family-purity blends** (see purity distribution section above) — `c_5` "Positive Resist Composition and Patterning" (44.6% purity, EUV-tagged) and `c_8` "EUV Immersion Lithography Manufacturing" (50.0% purity, tagged silicon_photonics despite the EUV-sounding name) are both genuine 3-way family blends, not measurement artifacts — verified by direct vote-count inspection. The taglines are accurate descriptions of the clusters' dominant content; the 3-way family *tag* is a coarser summary that loses that specificity by design (see `seed_cluster_family.sql` docstring). Not a bug, just a known limitation of collapsing 237 clusters into 3 headline families — no action planned unless it becomes a UX complaint.

**Resolved:** the 2026-06-26 run's `c_5` artifact (OCHRE library-catalog URL strings, hallucinated label) does not recur in this cluster set — see the embedding quality gate in ARCHITECTURE.md §8 and `MEMORY.md`. Note the cluster ID `c_5` has since been reassigned by re-clustering to unrelated, real content (the "Positive Resist Composition" cluster above) — cluster IDs are not stable across runs, see the caveat at the top of this doc.

**Fixed:** `seed_cluster_family.sql`'s patent-side vote was counting one vote per `fact_patent_filing` row (exploded per assignee) rather than per distinct patent, silently over-weighting multi-assignee patents. Fixed to vote on `distinct patent_id`; verified this changes 0/237 cluster tags on the current corpus, so it was a latent risk rather than an active source of mislabeling — but is now correct for future re-clusters where vote margins may be thinner.
