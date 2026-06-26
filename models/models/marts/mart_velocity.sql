{{
  config(
    materialized='table'
  )
}}

/*
  Mart: technology velocity — research-onset vs patent-onset time series and citation lags.

  Claim basis:
    - NPL-linked citation lag: derived from fact_npl_link (publication_date → filing_date),
      anchored on the CITING PATENT's cluster_id. Never described as "lead time."
      npl_median_lag_years is NULL and npl_reportable = false when npl_n_links < 20.
    - Cohort lag (cohort_lag_years): median(paper pub year) vs median(patent filing year)
      per cluster. SOFT ESTIMATE — papers and patents in the same cluster are not
      necessarily linked by an NPL citation. Column prefix "cohort_" signals this.
    - Time series: annual distinct paper/patent counts per cluster.

  Grain: one row per (cluster_id, year).
  Cluster-level lag metrics are denormalized across year rows for the same cluster.
  c_noise is included (is_noise = true); exclude from headline citation-lag findings.

  Depends on: fact_publication, fact_patent_filing, fact_npl_link, dim_patent,
              dim_technology_cluster
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

-- NPL-linked citation lag; patent cluster is the anchor per project decision
npl_lag as (
    select
        dpat.cluster_id,
        count(*)                                        as npl_n_links,
        round(median(nl.citation_lag_years), 2)         as npl_median_lag_years
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
        median(extract(year from filing_date)::int)     as med_filing_year
    from {{ ref('fact_patent_filing') }}
    where cluster_id is not null
    group by 1
),

cohort_lag as (
    select
        pp.cluster_id,
        round(pp.med_pub_year, 1)                       as cohort_med_pub_year,
        round(pt.med_filing_year, 1)                    as cohort_med_filing_year,
        round(pt.med_filing_year - pp.med_pub_year, 1)  as cohort_lag_years
    from cohort_paper pp
    inner join cohort_patent pt on pt.cluster_id = pp.cluster_id
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
    coalesce(pts.patent_count, 0)                       as patent_count,

    -- NPL-linked citation lag (patent's cluster anchor).
    -- npl_median_lag_years is NULL when npl_n_links < 20 (not reportable).
    case when coalesce(nl.npl_n_links, 0) >= 20
        then nl.npl_median_lag_years
    end                                                 as npl_median_lag_years,
    coalesce(nl.npl_n_links, 0)                         as npl_n_links,
    coalesce(nl.npl_n_links, 0) >= 20                   as npl_reportable,

    -- Cohort lag (SOFT — not NPL-linked; see claim basis above)
    cl.cohort_med_pub_year,
    cl.cohort_med_filing_year,
    cl.cohort_lag_years

from all_years ay
inner join {{ ref('dim_technology_cluster') }} dtc
    on dtc.cluster_id = ay.cluster_id
left join paper_series ps
    on ps.cluster_id = ay.cluster_id and ps.year = ay.year
left join patent_series pts
    on pts.cluster_id = ay.cluster_id and pts.year = ay.year
left join npl_lag nl
    on nl.cluster_id = ay.cluster_id
left join cohort_lag cl
    on cl.cluster_id = ay.cluster_id
