with history as (
    select * from {{ ref('stg_coin_price_history') }}
),

with_metrics as (
    select
        coin_id,
        price_date,
        price_usd,
        total_volume_usd as volume_usd,
        market_cap_usd,
        lag(price_usd) over (partition by coin_id order by price_date) as prev_price_usd,
        avg(price_usd) over (
            partition by coin_id order by price_date
            rows between 6 preceding and current row
        ) as price_7d_moving_avg
    from history
)

select
    coin_id,
    price_date,
    price_usd,
    volume_usd,
    market_cap_usd,
    price_7d_moving_avg,
    case
        when prev_price_usd is null or prev_price_usd = 0 then null
        else (price_usd - prev_price_usd) / prev_price_usd * 100
    end as daily_return_pct
from with_metrics
