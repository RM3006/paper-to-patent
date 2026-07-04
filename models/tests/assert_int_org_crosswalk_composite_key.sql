-- Fails if any (source, source_id) combination appears more than once.
-- Guards against the source view silently unioning two overlapping R2
-- snapshots (found live 2026-06-26: v2026-06-22 + v2026-06-26 together
-- produced 16,198 duplicate rows and 32 conflicting org_id assignments).
select source, source_id, count(*) as n
from {{ ref('int_org_crosswalk') }}
group by source, source_id
having count(*) > 1
