-- Fails if any cluster has negative patent, institution, or paper counts.
select *
from {{ ref('mart_gap') }}
where n_patents < 0
   or n_oa_institutions < 0
   or n_research_orgs < 0
   or n_papers < 0
