with ranked as (
    select
        coin_id,
        symbol,
        name,
        market_cap_rank,
        row_number() over (partition by coin_id order by loaded_at desc) as rn
    from {{ ref('stg_coin_snapshot') }}
)

select
    coin_id,
    symbol,
    name,
    market_cap_rank
from ranked
where rn = 1
