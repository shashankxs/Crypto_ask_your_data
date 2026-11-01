with source as (
    select * from {{ source('raw_ohlc', 'coin_ohlc') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by coin_id, candle_time_ms
            order by loaded_at desc
        ) as rn
    from source
)

select
    coin_id,
    to_timestamp(candle_time_ms / 1000) as candle_time,
    open,
    high,
    low,
    close
from deduped
where rn = 1
