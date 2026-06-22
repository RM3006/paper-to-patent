{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per distinct CPC group code appearing in scope patents.
  Depends on: stg_cpc
  Output: dev.duckdb marts.dim_cpc
*/

select distinct
    cpc_group,
    cpc_subclass,
    cpc_class,
    cpc_section

from {{ ref('stg_cpc') }}
where cpc_group is not null
