{{
  config(
    materialized='table'
  )
}}

/*
  Staging: CPC codes for scope patents only.
  Keeps inventional and additional codes; primary CPC is cpc_sequence = 0.
  Depends on: sources.patentsview_raw.cpc, stg_patents_scoped
  Output: dev.duckdb staging.stg_cpc
*/

select
    c.patent_id,
    c.cpc_group,
    c.cpc_subclass,
    c.cpc_class,
    c.cpc_section,
    c.cpc_type,
    c.cpc_sequence::integer   as cpc_sequence

from {{ source('patentsview_raw', 'cpc') }} c
inner join {{ ref('stg_patents_scoped') }} s
    on c.patent_id = s.patent_id
where c.cpc_group is not null
