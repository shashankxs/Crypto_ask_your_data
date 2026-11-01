with source as (
    select * from {{ source('raw_fear_greed', 'fear_greed_index') }}
),

deduped as (
    select
        *,
        row_number() over (partition by index_date order by loaded_at desc) as rn
    from source
)

select
    index_date,
    value as fear_greed_value,
    value_classification as fear_greed_label
from deduped
where rn = 1
