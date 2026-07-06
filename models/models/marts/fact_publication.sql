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

  family_id is this paper's OWN direct technology family, derived from its own
  primary_topic_id -- independent of which cluster it algorithmically landed in.
  T10502 ("Advanced Memory and Neural Computing") covers both neuromorphic and
  in-memory compute, so it can't be split by topic ID alone; those papers are
  classified by a keyword match on the PAPER'S OWN title + abstract (not the
  cluster's tagline -- a cluster-level tie-break would just inherit whatever the
  cluster's majority is, which is exactly the attribution problem this column
  exists to avoid). This is the authoritative column for family-level counting;
  a cluster's majority family (seed_cluster_family, joined via cluster_id) is a
  display label for the cluster as a whole, not a per-document fact.

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
        title,
        abstract,
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
        case
            when e.primary_topic_id = 'https://openalex.org/T11338' then 'euv'
            when e.primary_topic_id = 'https://openalex.org/T11429' then 'lasers'
            when e.primary_topic_id = 'https://openalex.org/T10299' then 'si_photonics'
            when e.primary_topic_id = 'https://openalex.org/T10502' then
                case
                    when regexp_matches(
                        lower(e.title || ' ' || coalesce(e.abstract, '')),
                        'neuromorphic|spik|synap|neuron|brain'
                    )
                        then 'neuromorphic'
                    when regexp_matches(
                        lower(e.title || ' ' || coalesce(e.abstract, '')),
                        'memristor|rram|resistive|nonvolatile|phase.change|memory'
                    )
                        then 'in_memory'
                end
        end                         as family_id,
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
