-- Fails loudly if clustering has genuinely run (ml_intermediate.clusters has
-- rows) but ml_intermediate.excluded_documents is empty.
--
-- create_external_sources() registers excluded_documents as an empty relation
-- only as a defensive fallback, before the document_exclusions asset has ever
-- produced a snapshot (e.g. a standalone `dbt build` on a fresh setup) -- see
-- create_external_sources.sql and ARCHITECTURE.md Section 7. In a normal
-- orchestrated run, document_exclusions runs upstream of staging and clustering
-- runs even later, so if clusters has rows the exclusions snapshot must already
-- exist and be non-empty -- at this corpus size the quality gate always finds
-- *some* version-style / non-English / placeholder documents to screen out.
-- An empty excluded_documents alongside a populated clusters table therefore
-- means the wrong (or a partially-written) snapshot resolved -- a deleted or
-- corrupted R2 object, or a source_root misconfiguration -- and
-- stg_openalex_works / stg_patents_scoped would silently stop excluding those
-- documents from the served marts (CLAUDE.md: "fail loudly, never silently
-- coerce").
with cluster_state as (
    select count(*) as n_clusters
    from {{ source('ml_intermediate', 'clusters') }}
),

excluded_state as (
    select count(*) as n_excluded
    from {{ source('ml_intermediate', 'excluded_documents') }}
)

select cluster_state.n_clusters, excluded_state.n_excluded
from cluster_state, excluded_state
where cluster_state.n_clusters > 0
  and excluded_state.n_excluded = 0
