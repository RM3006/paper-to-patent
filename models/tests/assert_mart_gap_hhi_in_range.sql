-- Fails if any reportable HHI is outside [0, 1].
select *
from {{ ref('mart_gap') }}
where hhi is not null
  and (hhi < 0 or hhi > 1)
