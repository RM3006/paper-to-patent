{{
  config(
    materialized='table'
  )
}}

/*
  Fact: one row per (paper, institution) combination in scope.
  org_id is attached via the crosswalk by matching institution_id → crosswalk.source_id.
  NULL org_id is allowed when an institution appears in OA but not in the crosswalk
  (rare: the crosswalk covers all OA institutions appearing in scope per Part 3).
  Depends on: stg_openalex_works, int_org_crosswalk
  Output: dev.duckdb marts.fact_publication
*/

-- Explode institution_ids list into one row per (paper, institution)
with exploded as (
    select
        work_id,
        publication_date,
        publication_year,
        primary_topic_id,
        primary_topic_name,
        unnest(institution_ids)     as institution_id
    from {{ ref('stg_openalex_works') }}
),

with_org as (
    select
        e.work_id,
        e.publication_date,
        e.publication_year,
        e.primary_topic_id,
        e.primary_topic_name,
        e.institution_id,
        x.org_id,
        x.match_method              as org_match_method,
        x.confidence                as org_confidence,
        fdc.cluster_id
    from exploded e
    left join {{ ref('int_org_crosswalk') }} x
        on x.source = 'openalex'
        and x.source_id = e.institution_id
    left join {{ ref('fact_document_cluster') }} fdc
        on fdc.doc_id = e.work_id
        and fdc.doc_type = 'paper'
)

select * from with_org
