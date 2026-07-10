-- Fails if seed_cluster_family's two-threshold floor is violated. Independently
-- recomputes, per cluster, purity (dominant real family / family-resolvable
-- docs) and coverage (resolvable docs / all docs) from the source tables, then
-- checks the label agrees:
--   * a real-family label requires purity >= 0.80 AND coverage >= 0.50
--   * a 'mixed' label requires that BOTH thresholds are NOT jointly met
with votes as (
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
        end as fam
    from (
        select distinct cluster_id, patent_id, primary_cpc
        from {{ ref('fact_patent_filing') }}
        where cluster_id is not null and cluster_id != 'c_noise'
    )
    union all
    select
        cluster_id,
        case primary_topic_id
            when 'https://openalex.org/T11338' then 'euv'
            when 'https://openalex.org/T11429' then 'silicon_photonics'
            when 'https://openalex.org/T10299' then 'silicon_photonics'
            when 'https://openalex.org/T10502' then 'neuromorphic_in_memory'
            else 'mixed'
        end
    from {{ ref('dim_paper') }}
    where cluster_id is not null and cluster_id != 'c_noise'
),

totals as (
    select cluster_id, count(*) as n_total
    from votes
    group by 1
),

real_totals as (
    select cluster_id, count(*) as n_real
    from votes
    where fam != 'mixed'
    group by 1
),

dom as (
    select cluster_id, max(n) as n_dom
    from (select cluster_id, fam, count(*) as n from votes where fam != 'mixed' group by 1, 2)
    group by 1
),

shares as (
    select
        t.cluster_id,
        coalesce(d.n_dom, 0)::double / nullif(rt.n_real, 0) as purity,
        coalesce(rt.n_real, 0)::double / t.n_total          as coverage
    from totals t
    left join real_totals rt on rt.cluster_id = t.cluster_id
    left join dom d          on d.cluster_id  = t.cluster_id
)

select scf.cluster_id, scf.family_id, s.purity, s.coverage
from {{ ref('seed_cluster_family') }} scf
join shares s on s.cluster_id = scf.cluster_id
where (scf.family_id != 'mixed' and not (s.purity >= 0.80 and s.coverage >= 0.50))
   or (scf.family_id = 'mixed'  and (s.purity >= 0.80 and s.coverage >= 0.50))
