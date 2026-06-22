{{
  config(
    materialized='table'
  )
}}

/*
  Intermediate: org_crosswalk sourced from R2.
  Re-exposes the Part 3 crosswalk inside the dbt graph so marts can ref() it.
  Depends on: sources.er_intermediate.org_crosswalk
  Output: dev.duckdb intermediate.int_org_crosswalk
*/

select
    org_id,
    source,
    source_id,
    canonical_name,
    match_method,
    confidence

from {{ source('er_intermediate', 'org_crosswalk') }}
