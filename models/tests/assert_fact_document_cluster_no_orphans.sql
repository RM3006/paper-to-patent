-- Fails if fact_document_cluster contains a doc_id absent from its own dimension --
-- i.e. a map/cluster point for a document that no longer exists in the served
-- corpus. This is the guard the Part 0-7 checkpoint review (2026-07-04, Issue 1)
-- recommended after finding 1,103 such orphans from a stale Part 5 run; the
-- inner join added to fact_document_cluster.sql makes this structurally
-- impossible today, but nothing previously caught a regression if that join
-- were ever weakened.
select doc_id, doc_type, 'paper' as expected_dim
from {{ ref('fact_document_cluster') }}
where doc_type = 'paper'
  and doc_id not in (select work_id from {{ ref('dim_paper') }})

union all

select doc_id, doc_type, 'patent' as expected_dim
from {{ ref('fact_document_cluster') }}
where doc_type = 'patent'
  and doc_id not in (select patent_id from {{ ref('dim_patent') }})
