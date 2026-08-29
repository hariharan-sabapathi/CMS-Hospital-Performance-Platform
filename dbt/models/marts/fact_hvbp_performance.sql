{#-
    estimated_dollar_impact_synthetic is a modeling assumption, not a CMS
    figure: TPS quartile tiers (dbt/seeds/adjustment_tier_reference.csv,
    calibrated to the actual FY2026 score distribution) times an assumed
    $10M Medicare base revenue (var: assumed_base_medicare_revenue). The
    real payment adjustment factor is published in IPPS Final Rule Table
    16B but is not loaded in this build — payment_adjustment_factor is kept
    nullable for it. See README data limitations.
-#}

with hvbp as (
    select * from {{ ref('stg_hvbp__scores') }}
),

hospital as (
    select hospital_key, ccn from {{ ref('dim_hospital') }}
),

tiers as (
    select * from {{ ref('adjustment_tier_reference') }}
),

scored as (
    select
        h.hospital_key,
        v.fiscal_year,
        v.total_performance_score,
        (
            select t.tier_label
            from tiers t
            where v.total_performance_score >= t.min_score
            order by t.min_score desc
            limit 1
        ) as synthetic_tier_label,
        (
            select t.adjustment_rate
            from tiers t
            where v.total_performance_score >= t.min_score
            order by t.min_score desc
            limit 1
        ) as synthetic_adjustment_rate
    from hvbp v
    join hospital h on v.ccn = h.ccn
)

select
    hospital_key,
    fiscal_year,
    total_performance_score,
    synthetic_tier_label,
    synthetic_adjustment_rate,
    synthetic_adjustment_rate * {{ var('assumed_base_medicare_revenue') }} as estimated_dollar_impact_synthetic,
    cast(null as double) as payment_adjustment_factor
from scored
