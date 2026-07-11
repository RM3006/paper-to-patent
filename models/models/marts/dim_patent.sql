{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per scope patent.
  Identity/text only -- cluster_id is deliberately NOT carried here (see dim_paper:
  it would make this dim depend on the ML clustering that itself reads this dim).
  The patent's cluster lives in the bridge fact_document_cluster
  (doc_type='patent'); join that (or fact_patent_filing) when it is needed.
  Depends on: stg_patents_scoped
  Output: dev.duckdb marts.dim_patent
*/

select
    p.patent_id,
    p.title,
    p.filing_date,
    p.grant_date,   -- metadata only; never used for time metrics
    p.patent_type

from {{ ref('stg_patents_scoped') }} p
