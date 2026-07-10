{{
  config(
    materialized='table'
  )
}}

/*
  Fact: resolved paper↔patent edges via non-patent-literature citations.

  Hybrid source, partitioned per patent (the "seam"): for any patent Marx &
  Fuegi ("Reliance on Science", CC-BY-4.0, Zenodo 7996195) covers at all, ALL
  of that patent's edges come from Marx & Fuegi -- gold-standard, published
  citation data. For patents M&F has zero coverage of (its vintage caps out
  around patents granted ~early 2023), edges come from our own DOI +
  fuzzy-title matcher (npl_links_raw) instead. No patent draws edges from
  both sources -- see assert_fact_npl_link_single_source.sql.

  The citation-lag interval (publication_date → filing_date) is computed here.
  All edges carry match_method + confidence (hard rule per CLAUDE.md §3).
  Never describes the interval as "lead time" or implies causation.

  Depends on: er_intermediate.mf_npl_links, er_intermediate.npl_links (both
  R2 intermediate), dim_paper, dim_patent
  Output: dev.duckdb marts.fact_npl_link
*/

with mf as (
    select
        patent_id,
        work_id,
        match_method,
        confidence,
        'marx_fuegi'            as link_source,
        cast(null as varchar)   as doi_extracted,
        confscore                as mf_confscore,
        wherefound                as mf_wherefound,
        self                    as mf_self
    from {{ source('er_intermediate', 'mf_npl_links') }}
),

mf_patents as (
    select distinct patent_id from mf
),

matcher as (
    select
        patent_id,
        work_id,
        match_method,
        confidence,
        -- confidence already distinguishes the matcher's two routes:
        -- 'high' only comes from the DOI route, 'medium' only from fuzzy-title
        case when confidence = 'high' then 'doi' else 'fuzzy_title' end as link_source,
        doi_extracted,
        cast(null as integer)   as mf_confscore,
        cast(null as varchar)   as mf_wherefound,
        cast(null as varchar)   as mf_self
    from {{ source('er_intermediate', 'npl_links') }}
    -- the seam: only fills patents Marx & Fuegi has zero coverage of
    where patent_id not in (select patent_id from mf_patents)
),

combined as (
    select * from mf
    union all
    select * from matcher
),

enriched as (
    select
        c.patent_id,
        c.work_id,
        c.match_method,
        c.confidence,
        c.link_source,
        c.doi_extracted,
        c.mf_confscore,
        c.mf_wherefound,
        c.mf_self,

        -- citation lag: paper publication → patent filing date
        p.publication_date,
        pat.filing_date,
        datediff('day', p.publication_date, pat.filing_date)   as citation_lag_days,
        round(
            datediff('day', p.publication_date, pat.filing_date) / 365.25,
            2
        )                                                       as citation_lag_years

    from combined c
    inner join {{ ref('dim_paper') }} p
        on p.work_id = c.work_id
    inner join {{ ref('dim_patent') }} pat
        on pat.patent_id = c.patent_id
    -- Only keep links where paper was published before the patent was filed
    where p.publication_date < pat.filing_date
)

select * from enriched
