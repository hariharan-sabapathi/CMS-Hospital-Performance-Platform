{#-
    One row per hospital: ED throughput measures + HVBP performance,
    side by side. This is the analysis table behind the ED/TPS finding in
    the README — correlational, cross-sectional, one fiscal year. See
    README "Key finding" and "Data limitations".
-#}

with hospital as (
    select * from {{ ref('dim_hospital') }}
),

ed_summary as (
    select * from {{ ref('int_hospital_ed_summary') }}
),

hvbp_perf as (
    select * from {{ ref('fact_hvbp_performance') }}
),

domain_scores as (
    select
        hospital_key,
        max(case when domain = 'hvbp_clinical_outcomes' then domain_score end)   as clinical_outcomes_score,
        max(case when domain = 'hvbp_safety' then domain_score end)              as safety_score,
        max(case when domain = 'hvbp_person_community' then domain_score end)    as person_community_score,
        max(case when domain = 'hvbp_efficiency' then domain_score end)          as efficiency_score
    from {{ ref('fact_hvbp_domain_score') }}
    group by hospital_key
),

joined as (
    select
        h.hospital_key,
        h.ccn,
        h.hospital_name,
        h.address,
        h.city,
        h.state,
        h.zip_code,
        h.county,
        h.present_in_ed,
        h.present_in_hvbp,
        e.ed_volume_category,
        e.median_arrival_to_departure_minutes,
        e.median_time_excl_transfers_minutes,
        e.median_time_psych_minutes,
        e.ed_boarding_time_minutes,
        e.left_without_being_seen_pct,
        e.head_ct_timely_pct,
        p.fiscal_year,
        p.total_performance_score,
        d.clinical_outcomes_score,
        d.safety_score,
        d.person_community_score,
        d.efficiency_score,
        p.synthetic_tier_label,
        p.estimated_dollar_impact_synthetic,
        p.payment_adjustment_factor
    from hospital h
    left join ed_summary e on h.ccn = e.ccn
    left join hvbp_perf p on h.hospital_key = p.hospital_key
    left join domain_scores d on h.hospital_key = d.hospital_key
)

select
    *,
    percent_rank() over (
        partition by state order by ed_boarding_time_minutes
    ) as boarding_time_percentile_in_state,
    percent_rank() over (
        partition by ed_volume_category order by ed_boarding_time_minutes
    ) as boarding_time_percentile_in_volume_peer_group
from joined
