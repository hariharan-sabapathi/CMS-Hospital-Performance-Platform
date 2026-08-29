{#-
    Pivots the long stg_ed__throughput measure readings wide, one row per
    hospital (CCN). Boarding time has no dedicated CMS measure in this
    dataset (the measure set is EDV, OP_18a-d, OP_22, OP_23 — see README);
    OP_18d (median time before transfer to another facility) is used as the
    boarding-time proxy since transferred patients are the ones literally
    waiting ("boarding") in the ED for their next placement. See
    dbt/seeds/measure_reference.csv for the documented definition.
-#}

with ed as (
    select * from {{ ref('stg_ed__throughput') }}
),

pivoted as (
    select
        ccn,
        max(case when measure_id = 'EDV' then score_raw end)                      as ed_volume_category,
        max(case when measure_id = 'OP_18a' then reported_value end)              as median_arrival_to_departure_minutes,
        max(case when measure_id = 'OP_18b' then reported_value end)              as median_time_excl_transfers_minutes,
        max(case when measure_id = 'OP_18c' then reported_value end)              as median_time_psych_minutes,
        max(case when measure_id = 'OP_18d' then reported_value end)              as ed_boarding_time_minutes,
        max(case when measure_id = 'OP_22' then reported_value end)               as left_without_being_seen_pct,
        max(case when measure_id = 'OP_23' then reported_value end)               as head_ct_timely_pct
    from ed
    group by ccn
)

select * from pivoted
