{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per OpenAlex work in scope.
  cluster_id is NULL here; populated when Part 5 embeddings land.
  Depends on: stg_openalex_works
  Output: dev.duckdb marts.dim_paper
*/

select
    work_id,
    work_url,
    doi,
    doi_bare,
    title,
    publication_date,
    publication_year,
    abstract,
    primary_topic_id,
    primary_topic_name,
    cast(null as varchar) as cluster_id  -- populated in Part 5

from {{ ref('stg_openalex_works') }}
