# Cluster Label Review — Part 5

Spot-check of Claude Haiku-generated technology cluster labels against their member documents.

**Current run date:** 2026-07-04 (post embedding-quality-gate re-cluster)
**Current corpus:** 186,933 docs (153,355 papers + 33,578 patents)
**Current clusters produced:** 237 named clusters + `c_noise`
**Current noise rate:** 35.4% (66,163 docs unclustered by HDBSCAN), down from 42.1% pre-gate
**Model version:** 2026-07-04

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

## Spot-check results (current, 2026-07-04)

> **Status:** Complete — production run 2026-07-04. **Score: 13 / 15 (86.7%) ✅ — passes, but narrower than the prior run's 14/15.**

Clusters selected: largest 13 non-noise clusters by `doc_count`, plus `c_5` (the current single worst-purity cluster from the family-purity measurement, 44.6%) and `c_48` (mid-size, ~800 docs).

| # | cluster_id | tagline | doc_count | Rating | Notes |
|---|---|---|---|---|---|
| 1 | c_42 | Spiking Neural Networks and Neuromorphic Computing | 10,276 | ✅ | Artificial-neuron/spiking-neuromorphic patents throughout; top terms (spiking, snn, neuromorphic) and titles agree cleanly |
| 2 | c_15 | Neural Networks and Machine Learning Systems | 9,485 | ❌ | **New finding.** Patent sample looks plausible (DRAM+ANN, generic ML method claims), but the paper-side sample includes clearly unrelated content: *"ELECTRICAL KITCHEN RANGE CONTROLLED BY PLC"* and *"UNL V Percussion Ensemble Moving Light Lab"* — a kitchen appliance and a music-performance piece, not neural-network research. This reads as a generic/boilerplate catch-all rather than a coherent technology family. |
| 3 | c_91 | Resistive Random Access Memory Technology | 7,487 | ✅ | Tight RRAM/ReRAM cluster; filament formation, read-state verification, low-leakage configuration cells all on-topic |
| 4 | c_133 | EUV Lithography Mask and Process Control | 3,863 | ✅ | EUV mask/OPC/critical-dimension patents; specific and accurate |
| 5 | c_231 | Photonic Crystal Biosensing Systems | 2,969 | ✅ | Photonic-crystal/refractive-index biosensor patents throughout |
| 6 | c_122 | In-Memory Computing for Neural Networks | 2,772 | ✅ | DNN accelerator/quantization patents (ResNet, MobileNet hardware implementations); top terms include "cim" (compute-in-memory), consistent with tagline |
| 7 | c_174 | Whispering Gallery Mode Microresonators | 2,638 | ⚠️ | Top terms strongly WGM-specific, but sample includes 2 clearly adjacent/off-topic patents (ultrasonic biomedical microbubbles, superhydrophobic surface synthesis) alongside 2 on-topic WGM microlaser/resonator patents |
| 8 | c_145 | Vertical Cavity Surface Emitting Lasers | 2,621 | ✅ | Pure VCSEL cluster — matches the same finding from the prior (2026-06-26) review |
| 9 | c_104 | Silicon Germanium Photodetectors | 2,585 | ✅ | GeSn/SiGe photodetector and epitaxial-growth patents; specific and consistent |
| 10 | c_222 | Nonlinear Optical Waveguide Technologies | 2,299 | ✅ | Second-harmonic-generation / nonlinear waveguide patents; 2 of 5 samples are adjacent materials-science patents but the core signal is clear |
| 11 | c_226 | Polymer Optical Waveguides | 2,281 | ✅ | Patent-only sample looked weak/generic; paper-side sample is clean and specific (Er-doped fiber lasing, polymer waveguide amplifiers, photoisomerization couplers, direct-written polymer waveguides) |
| 12 | c_7 | GeSn Strained Alloys for Infrared Optoelectronics | 2,244 | ✅ | Epitaxial GeSn/SiGeSnAs materials and infrared-emitting optoelectronic device patents; specific and consistent |
| 13 | c_198 | Silicon Photonic Optical Modulators | 2,022 | ✅ | Mach-Zehnder/ring modulator patents; matches the prior review's finding for the equivalent cluster |
| 14 | c_5 | Positive Resist Composition and Patterning | 56 (worst-purity cluster, 44.6%) | ✅ | Patent sample is tight and consistent (positive resist composition/patterning process, x5). Low family-purity here is about *family* classification (EUV vs. other), not label accuracy — the tagline correctly names what the cluster actually is. Top terms do show minor publishing-metadata contamination (journal, publisher, articles, page) at low volume — the same pattern behind the 2026-06-26 run's `c_65` artifact, now much smaller and not enough to misdirect the label |
| 15 | c_48 | Memristor-Based Chaotic Dynamical Systems | 796 | ✅ | 4 of 5 papers are specifically about memristor-based chaotic circuits/hyperchaos; 1 stray (an unrelated semantic-web-services paper) |

**Score: 13 / 15 (86.7%) ✅ — passes the ≥ 13/15 exit criterion, but with one genuine new failure (`c_15`) and one partial (`c_174`) worth tracking.**

### What's different from the 2026-06-26 run

- The previously known artifact cluster (`c_5`, then "Hybrid Volatile-Nonvolatile Memory Systems" — OCHRE library-catalog URL strings) is **confirmed gone**; no cluster in this run shows that failure mode. The embedding quality gate (placeholder-abstract / too-short / non-English / version-style-title checks) addressed it directly.
- A **new, different failure mode appeared**: `c_15` is a large (9,485-doc), generically-titled cluster containing clearly unrelated content (a kitchen-appliance patent, a music-performance paper) alongside plausible ML patents. This looks like leftover scope-contamination from an over-broad topic match, not the same placeholder-text mechanism the quality gate targets — the quality gate operates on abstract *quality*, not on-topic-ness, so it was never going to catch this. Worth a closer look before Part 8: check what these documents' `primary_topic_id`/`primary_cpc` actually are, since a coherent, well-labelled cluster with several genuinely off-domain members suggests either a topic-filter gap or a generically-worded set of patent claims that embed close together regardless of subject.

---

## Priority sanity checks (current)

| Technology family | Clusters found (of the largest 13 sampled) | Result |
|---|---|---|
| EUV Lithography | c_133 (EUV Lithography Mask and Process Control) | ✅ Present and correctly named among the largest clusters |
| Silicon Photonics | c_231 (Photonic Crystal Biosensing), c_174 (Whispering Gallery Mode Microresonators), c_104 (Silicon Germanium Photodetectors), c_222 (Nonlinear Optical Waveguide Technologies), c_226 (Polymer Optical Waveguides), c_7 (GeSn Strained Alloys), c_198 (Silicon Photonic Optical Modulators) | ✅ Broad, specific coverage across device sub-types, consistent with the prior run's finding |
| Neuromorphic / In-Memory | c_42 (Spiking Neural Networks and Neuromorphic Computing, the largest cluster overall at 10,276 docs), c_91 (RRAM), c_122 (In-Memory Computing for Neural Networks), c_48 (Memristor-Based Chaotic Dynamical Systems) | ✅ Strong coverage; largest single cluster is neuromorphic, matching the prior run |

---

## Cluster purity distribution by family (2026-07-04, current 237 clusters)

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

**Noise rate: 35.4% (66,163 / 186,933 docs)**, down from 42.1% in the 2026-06-26 run. The drop is attributed to the embedding-quality gate: placeholder/non-English/version-title text had been diffusing the whole embedding space generically, not just forming its own artifact clusters, so removing it tightened the overall point cloud. Still above the 30% warning threshold in the original template; the same causes likely remain in reduced form (genuinely diffuse boundary documents between the three broad technology families; `min_cluster_size=50` is conservative for this corpus size).

**Recommendation, unchanged:** re-tuning (`min_cluster_size=30`/`min_samples` or UMAP init) remains a Part 7+ option if map density becomes a UX problem, not a blocker today.

---

## Known issues carried forward

**`c_15` "Neural Networks and Machine Learning Systems"** (see spot-check row 2 above) — a large, generically-named cluster with confirmed off-domain content. Not yet root-caused. Suggested next step: pull `primary_topic_id`/`primary_cpc` for a larger sample of this cluster's members to determine whether this is topic-filter scope creep (documents that shouldn't be in the corpus at all) or a genuine embedding-space collision between generic ML/software patent boilerplate and our target hardware domains.

**`c_5` / `c_8` family-purity blends** (see purity distribution section above) — `c_5` "Positive Resist Composition and Patterning" (44.6% purity, EUV-tagged) and `c_8` "EUV Immersion Lithography Manufacturing" (50.0% purity, tagged silicon_photonics despite the EUV-sounding name) are both genuine 3-way family blends, not measurement artifacts — verified by direct vote-count inspection. The taglines are accurate descriptions of the clusters' dominant content; the 3-way family *tag* is a coarser summary that loses that specificity by design (see `seed_cluster_family.sql` docstring). Not a bug, just a known limitation of collapsing 237 clusters into 3 headline families — no action planned unless it becomes a UX complaint.

**Resolved:** the 2026-06-26 run's `c_5` artifact (OCHRE library-catalog URL strings, hallucinated label) does not recur in this cluster set — see the embedding quality gate in ARCHITECTURE.md §8 and `MEMORY.md`. Note the cluster ID `c_5` has since been reassigned by re-clustering to unrelated, real content (the "Positive Resist Composition" cluster above) — cluster IDs are not stable across runs, see the caveat at the top of this doc.

**Fixed:** `seed_cluster_family.sql`'s patent-side vote was counting one vote per `fact_patent_filing` row (exploded per assignee) rather than per distinct patent, silently over-weighting multi-assignee patents. Fixed to vote on `distinct patent_id`; verified this changes 0/237 cluster tags on the current corpus, so it was a latent risk rather than an active source of mislabeling — but is now correct for future re-clusters where vote margins may be thinner.
