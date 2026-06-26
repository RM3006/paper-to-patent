{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per OpenAlex work in scope.
  cluster_id back-filled from fact_document_cluster (Part 5 ML pipeline).
  NULL until document_clusters Dagster asset has been materialised and dbt rebuilt.
  Depends on: stg_openalex_works, fact_document_cluster
  Output: dev.duckdb marts.dim_paper
*/

select
    w.work_id,
    w.work_url,
    w.doi,
    w.doi_bare,
    w.title,
    w.publication_date,
    w.publication_year,
    w.abstract,
    w.primary_topic_id,
    w.primary_topic_name,
    fdc.cluster_id

from {{ ref('stg_openalex_works') }} w
left join {{ ref('fact_document_cluster') }} fdc
    on fdc.doc_id = w.work_id
    and fdc.doc_type = 'paper'
