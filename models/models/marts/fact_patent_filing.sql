{{
  config(
    materialized='table'
  )
}}

/*
  Fact: one row per (patent, assignee) combination in scope.
  Time metric anchor: filing_date (never grant_date).
  org_id attached via crosswalk on assignee_id.
  NULL org_id is allowed when an assignee is individual or not in the crosswalk.

  family_id is this patent's OWN direct technology family, derived from its own
  primary_cpc prefix -- independent of which cluster it algorithmically landed in.
  This is the authoritative column for family-level counting (patent-share, HHI,
  leaderboards): a cluster's majority family (seed_cluster_family, joined via
  cluster_id) is a display label for the cluster as a whole and should never be
  used to attribute an individual document's family, since ~44% of clusters mix
  Lasers/Silicon-Photonics or Neuromorphic/In-Memory content (measured 2026-07-04).

  Depends on: stg_patents_scoped, stg_assignees, int_org_crosswalk
  Output: dev.duckdb marts.fact_patent_filing
*/

select
    p.patent_id,
    p.filing_date,
    p.grant_date,              -- metadata only; never used in time metrics
    p.patent_type,
    cpc_primary.primary_cpc,

    case
        when cpc_primary.primary_cpc like 'G03F%' then 'euv'
        when cpc_primary.primary_cpc like 'H01S%' then 'lasers'
        when cpc_primary.primary_cpc like 'G02B%' then 'si_photonics'
        when cpc_primary.primary_cpc like 'G06N%' then 'neuromorphic'
        when cpc_primary.primary_cpc like 'G11C%' then 'in_memory'
        when cpc_primary.primary_cpc like 'H10N%' then 'in_memory'
    end                         as family_id,

    a.assignee_id,
    a.org_name                 as assignee_name,
    a.assignee_sequence,

    x.org_id,
    x.match_method             as org_match_method,
    x.confidence               as org_confidence,
    fdc.cluster_id

from {{ ref('stg_patents_scoped') }} p
-- bring in primary CPC code for the patent
left join (
    select patent_id, cpc_group as primary_cpc
    from {{ ref('stg_cpc') }}
    where cpc_sequence = 0
) cpc_primary
    on cpc_primary.patent_id = p.patent_id
left join {{ ref('stg_assignees') }} a
    on a.patent_id = p.patent_id
left join {{ ref('int_org_crosswalk') }} x
    on x.source = 'patentsview'
    and x.source_id = a.assignee_id
left join {{ ref('fact_document_cluster') }} fdc
    on fdc.doc_id = p.patent_id
    and fdc.doc_type = 'patent'
