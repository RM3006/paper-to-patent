-- Fails if any individual org share is outside [0, 1].
-- Per-org share is always <= 1 even on the paper side (where cluster sum can exceed 1).
select *
from {{ ref('mart_competitive') }}
where share < 0 or share > 1
