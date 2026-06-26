{{
  config(
    materialized='table'
  )
}}

/*
  Mart: research-to-patent concentration gap — researched broadly, patented narrowly.

  Claim basis: descriptive concentration measure within US patents only.
    HHI (Herfindahl-Hirschman Index) over primary assignees of US patents per cluster.
    Institution breadth is the count of distinct OpenAlex institutions contributing
    papers to the cluster — NOT a geographic comparison (that would be circular given
    US-only patent coverage). The finding is: "[cluster] has research from N institutions,
    but US patents are concentrated in Z assignees (HHI = X)."

  HHI methodology:
    - Primary assignee: assignee_sequence = 0 preferred; fall back to lowest non-null
      sequence; patents with no org-type assignee resolved to crosswalk get NULL.
    - HHI = Σ(share²) where share = org_patents / total_patents_in_cluster.
    - NULL-org patents are excluded from share computation; pct_unresolved_patents
      documents the exclusion rate (1.6% across scope).
    - hhi is NULL and hhi_reportable = false when n_patents_in_hhi < 10.
    - HHI is reported on a [0, 1] scale; ×10000 = traditional HHI points.

  Grain: one row per cluster_id.
  c_noise is included but is_noise = true; exclude from headline concentration findings.

  Depends on: fact_patent_filing, fact_publication, dim_technology_cluster
  Output: dev.duckdb main_marts.mart_gap
*/

-- Primary assignee per patent (one row per patent)
with primary_assignee as (
    select distinct on (patent_id)
        patent_id,
        cluster_id,
        org_id                                              as primary_org_id
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    order by
        patent_id,
        case
            when assignee_sequence = 0 then 0
            when assignee_sequence is null then 2
            else 1
        end,
        assignee_sequence
),

-- Count patents per (cluster, org) — NULL org_id is its own bucket
org_counts as (
    select
        cluster_id,
        primary_org_id,
        count(*)                                            as org_patents
    from primary_assignee
    group by 1, 2
),

cluster_patent_totals as (
    select cluster_id,
        sum(org_patents)                                    as total_patents,
        sum(org_patents) filter(where primary_org_id is null) as unresolved_patents
    from org_counts
    group by 1
),

-- HHI: exclude null-org rows from share computation
hhi_calc as (
    select
        oc.cluster_id,
        round(
            sum(
                (oc.org_patents * 1.0 / ct.total_patents) *
                (oc.org_patents * 1.0 / ct.total_patents)
            ),
            4
        )                                                   as hhi_raw,
        count(distinct oc.primary_org_id)
            filter(where oc.primary_org_id is not null)     as n_assignees,
        max(ct.total_patents)                               as total_patents,
        max(ct.unresolved_patents)                          as unresolved_patents
    from org_counts oc
    inner join cluster_patent_totals ct on ct.cluster_id = oc.cluster_id
    where oc.primary_org_id is not null                     -- exclude from HHI shares
    group by 1
),

-- Institution breadth: distinct institution_ids from the paper side
institution_breadth as (
    select
        cluster_id,
        count(distinct institution_id)                      as n_institutions,
        count(distinct work_id)                             as n_papers
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1
)

select
    dtc.cluster_id,
    dtc.tagline,
    dtc.cluster_id = 'c_noise'                              as is_noise,

    -- Patent concentration
    coalesce(h.total_patents, 0)                            as n_patents,
    coalesce(h.n_assignees, 0)                              as n_assignees,
    round(coalesce(h.unresolved_patents, 0) * 100.0
        / nullif(coalesce(h.total_patents, 0), 0), 1)       as pct_unresolved_patents,

    -- HHI (NULL when n_patents < 10 — not reportable)
    case when coalesce(h.total_patents, 0) >= 10
        then h.hhi_raw
    end                                                     as hhi,
    coalesce(h.total_patents, 0) >= 10                      as hhi_reportable,

    -- Research breadth
    coalesce(ib.n_institutions, 0)                          as n_institutions,
    coalesce(ib.n_papers, 0)                                as n_papers

from {{ ref('dim_technology_cluster') }} dtc
left join hhi_calc h
    on h.cluster_id = dtc.cluster_id
left join institution_breadth ib
    on ib.cluster_id = dtc.cluster_id
