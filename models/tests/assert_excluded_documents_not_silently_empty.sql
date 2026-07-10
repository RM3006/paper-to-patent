-- Fails loudly if ML has genuinely run (ml_intermediate.clusters has rows) but
-- ml_intermediate.excluded_documents is empty.
--
-- create_external_sources() registers excluded_documents as an empty relation
-- only as a *cold-start* fallback, before Part 5 (document_embeddings) has
-- ever produced a snapshot -- see create_external_sources.sql and
-- ARCHITECTURE.md Section 8. In that genuine cold-start case, clusters is
-- also unregistered/empty, since clustering depends on embeddings having run
-- first -- so this test is a no-op then (both sides are empty; nothing to
-- compare).
--
-- But document_embeddings writes embeddings.parquet and excluded_documents.
-- parquet together, in the same multi_asset call, and clustering can only
-- read a real embeddings snapshot. So if clusters has rows, excluded_documents
-- must also have a real (non-empty) snapshot -- at this corpus size, the
-- quality gate always finds *some* placeholder/non-English/version-style
-- documents to exclude. An empty excluded_documents alongside a populated
-- clusters table means the wrong (or a partially-written) snapshot was
-- resolved -- e.g. a partial multi_asset failure, a deleted/corrupted R2
-- object, or a source_root misconfiguration -- and stg_openalex_works /
-- stg_patents_scoped would silently stop excluding those documents from the
-- served marts (CLAUDE.md: "fail loudly, never silently coerce").
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
