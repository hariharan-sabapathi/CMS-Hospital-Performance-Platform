select
    {{ dbt_utils.generate_surrogate_key(['fiscal_year', 'domain']) }} as fiscal_period_key,
    fiscal_year,
    domain,
    cast(performance_start as date)  as performance_start,
    cast(performance_end as date)    as performance_end,
    lag_years,
    lag_note
from {{ ref('fiscal_period_reference') }}
