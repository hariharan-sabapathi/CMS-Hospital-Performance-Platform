with source as (
    select * from {{ read_bronze('cms_hospital_reference') }}
),

renamed as (
    select
        lpad(trim(facility_id), 6, '0')  as ccn,
        trim(facility_name)              as hospital_name,
        trim(address)                    as address,
        trim(city)                       as city,
        trim(state)                      as state,
        trim(zip_code)                   as zip_code,
        trim(county)                     as county,
        trim(telephone_number)           as telephone_number
    from source
)

select * from renamed
