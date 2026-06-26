-- Fails if any reportable NPL citation lag is negative.
-- A negative lag would mean a paper was published AFTER the patent was filed —
-- impossible given fact_npl_link already filters publication_date < filing_date.
select *
from {{ ref('mart_gap') }}
where npl_median_lag_years is not null
  and npl_median_lag_years < 0
