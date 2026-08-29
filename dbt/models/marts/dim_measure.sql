select
    {{ dbt_utils.generate_surrogate_key(['measure_id']) }} as measure_key,
    measure_id,
    measure_name,
    source,
    domain,
    direction,
    unit
from {{ ref('measure_reference') }}
