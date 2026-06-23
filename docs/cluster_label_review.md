# Cluster Label Review — Part 5

Spot-check of Claude Haiku-generated technology cluster labels against their member documents.

**Exit criterion (ROADMAP Part 5):** ≥ 13 / 15 spot-checked labels rated accurate — i.e. a human reviewer agrees the tagline fits the majority of the cluster's member documents.

**Rating scale:**
- ✅ Accurate — tagline clearly names the dominant technology in the cluster
- ⚠️ Partial — tagline is related but too broad or misses the dominant thread
- ❌ Inaccurate — tagline does not match the members

---

## How to populate this review

After the Part 5 ML assets have been materialised (`document_embeddings` → `document_clusters` → `cluster_labels`), run the following query in `dev.duckdb` to sample clusters for review:

```sql
-- Sample representative papers per cluster for spot-check
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

Pick 15 clusters at random (or prioritise the largest non-noise clusters) and fill in the table below.

---

## Spot-check results

> **Status:** Pending — requires production run of Part 5 ML assets on live corpus.

| # | cluster_id | tagline | Top c-TF-IDF terms (sample) | Rating | Notes |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | |
| 8 | | | | | |
| 9 | | | | | |
| 10 | | | | | |
| 11 | | | | | |
| 12 | | | | | |
| 13 | | | | | |
| 14 | | | | | |
| 15 | | | | | |

**Score: ? / 15**

---

## Priority sanity checks

These three clusters must exist and their taglines must be recognisable before the exit criterion is considered met:

| Technology family | Expected keyword(s) in tagline | cluster_id found | ✅ / ❌ |
|---|---|---|---|
| EUV Lithography | EUV, lithography, photomask, extreme ultraviolet | | |
| Silicon Photonics | photonic, silicon photon, waveguide, optical | | |
| Neuromorphic / In-Memory | memristor, neuromorphic, synaptic, in-memory | | |

---

## Noise cluster

`c_noise` receives a fixed label ("Frontier / Unclustered") — not reviewed against members, but a sample of its members should be checked to confirm they are genuinely fringe / interdisciplinary rather than a coherent cluster that HDBSCAN failed to capture.

> If the noise bucket contains > 30% of all documents, consider re-tuning `_HDBSCAN_MIN_CLUSTER_SIZE` downward and re-running `document_clusters`.
