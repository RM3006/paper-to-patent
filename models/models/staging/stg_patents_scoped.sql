{{
  config(
    materialized='table'
  )
}}

/*
  Staging: scope-filtered patents (CPC match + filing_date 2014–2025).
  Casts types and selects only the columns needed downstream.
  Depends on: sources.patentsview_raw.patents_scoped
  Output: dev.duckdb staging.stg_patents_scoped
*/

select
    patent_id,
    patent_title                    as title,
    filing_date::date               as filing_date,
    patent_date::date               as grant_date,   -- metadata only; never used in time metrics
    patent_type

from {{ source('patentsview_raw', 'patents_scoped') }}
where patent_id is not null
  and filing_date is not null
