select
    coin_id,
    candle_time,
    open,
    high,
    low,
    close
from {{ ref('stg_coin_ohlc') }}
