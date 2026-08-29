with hvbp as (
    select * from {{ ref('stg_hvbp__scores') }}
),

hospital as (
    select hospital_key, ccn from {{ ref('dim_hospital') }}
),

measure as (
    select measure_key, measure_id from {{ ref('dim_measure') }}
),

period as (
    select fiscal_period_key, fiscal_year, domain from {{ ref('dim_fiscal_period') }}
),

unpivoted as (
    select ccn, fiscal_year, 'HVBP_CLINICAL' as measure_id, 'hvbp_clinical_outcomes' as period_domain, clinical_outcomes_score as domain_score from hvbp
    union all
    select ccn, fiscal_year, 'HVBP_SAFETY', 'hvbp_safety', safety_score from hvbp
    union all
    select ccn, fiscal_year, 'HVBP_PERSON_COMMUNITY', 'hvbp_person_community', person_community_score from hvbp
    union all
    select ccn, fiscal_year, 'HVBP_EFFICIENCY', 'hvbp_efficiency', efficiency_score from hvbp
)

select
    h.hospital_key,
    m.measure_key,
    p.fiscal_period_key,
    u.fiscal_year,
    u.period_domain as domain,
    u.domain_score
from unpivoted u
join hospital h on u.ccn = h.ccn
join measure m on u.measure_id = m.measure_id
join period p on p.fiscal_year = u.fiscal_year and p.domain = u.period_domain
