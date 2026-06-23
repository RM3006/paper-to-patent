{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per scope patent.
  cluster_id back-filled from fact_document_cluster (Part 5 ML pipeline).
  NULL until document_clusters Dagster asset has been materialised and dbt rebuilt.
  Depends on: stg_patents_scoped, fact_document_cluster
  Output: dev.duckdb marts.dim_patent
*/

select
    p.patent_id,
    p.title,
    p.filing_date,
    p.grant_date,   -- metadata only; never used for time metrics
    p.patent_type,
    fdc.cluster_id

from {{ ref('stg_patents_scoped') }} p
left join {{ ref('fact_document_cluster') }} fdc
    on fdc.doc_id = p.patent_id
    and fdc.doc_type = 'patent'
