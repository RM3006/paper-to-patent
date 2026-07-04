{{
  config(
    materialized='table'
  )
}}

/*
  Mart: cluster -> presentation family assignment, using the ORIGINAL 3 scope
  families from ROADMAP.md Part 0 (EUV Lithography; Silicon Photonics, which
  includes lasers/H01S; Neuromorphic & In-Memory Compute, combined).

  This is a deliberate revert from an earlier 5-way split (EUV / Silicon
  Photonics / Lasers / Neuromorphic / In-Memory). Measuring cluster purity
  against each document's own CPC/topic tag (2026-07-04) showed the impurity
  was not random noise: 53 of ~299 clusters were a genuine Lasers<->Silicon-
  Photonics mix and 13 were a genuine Neuromorphic<->In-Memory mix (each
  requiring >=15% share on both sides), while every OTHER pair of families
  showed 0-3 such clusters. That is exactly the two seams where the 5-way
  split cut through a technology area that Part 0 originally scoped as one
  family (on-chip lasers and photonic integration are routinely the same
  research; memristors are natively both a neuromorphic synapse and a
  resistive memory cell). No cluster-level partition -- CPC rules, hierarchy,
  or an LLM -- can make that content single-family, because it genuinely isn't.
  Reverting to the 3 families where the data actually separates cleanly is the
  only assignment here that is honestly non-overlapping.

  Finer-grained specificity (e.g. "VCSEL lasers" vs "silicon photonic
  modulators") lives on the individual cluster tagline, not on an intermediate
  family bucket -- see dim_technology_cluster.

  This cluster-level assignment is a DISPLAY label for the cluster as a whole
  (map colour, cluster card). It is deliberately NOT used for family-level
  counting: fact_patent_filing.family_id and fact_publication.family_id carry
  each document's own direct family (unaffected by which cluster it landed in)
  and are the authoritative source for any patent-share, HHI, or leaderboard
  number. Join through cluster_id only when you want the cluster's own label.

  Method: majority vote per cluster over its member documents' family signal.
    - Patents vote via primary_cpc prefix (G03F->euv; G02B or H01S->
      silicon_photonics; G06N, G11C, or H10N->neuromorphic_in_memory).
    - Papers vote via primary_topic_id (T11338->euv; T10299 or T11429->
      silicon_photonics; T10502->neuromorphic_in_memory). Unlike the 5-way
      version, T10502 no longer needs a keyword tie-break: since neuromorphic
      and in-memory are merged back into one family, T10502 ("Advanced Memory
      and Neural Computing") maps to it unambiguously.
    - Clusters with no resolvable signal default to 'adjacent'. Every
      non-noise cluster gets a row -- mart_family inner-joins this table, so a
      missing row would silently drop that cluster's papers/patents from every
      family total.

  Depends on: fact_patent_filing, dim_paper, dim_technology_cluster
  Output: dev.duckdb main_marts.seed_cluster_family
*/

with family_meta (family_id, family_name, family_sort_order) as (
    values
        ('euv',                    'EUV Lithography',                   1),
        ('silicon_photonics',      'Silicon Photonics',                  2),
        ('neuromorphic_in_memory', 'Neuromorphic & In-Memory Compute',   3),
        ('adjacent',               'Adjacent / Out of Headline',         4)
),

-- Patent-side votes: primary_cpc prefix -> family.
-- One vote per distinct patent, not per assignee-row (fact_patent_filing is
-- exploded per assignee; voting on raw rows would let a 3-assignee patent
-- outvote three single-assignee patents in a different family).
patent_votes as (
    select
        cluster_id,
        case
            when primary_cpc like 'G03F%' then 'euv'
            when primary_cpc like 'H01S%' then 'silicon_photonics'
            when primary_cpc like 'G02B%' then 'silicon_photonics'
            when primary_cpc like 'G06N%' then 'neuromorphic_in_memory'
            when primary_cpc like 'G11C%' then 'neuromorphic_in_memory'
            when primary_cpc like 'H10N%' then 'neuromorphic_in_memory'
        end as family_vote
    from (
        select distinct cluster_id, patent_id, primary_cpc
        from {{ ref('fact_patent_filing') }}
        where cluster_id is not null and cluster_id != 'c_noise'
    )
),

-- Paper-side votes: primary_topic_id -> family (unambiguous once merged)
paper_votes as (
    select
        cluster_id,
        case primary_topic_id
            when 'https://openalex.org/T11338' then 'euv'
            when 'https://openalex.org/T11429' then 'silicon_photonics'
            when 'https://openalex.org/T10299' then 'silicon_photonics'
            when 'https://openalex.org/T10502' then 'neuromorphic_in_memory'
        end as family_vote
    from {{ ref('dim_paper') }}
    where cluster_id is not null and cluster_id != 'c_noise'
),

all_votes as (
    select cluster_id, family_vote from patent_votes where family_vote is not null
    union all
    select cluster_id, family_vote from paper_votes where family_vote is not null
),

vote_counts as (
    select cluster_id, family_vote, count(*) as n_votes
    from all_votes
    group by 1, 2
),

-- Plurality winner per cluster; ties broken deterministically by family_id.
ranked as (
    select
        cluster_id,
        family_vote,
        row_number() over (
            partition by cluster_id
            order by n_votes desc, family_vote asc
        ) as rnk
    from vote_counts
)

select
    dtc.cluster_id,
    coalesce(r.family_vote, 'adjacent')     as family_id,
    fm.family_name,
    fm.family_sort_order

from {{ ref('dim_technology_cluster') }} dtc
left join ranked r
    on r.cluster_id = dtc.cluster_id and r.rnk = 1
inner join family_meta fm
    on fm.family_id = coalesce(r.family_vote, 'adjacent')
where dtc.cluster_id != 'c_noise'
