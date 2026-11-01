with source as (
    select * from raw.coin_market_snapshot
)

select
    loaded_at,
    coin_id,
    upper(symbol)                  as symbol,
    name,
    current_price                  as price_usd,
    market_cap                     as market_cap_usd,
    market_cap_rank,
    total_volume                   as volume_usd,
    price_change_pct_24h,
    price_change_pct_7d,
    circulating_supply,
    ath                            as all_time_high_usd,
    ath_change_pct
from source
