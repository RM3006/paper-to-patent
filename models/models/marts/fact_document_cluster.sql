{{
  config(
    materialized='table'
  )
}}

/*
  Fact: one row per document → technology cluster assignment.
  doc_type 'paper'  → doc_id = work_id  (joins to dim_paper.work_id).
  doc_type 'patent' → doc_id = patent_id (joins to dim_patent.patent_id).
  umap_x / umap_y: 2D coordinates for the technology map (Streamlit scattergl).

  Filtered to doc_ids still present in the current scoped staging models.
  The ML pipeline (Part 5) embeds/clusters a snapshot of the corpus that can
  drift from a later staging-layer filter change (e.g. a new junk-title
  exclusion) without a re-cluster -- this join drops any such doc from the
  map/cluster fact instead of surfacing it as an orphan point (see Issue 1
  in the Part 0-7 checkpoint review, MEMORY.md). Joins against the staging
  models, not dim_paper/dim_patent, to avoid a circular dependency (those
  dims themselves backfill cluster_id from this fact).
  Depends on: ml_intermediate.clusters (R2, written by document_clusters
  Dagster asset), stg_openalex_works, stg_patents_scoped
  Output: dev.duckdb main_marts.fact_document_cluster
*/

select
    c.doc_id,
    c.doc_type,
    c.cluster_id,
    c.umap_x,
    c.umap_y,
    c.model_version

from {{ source('ml_intermediate', 'clusters') }} c
where
    (c.doc_type = 'paper' and exists (
        select 1 from {{ ref('stg_openalex_works') }} w where w.work_id = c.doc_id
    ))
    or
    (c.doc_type = 'patent' and exists (
        select 1 from {{ ref('stg_patents_scoped') }} p where p.patent_id = c.doc_id
    ))
