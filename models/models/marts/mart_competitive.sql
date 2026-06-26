{{
  config(
    materialized='table'
  )
}}

/*
  Mart: competitive landscape — who captures IP vs who produces research, per cluster.

  Claim basis: descriptive counts of US patents and papers attributed to each org.
    Patent side: distinct USPTO patents assigned to org (US-only — stated caveat).
    Paper side:  distinct OpenAlex papers attributed to org via author institutions.
    This is NOT an NPL-linked signal; no causal link between a paper and a patent
    is implied by an org appearing on both sides.

  Grain: one row per (cluster_id, side, org_id_key).
    side = 'patent' (assignee side) | 'paper' (institution side)
    org_id_key = coalesce(org_id, 'unresolved') — never NULL, safe for joins.

  Share definition: doc_count / cluster_total where cluster_total is the distinct
  document count for that side in the cluster. On the paper side shares can SUM to
  > 100% per cluster because a paper with N co-authoring institutions is counted N
  times (once per org); this is correct — it is a co-attribution share, not a
  partitioned share. Each individual org's share remains in [0, 1].

  Unresolved rows (no crosswalk match) are included with org_id = null and
  canonical_name = 'Unresolved'. They are never silently dropped.

  Depends on: fact_patent_filing, fact_publication, dim_organization,
              dim_technology_cluster
  Output: dev.duckdb main_marts.mart_competitive
*/

-- ---------------------------------------------------------------------------
-- Patent side: one row per (cluster, org_id)
-- ---------------------------------------------------------------------------
with patent_org as (
    select
        cluster_id,
        coalesce(org_id, 'unresolved')              as org_id_key,
        org_id,
        count(distinct patent_id)                   as doc_count
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1, 2, 3
),

patent_total as (
    select cluster_id, count(distinct patent_id)    as cluster_total
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1
),

-- ---------------------------------------------------------------------------
-- Paper side: one row per (cluster, org_id) — institution_ids rolled up per org
-- ---------------------------------------------------------------------------
paper_org as (
    select
        cluster_id,
        coalesce(org_id, 'unresolved')              as org_id_key,
        org_id,
        count(distinct work_id)                     as doc_count
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1, 2, 3
),

paper_total as (
    select cluster_id, count(distinct work_id)      as cluster_total
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1
),

-- ---------------------------------------------------------------------------
-- Union both sides with share + rank
-- ---------------------------------------------------------------------------
combined as (
    select
        po.cluster_id,
        'patent'                                    as side,
        po.org_id_key,
        po.org_id,
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
        pao.doc_count,
        round(pao.doc_count * 1.0 / pt.cluster_total, 4) as share,
        pt.cluster_total
    from paper_org pao
    inner join paper_total pt on pt.cluster_id = pao.cluster_id
)

select
    c.cluster_id,
    dtc.tagline,
    c.side,
    c.org_id_key,
    c.org_id,
    coalesce(dorg.canonical_name, 'Unresolved')     as canonical_name,
    coalesce(dorg.primary_match_method, 'none')     as match_method,
    coalesce(dorg.primary_confidence, 'low')        as confidence,
    c.doc_count,
    c.share,
    c.cluster_total,
    row_number() over (
        partition by c.cluster_id, c.side
        order by c.doc_count desc
    )                                               as rank_in_cluster

from combined c
inner join {{ ref('dim_technology_cluster') }} dtc
    on dtc.cluster_id = c.cluster_id
left join {{ ref('dim_organization') }} dorg
    on dorg.org_id = c.org_id
