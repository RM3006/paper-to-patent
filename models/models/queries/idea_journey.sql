{{
  config(
    materialized='view'
  )
}}

/*
  Canonical query: "idea journey" for a given org_id.
  Returns papers the org published, patents the org filed, and the NPL links
  connecting them (from fact_npl_link, populated in Part 4 Step 2).

  Time metric: citation_lag_days / citation_lag_years = paper publication_date →
  patent filing_date. Never "lead time" or "time to market" — those imply causation.

  Usage: filter the view by org_id in a subsequent WHERE clause:
    SELECT * FROM main_marts.idea_journey WHERE org_id = 'org_nvidia';

  Depends on: dim_organization, fact_publication, dim_paper,
              fact_patent_filing, dim_patent, fact_npl_link
  Output: dev.duckdb marts.idea_journey (view)
*/

with papers as (
    select
        fp.org_id,
        fp.work_id,
        p.title                 as paper_title,
        p.publication_date,
        p.doi,
        p.primary_topic_name
    from {{ ref('fact_publication') }} fp
    inner join {{ ref('dim_paper') }} p
        on p.work_id = fp.work_id
    where fp.org_id is not null
),

patents as (
    select
        ff.org_id,
        ff.patent_id,
        pat.title               as patent_title,
        ff.filing_date,
        pat.grant_date,
        ff.primary_cpc
    from {{ ref('fact_patent_filing') }} ff
    inner join {{ ref('dim_patent') }} pat
        on pat.patent_id = ff.patent_id
    where ff.org_id is not null
)

select
    o.org_id,
    o.canonical_name                        as org_name,

    -- paper side
    pa.work_id,
    pa.paper_title,
    pa.publication_date,
    pa.doi,
    pa.primary_topic_name,

    -- patent side
    pt.patent_id,
    pt.patent_title,
    pt.filing_date,
    pt.grant_date,
    pt.primary_cpc,

    -- NPL link (populated after Step 2; NULL until then)
    nl.match_method                         as npl_match_method,
    nl.confidence                           as npl_confidence,
    nl.citation_lag_days,
    nl.citation_lag_years

from {{ ref('dim_organization') }} o
left join papers pa
    on pa.org_id = o.org_id
left join patents pt
    on pt.org_id = o.org_id
left join {{ ref('fact_npl_link') }} nl
    on nl.patent_id = pt.patent_id
    and nl.work_id  = pa.work_id
