{{
  config(
    materialized='table'
  )
}}

/*
  Dimension: one row per OpenAlex work in scope.
  Identity/text only -- cluster_id is deliberately NOT carried here. The paper's
  cluster lives in the bridge fact_document_cluster (doc_type='paper'); join that
  (or fact_publication) when a paper's cluster is needed. Keeping the dim
  cluster-free is what makes the ML step sit cleanly downstream of the dims in a
  single acyclic graph: the embedding/clustering asset reads this dim, so this
  dim must not in turn read the clusters (that was the old cycle -- see
  ARCHITECTURE.md §7 / docs/workflow.md).
  Depends on: stg_openalex_works
  Output: dev.duckdb marts.dim_paper
*/

select
    w.work_id,
    w.work_url,
    w.doi,
    w.doi_bare,
    w.title,
    w.publication_date,
    w.publication_year,
    w.abstract,
    w.primary_topic_id,
    w.primary_topic_name

from {{ ref('stg_openalex_works') }} w
