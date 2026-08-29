with source as (
    select * from {{ read_bronze('cms_ed_measures') }}
),

renamed as (
    select
        lpad(trim(facility_id), 6, '0')            as ccn,
        measure_id,
        measure_name,
        cast(start_date as date)                   as start_date,
        cast(end_date as date)                      as end_date,
        case
            when lower(cast(score_available as varchar)) = 'true'
                then try_cast(score_raw as double)
            else null
        end                                          as reported_value,
        score_raw,
        lower(cast(score_available as varchar)) = 'true'  as score_available,
        try_cast(sample_size as integer)            as sample_size,
        footnote                                     as footnote_code
    from source
),

final as (
    select
        ccn,
        measure_id,
        measure_name,
        start_date,
        end_date,
        reported_value,
        score_raw,
        score_available,
        sample_size,
        footnote_code
    from renamed
)

select * from final
