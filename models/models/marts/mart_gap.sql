{{
  config(
    materialized='table'
  )
}}

/*
  Mart: per-cluster summary — citation lag, concentration gap, and research breadth.

  Claim basis: descriptive concentration measure within US patents only.
    HHI (Herfindahl-Hirschman Index) over primary assignees of US patents per cluster.
    n_oa_institutions = count(distinct institution_id) — sub-org granularity (IBM Research
    Almaden and IBM Research Zürich are 2). n_research_orgs = count(distinct org_id) —
    org-level, post-ER, comparable to n_assignees. Use n_research_orgs for the
    breadth-vs-concentration comparison; use n_oa_institutions for fine-grained diversity.

  HHI methodology:
    - Primary assignee: assignee_sequence = 0 preferred; fall back to lowest non-null
      sequence; patents with no org-type assignee resolved to crosswalk get NULL.
    - HHI = Σ(share²) where share = org_patents / resolved_patents_in_cluster.
      Denominator is resolved patents only; unresolved (null-org) patents are excluded
      from both numerator and denominator so they do not dilute measured concentration.
      pct_unresolved_patents documents the exclusion rate (1.6% across scope on average;
      some clusters are higher — see mart output).
    - hhi is NULL and hhi_reportable = false when resolved_patents < 10.
    - HHI is reported on a [0, 1] scale; ×10000 = traditional HHI points.

  Citation lag (NPL-linked):
    - npl_median_lag_years: median(filing_date − publication_date) for NPL-cited pairs,
      anchored on the citing patent's cluster. NULL when npl_n_links < 20.
    - cohort_lag_years: median(patent filing year) − median(paper pub year) per cluster.
      SOFT ESTIMATE — papers and patents need not be directly NPL-linked.

  Grain: one row per cluster_id.
  c_noise is included but is_noise = true; exclude from headline findings.

  Depends on: fact_patent_filing, fact_publication, fact_npl_link, dim_patent,
              dim_technology_cluster
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
        sum(org_patents) filter(where primary_org_id is null)     as unresolved_patents,
        sum(org_patents) filter(where primary_org_id is not null) as resolved_patents
    from org_counts
    group by 1
),

-- HHI: shares computed over resolved patents only (denominator excludes null-org patents)
hhi_calc as (
    select
        oc.cluster_id,
        round(
            sum(
                (oc.org_patents * 1.0 / ct.resolved_patents) *
                (oc.org_patents * 1.0 / ct.resolved_patents)
            ),
            4
        )                                                   as hhi_raw,
        count(distinct oc.primary_org_id)
            filter(where oc.primary_org_id is not null)     as n_assignees,
        max(ct.total_patents)                               as total_patents,
        max(ct.unresolved_patents)                          as unresolved_patents,
        max(ct.resolved_patents)                            as resolved_patents
    from org_counts oc
    inner join cluster_patent_totals ct on ct.cluster_id = oc.cluster_id
    where oc.primary_org_id is not null
    group by 1
),

-- Institution breadth: two granularities (sub-org and org-level)
institution_breadth as (
    select
        cluster_id,
        count(distinct institution_id)                      as n_oa_institutions,
        count(distinct org_id)                              as n_research_orgs,
        count(distinct work_id)                             as n_papers
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1
),

-- NPL-linked citation lag; patent cluster is the anchor per project decision
npl_lag as (
    select
        dpat.cluster_id,
        count(*)                                            as npl_n_links,
        round(median(nl.citation_lag_years), 2)             as npl_median_lag_years
    from {{ ref('fact_npl_link') }} nl
    inner join {{ ref('dim_patent') }} dpat
        on dpat.patent_id = nl.patent_id
    where dpat.cluster_id is not null
    group by 1
),

-- Cohort lag (SOFT ESTIMATE — not NPL-linked)
cohort_paper as (
    select cluster_id, median(publication_year) as med_pub_year
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1
),

cohort_patent as (
    select
        cluster_id,
        median(extract(year from filing_date)::int)         as med_filing_year
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1
),

cohort_lag as (
    select
        pp.cluster_id,
        round(pp.med_pub_year, 1)                           as cohort_med_pub_year,
        round(pt.med_filing_year, 1)                        as cohort_med_filing_year,
        round(pt.med_filing_year - pp.med_pub_year, 1)      as cohort_lag_years
    from cohort_paper pp
    inner join cohort_patent pt on pt.cluster_id = pp.cluster_id
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

    -- HHI (NULL when resolved patents < 10 — not reportable)
    case when coalesce(h.resolved_patents, 0) >= 10
        then h.hhi_raw
    end                                                     as hhi,
    coalesce(h.resolved_patents, 0) >= 10                   as hhi_reportable,

    -- Research breadth
    -- n_oa_institutions: sub-org granularity (IBM Research Almaden ≠ IBM Research Zürich)
    -- n_research_orgs:   org-level post-ER, directly comparable to n_assignees
    coalesce(ib.n_oa_institutions, 0)                       as n_oa_institutions,
    coalesce(ib.n_research_orgs, 0)                         as n_research_orgs,
    coalesce(ib.n_papers, 0)                                as n_papers,

    -- NPL-linked citation lag (NULL when npl_n_links < 20)
    case when coalesce(nl.npl_n_links, 0) >= 20
        then nl.npl_median_lag_years
    end                                                     as npl_median_lag_years,
    coalesce(nl.npl_n_links, 0)                             as npl_n_links,
    coalesce(nl.npl_n_links, 0) >= 20                       as npl_reportable,

    -- Cohort lag (SOFT — papers and patents in the cluster need not be NPL-linked)
    cl.cohort_med_pub_year,
    cl.cohort_med_filing_year,
    cl.cohort_lag_years

from {{ ref('dim_technology_cluster') }} dtc
left join hhi_calc h
    on h.cluster_id = dtc.cluster_id
left join institution_breadth ib
    on ib.cluster_id = dtc.cluster_id
left join npl_lag nl
    on nl.cluster_id = dtc.cluster_id
left join cohort_lag cl
    on cl.cluster_id = dtc.cluster_id
