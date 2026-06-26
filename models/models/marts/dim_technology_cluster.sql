{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per technology cluster.
  c_noise is included with a fixed "Frontier / Unclustered" label.
  Depends on: ml_intermediate.cluster_labels (R2, written by cluster_labels Dagster asset)
  Output: dev.duckdb main_marts.dim_technology_cluster
*/

select
    cluster_id,
    tagline,
    summary_friendly,
    top_terms

from {{ source('ml_intermediate', 'cluster_labels') }}
