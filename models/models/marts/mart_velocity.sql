{{
  config(
    materialized='table'
  )
}}

/*
  Mart: technology velocity — annual paper and patent counts per cluster.

  Grain: one row per (cluster_id, year). Pure time series — no cluster-level
  lag scalars. Citation lag and cohort lag metrics live in mart_gap (per cluster).

  c_noise is included (is_noise = true); exclude from headline trend findings.

  Depends on: fact_publication, fact_patent_filing, dim_technology_cluster
  Output: dev.duckdb main_marts.mart_velocity
*/

with paper_series as (
    select
        cluster_id,
        publication_year                                as year,
        count(distinct work_id)                         as paper_count
    from {{ ref('fact_publication') }}
    where cluster_id is not null
    group by 1, 2
),

patent_series as (
    select
        cluster_id,
        extract(year from filing_date)::int             as year,
        count(distinct patent_id)                       as patent_count
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1, 2
),

-- All (cluster, year) combinations present in either series
all_years as (
    select cluster_id, year from paper_series
    union
    select cluster_id, year from patent_series
)

select
    ay.cluster_id,
    dtc.tagline,
    ay.cluster_id = 'c_noise'                          as is_noise,
    ay.year,

    coalesce(ps.paper_count, 0)                         as paper_count,
    coalesce(pts.patent_count, 0)                       as patent_count

from all_years ay
inner join {{ ref('dim_technology_cluster') }} dtc
    on dtc.cluster_id = ay.cluster_id
left join paper_series ps
    on ps.cluster_id = ay.cluster_id and ps.year = ay.year
left join patent_series pts
    on pts.cluster_id = ay.cluster_id and pts.year = ay.year
