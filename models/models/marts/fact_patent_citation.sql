{{
  config(
    materialized='table'
  )
}}

/*
  Fact: patent-to-patent citation edges where the citing patent is in scope.
  Depends on: stg_patent_citations
  Output: dev.duckdb marts.fact_patent_citation
*/

select
    citing_patent_id,
    cited_patent_id

from {{ ref('stg_patent_citations') }}
