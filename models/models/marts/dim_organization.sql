{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per canonical org_id.
  Built from int_org_crosswalk; multiple source rows collapse to one dimension row.
  Canonical name priority: seed_crosswalk > fuzzy_high > native_id > ror.
  Depends on: int_org_crosswalk
  Output: dev.duckdb marts.dim_organization
*/

with ranked as (
    select
        org_id,
        canonical_name,
        match_method,
        confidence,
        -- Priority: seed rows have known canonical names; prefer them.
        case match_method
            when 'seed_crosswalk' then 1
            when 'fuzzy_high'     then 2
            when 'native_id'      then 3
            when 'ror'            then 4
            else 5
        end as method_rank
    from {{ ref('int_org_crosswalk') }}
),

best_per_org as (
    select distinct on (org_id)
        org_id,
        canonical_name,
        match_method,
        confidence
    from ranked
    order by org_id, method_rank asc
)

select
    org_id,
    canonical_name,
    match_method  as primary_match_method,
    confidence    as primary_confidence
from best_per_org
