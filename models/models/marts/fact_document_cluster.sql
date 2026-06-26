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
  Depends on: ml_intermediate.clusters (R2, written by document_clusters Dagster asset)
  Output: dev.duckdb main_marts.fact_document_cluster
*/

select
    doc_id,
    doc_type,
    cluster_id,
    umap_x,
    umap_y,
    model_version

from {{ source('ml_intermediate', 'clusters') }}
