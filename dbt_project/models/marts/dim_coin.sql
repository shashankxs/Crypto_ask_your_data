-- An accumulating dimension: the market-cap snapshot and the price-history
-- extract are refreshed independently and the top-25 list can shift between
-- runs, so a coin can appear in one but briefly not the other. Sourcing
-- coin_id from the union of both keeps referential integrity with
-- fct_coin_price_daily intact instead of silently dropping history rows
-- for a coin that just fell out of today's top 25.
with latest_snapshot_attrs as (
    select
        coin_id,
        symbol,
        name,
        image_url,
        market_cap_rank,
        row_number() over (partition by coin_id order by loaded_at desc) as rn
    from {{ ref('stg_coin_snapshot') }}
    qualify rn = 1
),

all_known_coins as (
    select coin_id from {{ ref('stg_coin_snapshot') }}
    union
    select coin_id from {{ ref('stg_coin_price_history') }}
)

select
    c.coin_id,
    s.symbol,
    s.name,
    s.image_url,
    s.market_cap_rank
from all_known_coins c
left join latest_snapshot_attrs s using (coin_id)
