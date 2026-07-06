{{
  config(
    materialized='table'
  )
}}

/*
  Staging: scope-filtered patents (CPC match + filing_date 2014–2025).
  Casts types and selects only the columns needed downstream.
  Excludes doc_ids in ml_intermediate.excluded_documents (patents the Part 5
  embedding quality gate excluded entirely -- version-style title). Real
  dependency on Part 5 having run: before it ever has, that source is an
  empty relation and this filter is a no-op, not an error -- see
  create_external_sources() and MEMORY.md.
  Depends on: sources.patentsview_raw.patents_scoped, sources.ml_intermediate.excluded_documents
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
  and patent_id not in (
      select doc_id from {{ source('ml_intermediate', 'excluded_documents') }}
      where doc_type = 'patent'
  )
