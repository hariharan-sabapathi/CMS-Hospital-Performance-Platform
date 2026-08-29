with source as (
    select * from {{ read_bronze('cms_hvbp') }}
),

renamed as (
    select
        lpad(trim(facility_id), 6, '0')        as ccn,
        cast(fiscal_year as integer)           as fiscal_year,
        trim(facility_name)                    as hospital_name,
        trim(state)                            as state,
        trim(city)                             as city,
        trim(county)                           as county,
        trim(zip_code)                         as zip_code,
        cast(clinical_outcomes_score as double)  as clinical_outcomes_score,
        cast(safety_score as double)             as safety_score,
        cast(person_community_score as double)   as person_community_score,
        cast(efficiency_score as double)         as efficiency_score,
        cast(total_performance_score as double)  as total_performance_score
    from source
)

select * from renamed
