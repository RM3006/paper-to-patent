{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per scope patent.
  cluster_id is NULL here; populated when Part 5 embeddings land.
  Depends on: stg_patents_scoped
  Output: dev.duckdb marts.dim_patent
*/

select
    patent_id,
    title,
    filing_date,
    grant_date,   -- metadata only; never used for time metrics
    patent_type,
    cast(null as varchar) as cluster_id  -- populated in Part 5

from {{ ref('stg_patents_scoped') }}
