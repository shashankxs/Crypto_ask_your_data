with ranked as (
    select
        *,
        row_number() over (partition by coin_id order by loaded_at desc) as rn
    from {{ ref('stg_coin_snapshot') }}
)

select
    coin_id,
    symbol,
    name,
    market_cap_rank,
    price_usd,
    market_cap_usd,
    volume_usd,
    price_change_pct_24h,
    price_change_pct_7d,
    circulating_supply,
    all_time_high_usd,
    ath_change_pct,
    loaded_at as snapshot_loaded_at
from ranked
where rn = 1
