-- Fails if any patent_id in fact_npl_link draws edges from both Marx & Fuegi
-- and our own matcher (doi/fuzzy_title).
--
-- fact_npl_link.sql implements a hybrid seam: for any patent Marx & Fuegi
-- covers at all, ALL of that patent's edges must come from Marx & Fuegi; the
-- matcher only fills patents Marx & Fuegi has zero coverage of (its vintage
-- caps out around patents granted ~early 2023). This is enforced by an
-- explicit "where patent_id not in (mf_patents)" filter on the matcher CTE --
-- this test guards against that filter regressing silently in a future edit.
select patent_id
from {{ ref('fact_npl_link') }}
group by patent_id
having count(distinct case when link_source = 'marx_fuegi' then 1 else 0 end) > 1
