-- Joins two independently-sourced extracts (CoinGecko price history and the
-- alternative.me Fear & Greed Index) on calendar date, so the AI layer can
-- answer cross-source questions like "was sentiment fearful on days bitcoin
-- dropped the most?" instead of only ever querying one API's data in isolation.
with market_daily as (
    select
        price_date,
        avg(daily_return_pct) as market_avg_daily_return_pct,
        sum(volume_usd) as market_total_volume_usd
    from {{ ref('fct_coin_price_daily') }}
    group by price_date
),

sentiment as (
    select * from {{ ref('stg_fear_greed') }}
)

select
    coalesce(m.price_date, s.index_date) as date,
    m.market_avg_daily_return_pct,
    m.market_total_volume_usd,
    s.fear_greed_value,
    s.fear_greed_label
from market_daily m
full outer join sentiment s on m.price_date = s.index_date
