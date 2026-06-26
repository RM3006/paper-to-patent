-- Fails if any cluster has negative patent or paper counts.
select *
from {{ ref('mart_gap') }}
where n_patents < 0
   or n_institutions < 0
   or n_papers < 0
