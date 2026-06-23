{{
  config(
    materialized='table'
  )
}}

/*
  Fact: resolved paper↔patent edges via non-patent-literature citations.
  The citation-lag interval (publication_date → filing_date) is computed here.
  All edges carry match_method + confidence (hard rule per CLAUDE.md §3).
  Never describes the interval as "lead time" or implies causation.

  Input is the Python NPL matcher output written to R2 by the
  npl_links_raw Dagster asset (Part 4 Step 2).
  Depends on: er_intermediate.npl_links (R2 intermediate), dim_paper, dim_patent
  Output: dev.duckdb marts.fact_npl_link
*/

with raw as (
    select *
    from {{ source('er_intermediate', 'npl_links') }}
),

enriched as (
    select
        r.patent_id,
        r.work_id,
        r.match_method,
        r.confidence,
        r.doi_extracted,

        -- citation lag: paper publication → patent filing date
        p.publication_date,
        pat.filing_date,
        datediff('day', p.publication_date, pat.filing_date)   as citation_lag_days,
        round(
            datediff('day', p.publication_date, pat.filing_date) / 365.25,
            2
        )                                                       as citation_lag_years

    from raw r
    inner join {{ ref('dim_paper') }} p
        on p.work_id = r.work_id
    inner join {{ ref('dim_patent') }} pat
        on pat.patent_id = r.patent_id
    -- Only keep links where paper was published before the patent was filed
    where p.publication_date < pat.filing_date
)

select * from enriched
