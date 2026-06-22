{{
  config(
    materialized='table'
  )
}}

/*
  Staging: patent-to-patent citation edges where the citing patent is in scope.
  Depends on: sources.patentsview_raw.citations, stg_patents_scoped
  Output: dev.duckdb staging.stg_patent_citations
*/

select
    c.patent_id          as citing_patent_id,
    c.citation_patent_id as cited_patent_id

from {{ source('patentsview_raw', 'citations') }} c
inner join {{ ref('stg_patents_scoped') }} s
    on c.patent_id = s.patent_id
where c.citation_patent_id is not null
