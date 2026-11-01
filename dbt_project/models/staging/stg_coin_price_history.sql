-- CoinGecko's daily-interval endpoint includes an extra intraday point for
-- the most recent day (alongside its midnight point), so dedupe down to one
-- row per coin per calendar date, keeping the latest observation of that day.
with source as (
    select
        coin_id,
        to_timestamp(price_timestamp_ms / 1000)::date as price_date,
        price_timestamp_ms,
        price_usd,
        total_volume_usd,
        market_cap_usd
    from {{ source('raw', 'coin_price_history') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by coin_id, price_date
            order by price_timestamp_ms desc
        ) as rn
    from source
)

select
    coin_id,
    price_date,
    price_usd,
    total_volume_usd,
    market_cap_usd
from deduped
where rn = 1
