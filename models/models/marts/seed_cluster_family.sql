{{
  config(
    materialized='table'
  )
}}

/*
  Mart: cluster -> presentation family assignment, using the ORIGINAL 3 scope
  families from ROADMAP.md Part 0 (EUV Lithography; Silicon Photonics, which
  includes lasers/H01S; Neuromorphic & In-Memory Compute, combined), plus a
  'mixed' bucket for clusters that no single family clearly dominates.

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

  Method: a confidence-floored dominant-family vote per cluster.
    - Patents vote via primary_cpc prefix (G03F->euv; G02B or H01S->
      silicon_photonics; G06N, G11C, or H10N->neuromorphic_in_memory). A patent
      whose PRIMARY cpc is outside the six scope subclasses (it entered scope
      on a prominent-but-secondary code -- ~30% of patents) votes 'mixed'.
    - Papers vote via primary_topic_id (T11338->euv; T10299 or T11429->
      silicon_photonics; T10502->neuromorphic_in_memory). At this 3-way grain
      T10502 ("Advanced Memory and Neural Computing") maps unambiguously, so
      papers always resolve to a real family.
    - THE FLOOR (two thresholds): a cluster is labelled with a real family only
      if BOTH (a) that family is >= 80% of the cluster's family-RESOLVABLE
      documents [purity], AND (b) family-resolvable documents are >= 50% of ALL
      its documents [coverage]. So 'mixed' means the cluster genuinely spans
      >= 2 families (fails purity) OR is mostly off-scope (fails coverage). This
      stops a 37%-plurality cluster (e.g. generic-ML "Transformer Models")
      being painted a confident family colour, WITHOUT demoting a clean single-
      technology cluster that merely happens to be patent-heavy (e.g. "Cross-
      Point Memory Arrays" -- 99% in-memory among its resolvable docs, but 31%
      off-scope-primary patents). Measured 2026-07-08: 19 of 227 clusters
      resolve to 'mixed'.
    - Every non-noise cluster gets a row -- mart_family inner-joins this table,
      so a missing row would silently drop that cluster from every family
      total. 'mixed' rows are included but excluded from the UI headline charts.

  Depends on: fact_patent_filing, fact_document_cluster, dim_paper, dim_technology_cluster
  Output: dev.duckdb main_marts.seed_cluster_family
*/

with family_meta (family_id, family_name, family_sort_order) as (
    values
        ('euv',                    'EUV Lithography',                   1),
        ('silicon_photonics',      'Silicon Photonics',                  2),
        ('neuromorphic_in_memory', 'Neuromorphic & In-Memory Compute',   3),
        ('mixed',                  'Mixed',                              4)
),

-- Patent-side votes: one per distinct patent (fact_patent_filing is exploded
-- per assignee; voting on raw rows would let a 3-assignee patent outvote three
-- single-assignee patents). Off-scope / missing primary CPC -> 'mixed' so it
-- counts in the denominator instead of being silently dropped.
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
            else 'mixed'
        end as family_vote
    from (
        select distinct cluster_id, patent_id, primary_cpc
        from {{ ref('fact_patent_filing') }}
        where cluster_id is not null and cluster_id != 'c_noise'
    )
),

-- Paper-side votes: one per paper. T10502 -> neuromorphic_in_memory is
-- unambiguous at the 3-way grain; the else keeps the expression total.
-- cluster_id comes from the bridge fact_document_cluster (one row per doc), not
-- from dim_paper -- the dim no longer carries cluster_id (that denormalisation
-- was the dim->clusters->dim cycle; see dim_paper.sql).
paper_votes as (
    select
        fdc.cluster_id,
        case dp.primary_topic_id
            when 'https://openalex.org/T11338' then 'euv'
            when 'https://openalex.org/T11429' then 'silicon_photonics'
            when 'https://openalex.org/T10299' then 'silicon_photonics'
            when 'https://openalex.org/T10502' then 'neuromorphic_in_memory'
            else 'mixed'
        end as family_vote
    from {{ ref('dim_paper') }} dp
    inner join {{ ref('fact_document_cluster') }} fdc
        on fdc.doc_id = dp.work_id and fdc.doc_type = 'paper'
    where fdc.cluster_id is not null and fdc.cluster_id != 'c_noise'
),

all_votes as (
    select cluster_id, family_vote from patent_votes
    union all
    select cluster_id, family_vote from paper_votes
),

-- Denominators.
cluster_totals as (
    select cluster_id, count(*) as n_total          -- ALL documents (coverage denom)
    from all_votes
    group by 1
),

real_totals as (
    select cluster_id, count(*) as n_real           -- family-resolvable docs (purity denom)
    from all_votes
    where family_vote != 'mixed'
    group by 1
),

-- Vote counts per real family.
real_family_counts as (
    select cluster_id, family_vote, count(*) as n_votes
    from all_votes
    where family_vote != 'mixed'
    group by 1, 2
),

-- Dominant real family per cluster; ties broken deterministically by family_id.
ranked as (
    select
        cluster_id,
        family_vote,
        n_votes,
        row_number() over (
            partition by cluster_id
            order by n_votes desc, family_vote asc
        ) as rnk
    from real_family_counts
),

dominant as (
    select cluster_id, family_vote, n_votes
    from ranked
    where rnk = 1
),

-- A real family names the cluster only if BOTH thresholds clear:
--   purity   = dominant family / resolvable docs >= 0.80
--   coverage = resolvable docs / all docs        >= 0.50
-- otherwise the cluster genuinely spans families or is mostly off-scope -> 'mixed'.
assigned as (
    select
        dtc.cluster_id,
        case
            when d.n_votes is not null
                 and d.n_votes::double / rt.n_real  >= 0.80
                 and rt.n_real::double / ct.n_total >= 0.50
            then d.family_vote
            else 'mixed'
        end as family_id
    from {{ ref('dim_technology_cluster') }} dtc
    left join cluster_totals ct on ct.cluster_id = dtc.cluster_id
    left join real_totals    rt on rt.cluster_id = dtc.cluster_id
    left join dominant       d  on d.cluster_id  = dtc.cluster_id
    where dtc.cluster_id != 'c_noise'
)

select
    a.cluster_id,
    a.family_id,
    fm.family_name,
    fm.family_sort_order
from assigned a
inner join family_meta fm
    on fm.family_id = a.family_id
