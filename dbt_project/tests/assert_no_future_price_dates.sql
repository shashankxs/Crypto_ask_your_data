-- Singular test: a price_date in the future would indicate a timezone bug
-- or bad data from the source API. Returns offending rows (dbt fails the
-- test if this query returns any rows).
select *
from {{ ref('fct_coin_price_daily') }}
where price_date > current_date
