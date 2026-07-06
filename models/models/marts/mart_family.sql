{{
  config(
    materialized='table'
  )
}}

/*
  Gold mart: family-level scorecard — one row per technology family.
  The 5 headline families are a PRESENTATION rollup over ~303 clusters;
  cluster → family mapping is the curated seed_cluster_family.
  "adjacent" rows are included but excluded from headline charts by the UI.

  Claim: "5 families" front-door scorecard (papers, patents, assignees, researchers,
  median citation lag, patent-to-paper ratio). All US-patent-only; stated in UI.

  Depends on: mart_gap, mart_competitive, seed_cluster_family
  Output: dev.duckdb main_marts.mart_family
*/

with gap as (
    select
        mg.cluster_id,
        mg.n_papers,
        mg.n_patents,
        mg.n_assignees,
        mg.n_research_orgs,
        mg.npl_median_lag_years,
        mg.npl_n_links,
        mg.npl_reportable,
        mg.hhi,
        mg.hhi_reportable
    from {{ ref('mart_gap') }} mg
    where mg.cluster_id != 'c_noise'
      and not mg.is_noise
),

family_map as (
    select cluster_id, family_id, family_name, family_sort_order
    from {{ ref('seed_cluster_family') }}
),

top_assignees as (
    select
        mc.cluster_id,
        mc.canonical_name,
        mc.rank_in_cluster
    from {{ ref('mart_competitive') }} mc
    where mc.side = 'patent'
      and mc.rank_in_cluster = 1
      and mc.canonical_name is not null
),

top_researchers as (
    select
        mc.cluster_id,
        mc.canonical_name,
        mc.rank_in_cluster
    from {{ ref('mart_competitive') }} mc
    where mc.side = 'paper'
      and mc.rank_in_cluster = 1
      and mc.canonical_name is not null
),

per_cluster as (
    select
        g.cluster_id,
        fm.family_id,
        fm.family_name,
        fm.family_sort_order,
        g.n_papers,
        g.n_patents,
        g.n_assignees,
        g.n_research_orgs,
        g.npl_median_lag_years,
        g.npl_n_links,
        g.npl_reportable,
        g.hhi,
        g.hhi_reportable,
        ta.canonical_name  as top_assignee_name,
        tr.canonical_name  as top_researcher_name
    from gap g
    inner join family_map fm
        on fm.cluster_id = g.cluster_id
    left join top_assignees ta
        on ta.cluster_id = g.cluster_id
    left join top_researchers tr
        on tr.cluster_id = g.cluster_id
),

aggregated as (
    select
        family_id,
        family_name,
        family_sort_order,
        sum(n_papers)                                                as n_papers,
        sum(n_patents)                                               as n_patents,
        -- research breadth: distinct orgs across clusters (approximate — counts
        -- per-cluster unique orgs; cross-cluster dedup requires mart_competitive join)
        sum(n_research_orgs)                                         as n_research_orgs_sum,
        sum(n_assignees)                                             as n_assignees_sum,
        -- weighted median lag (weighted by npl_n_links per cluster)
        round(
            sum(
                case when npl_reportable
                     then npl_median_lag_years * npl_n_links
                     else 0 end
            ) / nullif(
                sum(case when npl_reportable then npl_n_links else 0 end),
                0
            ),
            2
        )                                                            as median_lag_years_weighted,
        sum(case when npl_reportable then npl_n_links else 0 end)   as total_npl_links,
        count(*)                                                     as n_clusters,
        -- top assignee and researcher = those with most clusters ranked #1
        mode() within group (order by top_assignee_name)            as top_assignee_name,
        mode() within group (order by top_researcher_name)          as top_researcher_name
    from per_cluster
    group by family_id, family_name, family_sort_order
)

select
    family_id,
    family_name,
    family_sort_order,
    n_papers,
    n_patents,
    n_clusters,
    -- patent density: patents per paper (higher = more IP-intensive relative to research)
    round(
        cast(n_patents as double) / nullif(n_patents + n_papers, 0),
        3
    )                                                                as patent_share,
    n_research_orgs_sum,
    n_assignees_sum,
    median_lag_years_weighted,
    total_npl_links,
    top_assignee_name,
    top_researcher_name

from aggregated
order by family_sort_order
