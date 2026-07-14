{{
  config(
    materialized='table'
  )
}}

/*
  Gold mart: family-level scorecard — one row per DOCUMENT-LEVEL technology
  family (5-way: euv / lasers / si_photonics / neuromorphic / in_memory).

  This is a rebuild (2026-07) off fact_patent_filing.family_id /
  fact_publication.family_id directly -- each document's OWN direct family,
  independent of the cluster it algorithmically landed in (see those models'
  docstrings). The prior version of this mart aggregated via seed_cluster_family
  (a CLUSTER-grained display label, majority-vote over documents, 3-way +
  'mixed') -- that basis under-counted every family (it excludes 'mixed'-labelled
  clusters and the ~41% of documents in the unclustered 'noise' cluster) and
  attributed documents by their cluster's majority rather than their own CPC/
  topic. seed_cluster_family remains correct and unchanged for its own purpose
  (the Technology Landscape map's cluster colouring) -- it is simply no longer
  the basis for family-level counting anywhere. See fact_patent_filing.sql /
  fact_publication.sql docstrings for why family_id is the authoritative column.

  Claim: "5 technology families" front-door scorecard (papers, patents, research
  org / assignee breadth, median citation lag). All US-patent-only; stated in UI.

  patent_share = this family's n_patents / total n_patents across all 5 families
  (2026-07: redefined from n_patents / (n_patents + n_papers)). It answers "what
  slice of all US patenting activity does this family represent" -- a composition
  question over the patent pool alone. It is NOT a research-to-patent conversion
  or capture rate: papers do not appear in the formula, and a family can have a
  high patent_share while still having low research capture, or vice versa.

  Documents with no resolvable family_id (patents whose PRIMARY CPC is off the
  six scope subclasses -- they entered scope via a secondary code; papers whose
  T10502 neuromorphic/in-memory keyword tiebreak matched neither pattern) are
  NOT a row in this mart -- they are a disclosed "unattributed" bucket computed
  separately by the UI at render time (rule: no invented data, NULL stays NULL
  and disclosed, never silently redistributed into one of the 5 families).

  avg_grant_lag_years = mean(grant_date - filing_date) per family, in years --
  the ONE narrow, explicitly authorised exception to "grant date is never used
  for a time metric" (CLAUDE.md rule 2, 2026-07 amendment). This is a data-
  completeness diagnostic, not an R&D-velocity claim: it exists solely so the
  UI can shade the recent filing years that are under-counted because those
  patents haven't yet cleared USPTO examination (Family Deepdive velocity
  chart). It is never blended with median_lag_years_weighted (citation lag)
  and never described as "lead time" or innovation speed.

  Depends on: fact_patent_filing, fact_publication, fact_npl_link, dim_patent
  Output: dev.duckdb main_marts.mart_family
*/

with family_meta (family_id, family_name, family_sort_order) as (
    values
        ('euv',          'EUV Lithography',        1),
        ('lasers',       'Lasers',                  2),
        ('si_photonics', 'Silicon Photonics',       3),
        ('neuromorphic', 'Neuromorphic',            4),
        ('in_memory',    'In-Memory Compute',       5)
),

patent_counts as (
    select family_id, count(distinct patent_id) as n_patents
    from {{ ref('fact_patent_filing') }}
    where family_id is not null
    group by 1
),

-- Denominator for patent_share: total US patents across all 5 families (the
-- disclosed "unattributed" bucket is intentionally excluded -- it is never
-- redistributed into any family-level ratio, see module docstring).
patent_totals as (
    select sum(n_patents) as total_patents
    from patent_counts
),

paper_counts as (
    select family_id, count(distinct work_id) as n_papers
    from {{ ref('fact_publication') }}
    where family_id is not null
    group by 1
),

-- Research/assignee breadth: exact distinct-org counts at family grain. (The
-- prior cluster-rollup version of this mart summed per-cluster unique-org
-- counts across clusters -- an approximation, since the same org active in two
-- clusters was double-counted. There is no cluster to cross here, so this is
-- now exact, not just re-derived on a new basis.)
patent_org_breadth as (
    select family_id, count(distinct org_id) as n_assignees
    from {{ ref('fact_patent_filing') }}
    where family_id is not null and org_id is not null
    group by 1
),

paper_org_breadth as (
    select family_id, count(distinct org_id) as n_research_orgs
    from {{ ref('fact_publication') }}
    where family_id is not null and org_id is not null
    group by 1
),

-- One row per distinct (patent, family) -- fact_patent_filing is exploded per
-- assignee, so joining fact_npl_link directly against it would double-count a
-- multi-assignee patent's NPL links.
patent_family as (
    select distinct patent_id, family_id
    from {{ ref('fact_patent_filing') }}
    where family_id is not null
),

-- TRUE median over every NPL-linked citation in the family (not a weighted
-- average of per-cluster medians, which the prior version computed and which
-- is a biased approximation of the true median). Same >= 20-link reportability
-- floor used throughout the project (mart_gap, cluster-level).
npl_lag as (
    select
        pf.family_id,
        count(*)                                     as npl_n_links,
        round(median(nl.citation_lag_years), 2)      as npl_median_lag_years
    from {{ ref('fact_npl_link') }} nl
    inner join patent_family pf on pf.patent_id = nl.patent_id
    group by 1
),

-- Grant lag: mean(grant_date - filing_date) per family, in years. The narrow,
-- authorised exception to the grant-date ban (see module docstring) -- a
-- data-completeness diagnostic, not a velocity claim. Every family clears
-- hundreds of patents with a grant_date, so no reportability floor is needed
-- here (unlike npl_lag's >= 20-link floor).
grant_lag as (
    select
        pf.family_id,
        avg(date_diff('day', dp.filing_date, dp.grant_date) / 365.25) as avg_grant_lag_years
    from patent_family pf
    inner join {{ ref('dim_patent') }} dp on dp.patent_id = pf.patent_id
    where dp.grant_date is not null
    group by 1
)

select
    fm.family_id,
    fm.family_name,
    fm.family_sort_order,
    coalesce(pc.n_papers, 0)                          as n_papers,
    coalesce(ptc.n_patents, 0)                         as n_patents,
    -- this family's share of all US patents in scope (across the 5 families) --
    -- a slice of the patent pool, not a claim about how much research got
    -- captured as IP. Papers do not appear in this ratio at all.
    round(
        cast(coalesce(ptc.n_patents, 0) as double)
        / nullif(pt.total_patents, 0),
        3
    )                                                   as patent_share,
    coalesce(pob.n_research_orgs, 0)                   as n_research_orgs_sum,
    coalesce(paob.n_assignees, 0)                      as n_assignees_sum,
    case when coalesce(nl.npl_n_links, 0) >= 20
        then nl.npl_median_lag_years
    end                                                 as median_lag_years_weighted,
    coalesce(nl.npl_n_links, 0)                        as total_npl_links,
    round(gl.avg_grant_lag_years, 2)                   as avg_grant_lag_years

from family_meta fm
left join paper_counts       pc  on pc.family_id  = fm.family_id
left join patent_counts      ptc on ptc.family_id = fm.family_id
left join paper_org_breadth  pob on pob.family_id = fm.family_id
left join patent_org_breadth paob on paob.family_id = fm.family_id
left join npl_lag            nl  on nl.family_id  = fm.family_id
left join grant_lag          gl  on gl.family_id  = fm.family_id
cross join patent_totals     pt

order by fm.family_sort_order
