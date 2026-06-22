{{
  config(
    materialized='table'
  )
}}

/*
  Staging: NPL "other reference" strings for scope patents.
  Does NOT attempt matching here — raw text preserved for the Python NPL matcher.
  Depends on: sources.patentsview_raw.npl, stg_patents_scoped
  Output: dev.duckdb staging.stg_npl
*/

select
    n.patent_id,
    n.other_reference_sequence::integer   as ref_sequence,
    n.other_reference_text                as ref_text,
    -- Pre-extract DOI pattern where present (high-confidence match path)
    lower(
        regexp_extract(
            n.other_reference_text,
            '10\.\d{4,9}/[-._;()/:A-Za-z0-9]+',
            0
        )
    )                                     as doi_extracted

from {{ source('patentsview_raw', 'npl') }} n
inner join {{ ref('stg_patents_scoped') }} s
    on n.patent_id = s.patent_id
where n.other_reference_text is not null
