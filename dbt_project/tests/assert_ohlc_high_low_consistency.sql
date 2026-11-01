-- Singular test: a candle's high must be the max and low must be the min
-- of (open, high, low, close) — violations would indicate a parsing bug or
-- bad data from the source API.
select *
from {{ ref('fct_coin_ohlc') }}
where high < open
   or high < close
   or high < low
   or low > open
   or low > close
