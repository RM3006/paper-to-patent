{{
  config(
    materialized='table'
  )
}}

/*
  Mart: competitive landscape — who captures IP vs who produces research, per
  cluster AND per document-level technology family.

  Claim basis: descriptive counts of US patents and papers attributed to each org.
    Patent side: distinct USPTO patents assigned to org (US-only — stated caveat).
    Paper side:  distinct OpenAlex papers attributed to org via author institutions.
    This is NOT an NPL-linked signal; no causal link between a paper and a patent
    is implied by an org appearing on both sides.

  Grain: one row per (cluster_id, side, org_id_key, family_id_key).
    side = 'patent' (assignee side) | 'paper' (institution side)
    org_id_key = coalesce(org_id, 'unresolved') — never NULL, safe for joins.
    family_id_key = coalesce(family_id, 'unattributed') — never NULL. family_id is
    each document's OWN direct technology family (fact_patent_filing.family_id /
    fact_publication.family_id, 5-way: euv/lasers/si_photonics/neuromorphic/
    in_memory) — independent of the cluster it algorithmically landed in; see
    those models' docstrings. A document with an off-scope primary CPC (patents;
    it entered scope on a prominent-but-secondary code) or an unresolved
    neuromorphic/in-memory keyword tiebreak (papers) has a NULL family_id and
    rolls into 'unattributed' here rather than being silently dropped.

  Share definition: doc_count / cluster_total where cluster_total is the distinct
  document count for that side in the CLUSTER AS A WHOLE (all families combined —
  unaffected by the family split; same meaning as before this grain was widened).
  On the paper side shares can SUM to > 100% per cluster because a paper with N
  co-authoring institutions is counted N times (once per org); this is correct —
  it is a co-attribution share, not a partitioned share. Each individual org's
  share remains in [0, 1].

  rank_in_cluster: this organisation's rank by ITS TOTAL doc_count across ALL its
  family slices within (cluster_id, side) — i.e. the same value repeats on every
  family-sliced row belonging to that org. It answers "how active is this org in
  this cluster overall," not "how active is this org in this cluster for this
  family" — deliberately unchanged from its pre-widening meaning.

  Unresolved rows (no crosswalk match) are included with org_id = null and
  canonical_name = 'Unresolved'. They are never silently dropped.

  Depends on: fact_patent_filing, fact_publication, dim_organization,
              dim_technology_cluster
  Output: dev.duckdb main_marts.mart_competitive
*/

-- ---------------------------------------------------------------------------
-- Patent side: one row per (cluster, org_id, family_id)
-- ---------------------------------------------------------------------------
with patent_org as (
    select
        cluster_id,
        coalesce(org_id, 'unresolved')              as org_id_key,
        org_id,
        coalesce(family_id, 'unattributed')         as family_id_key,
        family_id,
        count(distinct patent_id)                   as doc_count
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1, 2, 3, 4, 5
),

patent_total as (
    select cluster_id, count(distinct patent_id)    as cluster_total
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1
),

-- ---------------------------------------------------------------------------
-- Paper side: one row per (cluster, org_id, family_id) — institution_ids rolled up per org
-- ---------------------------------------------------------------------------
paper_org as (
    select
        cluster_id,
        coalesce(org_id, 'unresolved')              as org_id_key,
        org_id,
        coalesce(family_id, 'unattributed')         as family_id_key,
        family_id,
        count(distinct work_id)                     as doc_count
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1, 2, 3, 4, 5
),

paper_total as (
    select cluster_id, count(distinct work_id)      as cluster_total
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1
),

-- ---------------------------------------------------------------------------
-- Union both sides with share + cluster_total
-- ---------------------------------------------------------------------------
combined as (
    select
        po.cluster_id,
        'patent'                                    as side,
        po.org_id_key,
        po.org_id,
        po.family_id_key,
        po.family_id,
        po.doc_count,
        round(po.doc_count * 1.0 / pt.cluster_total, 4) as share,
        pt.cluster_total
    from patent_org po
    inner join patent_total pt on pt.cluster_id = po.cluster_id

    union all

    select
        pao.cluster_id,
        'paper'                                     as side,
        pao.org_id_key,
        pao.org_id,
        pao.family_id_key,
        pao.family_id,
        pao.doc_count,
        round(pao.doc_count * 1.0 / pt.cluster_total, 4) as share,
        pt.cluster_total
    from paper_org pao
    inner join paper_total pt on pt.cluster_id = pao.cluster_id
),

-- ---------------------------------------------------------------------------
-- rank_in_cluster computed on the org's TOTAL doc_count across all its family
-- slices, then attached to every one of that org's family-sliced rows -- see
-- docstring. Must be derived after the family split, not before, since combined
-- is already split by family_id_key.
-- ---------------------------------------------------------------------------
org_cluster_totals as (
    select cluster_id, side, org_id_key, sum(doc_count) as org_doc_count
    from combined
    group by 1, 2, 3
),

org_rank as (
    select
        cluster_id, side, org_id_key,
        row_number() over (
            partition by cluster_id, side
            order by org_doc_count desc, org_id_key
        ) as rank_in_cluster
    from org_cluster_totals
)

select
    c.cluster_id,
    dtc.tagline,
    c.side,
    c.org_id_key,
    c.org_id,
    c.family_id_key,
    c.family_id,
    coalesce(dorg.canonical_name, 'Unresolved')     as canonical_name,
    coalesce(dorg.primary_match_method, 'none')     as match_method,
    coalesce(dorg.primary_confidence, 'low')        as confidence,
    c.doc_count,
    c.share,
    c.cluster_total,
    r.rank_in_cluster

from combined c
inner join {{ ref('dim_technology_cluster') }} dtc
    on dtc.cluster_id = c.cluster_id
left join {{ ref('dim_organization') }} dorg
    on dorg.org_id = c.org_id
inner join org_rank r
    on r.cluster_id = c.cluster_id and r.side = c.side and r.org_id_key = c.org_id_key
