-- Fails if any (cluster_id, year) pair appears more than once in mart_velocity.
select cluster_id, year, count(*) as n
from {{ ref('mart_velocity') }}
group by cluster_id, year
having count(*) > 1
