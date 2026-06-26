-- Fails if any (cluster_id, side, org_id_key) combination appears more than once.
select cluster_id, side, org_id_key, count(*) as n
from {{ ref('mart_competitive') }}
group by cluster_id, side, org_id_key
having count(*) > 1
