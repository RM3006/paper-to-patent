{{
  config(
    materialized='table'
  )
}}

/*
  Staging: PatentsView disambiguated assignees joined to scope.
  Only keeps assignees whose patent is in patents_scoped.
  Filters to organisation-type assignees (assignee_type in 2,3,6,7).
  Depends on: sources.patentsview_raw.assignees, stg_patents_scoped
  Output: dev.duckdb staging.stg_assignees
*/

select
    a.patent_id,
    a.assignee_id,
    a.disambig_assignee_organization   as org_name,
    a.assignee_type,
    a.assignee_sequence::integer       as assignee_sequence

from {{ source('patentsview_raw', 'assignees') }} a
inner join {{ ref('stg_patents_scoped') }} s
    on a.patent_id = s.patent_id
where a.assignee_id is not null
  and a.disambig_assignee_organization is not null
  -- restrict to organisation-type assignees; skip individual inventors
  and a.assignee_type in ('2', '3', '6', '7')
