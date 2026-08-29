with ed as (
    select * from {{ ref('stg_ed__throughput') }}
),

hospital as (
    select hospital_key, ccn from {{ ref('dim_hospital') }}
),

measure as (
    select measure_key, measure_id from {{ ref('dim_measure') }}
),

annual_period as (
    select fiscal_period_key from {{ ref('dim_fiscal_period') }} where domain = 'ed_annual'
),

rolling_period as (
    select fiscal_period_key from {{ ref('dim_fiscal_period') }} where domain = 'ed_rolling12'
)

select
    h.hospital_key,
    m.measure_key,
    case when e.measure_id in ('EDV', 'OP_22') then a.fiscal_period_key else r.fiscal_period_key end as period_key,
    e.reported_value,
    e.score_raw,
    e.sample_size,
    e.footnote_code
from ed e
join hospital h on e.ccn = h.ccn
join measure m on e.measure_id = m.measure_id
cross join annual_period a
cross join rolling_period r
