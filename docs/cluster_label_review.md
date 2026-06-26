# Cluster Label Review — Part 5

Spot-check of Claude Haiku-generated technology cluster labels against their member documents.

**Run date:** 2026-06-26  
**Corpus:** 197,456 docs (163,878 papers + 33,578 patents)  
**Clusters produced:** 303 named clusters + `c_noise`  
**Noise rate:** 42.1% (83,182 docs unclustered by HDBSCAN)  
**Model version:** 2026-06-26

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

---

## Spot-check results

> **Status:** Complete — production run 2026-06-26. **Score: 14 / 15 ✅**

Clusters selected: largest 13 non-noise clusters by `doc_count`, plus c_5 (a known artifact) and c_237 (mid-size silicon photonics).

| # | cluster_id | tagline | Top c-TF-IDF terms (sample) | doc_count | Rating | Notes |
|---|---|---|---|---|---|---|
| 1 | c_152 | Spiking Neuromorphic Neural Networks | spiking, snns, snn, spiking neural, neurons | 8,115 | ✅ | Dominant neuromorphic family; SNN/spike-timing content confirmed |
| 2 | c_56 | Germanium-Tin Photodiode Structures | gesn, ge, sn, si, ge sn | 5,392 | ✅ | GeSn alloy photodetectors; silicon photonics sub-family |
| 3 | c_158 | In-Memory Computing for Neural Networks | cim, dnn, memory, accelerators, sram, inference | 3,917 | ✅ | CIM/SRAM inference accelerators; correct in-memory compute family |
| 4 | c_242 | Resistive Switching Memory Technologies | resistive switching, rram, switching, oxygen, filament | 3,724 | ✅ | RRAM/memristive switching; tight cluster |
| 5 | c_200 | Quantum Photonic Systems and Sources | quantum, photon, photons, entangled, entanglement | 3,242 | ✅ | Quantum photonics; entangled-photon generation confirmed |
| 6 | c_285 | Photonic Crystal Biosensors and Waveguide Sensing | riu, sensor, spr, refractive index, waveguide | 3,079 | ✅ | Refractive-index sensing / photonic biosensors; accurate |
| 7 | c_99 | Vertical Cavity Surface Emitting Lasers | vcsel, vcsels, vertical cavity, surface emitting | 2,933 | ✅ | Pure VCSEL cluster; top terms exact match |
| 8 | c_232 | Memristor-based Neuromorphic Computing | memristor, memristive, memristors, neuromorphic, synaptic | 2,388 | ✅ | Memristor/neuromorphic devices; accurate |
| 9 | c_165 | EUV Chemically Amplified Photoresist | euv, resist, resists, euv lithography, chemically amplified, pag | 1,697 | ✅ | **EUV sanity cluster.** Photoresist chemistry sub-family; tagline names EUV recognisably |
| 10 | c_226 | Silicon Photonic Modulators | modulator, modulators, mzm, mach zehnder | 1,638 | ✅ | Mach-Zehnder modulator family; tight silicon photonics cluster |
| 11 | c_197 | Lithium Niobate Photonic Modulators | niobate, lithium niobate, lnoi, tfln | 1,457 | ✅ | LNOI / thin-film LN modulators; accurate and specific |
| 12 | c_171 | EUV Lithography and OPC Optimization | cd, opc, mask, euv, cdu, ilt | 1,348 | ✅ | OPC/ILT mask optimization for EUV; correctly named |
| 13 | c_174 | EUV Mask Defect Inspection and Correction | euv, mask, euv mask, euv lithography, absorber, inspection | 973 | ✅ | EUV mask inspection and repair; accurate |
| 14 | c_5 | Hybrid Volatile-Nonvolatile Memory Systems | ochre, lib uchicago, org ochre, http pi, pi lib | 1,000 | ❌ | **Artifact cluster.** Top terms are URL/library-catalog strings (OCHRE database at U Chicago), not scientific content. Haiku label is hallucinated from garbage input. |
| 15 | c_237 | Optical Phased Array Beam Steering | opa, optical phased, phased, steering, beam steering | 985 | ✅ | OPA LiDAR beam-steering; accurate |

**Score: 14 / 15 (93.3%) ✅ — passes the ≥ 13/15 exit criterion.**

---

## Priority sanity checks

| Technology family | Expected keyword(s) in tagline | Clusters found | Result |
|---|---|---|---|
| EUV Lithography | EUV, lithography, photomask, extreme ultraviolet | c_165 (EUV Chemically Amplified Photoresist), c_171 (EUV Lithography and OPC Optimization), c_174 (EUV Mask Defect Inspection and Correction) | ✅ EUV splits into 3 coherent sub-families, each with "EUV" in the tagline. Not one monolithic family, but each sub-family is correctly named. Acceptable for a 303-cluster model. |
| Silicon Photonics | photonic, silicon photon, waveguide, optical | c_226 (Silicon Photonic Modulators), c_197 (Lithium Niobate Photonic Modulators), c_248 (Silicon Photonic Optical Switching), c_295 (Silicon Photonic Grating Couplers), c_285 (Photonic Crystal Biosensors), c_267 (Integrated Photonic Spectrometers) | ✅ Silicon photonics is well-covered across device-type sub-clusters; all taglines name the technology recognisably. |
| Neuromorphic / In-Memory | memristor, neuromorphic, synaptic, in-memory | c_152 (Spiking Neuromorphic Neural Networks), c_158 (In-Memory Computing for Neural Networks), c_232 (Memristor-based Neuromorphic Computing), c_193 (Optoelectronic Synaptic Neuromorphic Devices), c_228 (Neuromorphic Computing with Synaptic Devices) | ✅ Strong coverage; largest single cluster (c_152, 8,115 docs) is neuromorphic. All taglines correctly named. |

---

## Noise cluster

`c_noise` receives the fixed label "Frontier / Unclustered" — not reviewed against members.

**Noise rate: 42.1% (83,182 / 197,456 docs).** This exceeds the 30% warning threshold in the template. Likely causes:
- The corpus spans three broad technology families with genuinely diffuse boundary documents (e.g. general semiconductor physics papers).
- UMAP spectral initialisation failed and fell back to random init (eigengap warning); this can produce a more fragmented embedding layout, pushing more points into noise.
- `min_cluster_size=50` is conservative for a 303-cluster result; lowering it would absorb more noise but produce smaller, noisier clusters.

**Recommendation for Part 7 / re-run:** Consider `min_cluster_size=30` or `min_samples=5` tuning if the UI benefit of capturing more documents outweighs label quality risk. Not blocking for Part 6.

---

## Known artifact cluster

**c_5** ("Hybrid Volatile-Nonvolatile Memory Systems", 1,000 docs) consists of documents whose text content was dominated by bibliographic metadata strings (OCHRE library catalog URLs from U Chicago). The sentence-transformer encoded these strings as a coherent cluster, and Haiku produced a plausible-sounding but hallucinated label. 

This cluster will be visible in the UI as a low-signal outlier. Mitigation options for Part 7: filter documents where the majority of tokens are URL-like strings before embedding, or exclude clusters whose top c-TF-IDF terms contain no recognisable scientific vocabulary.
