with ed_hospitals as (
    select ccn, hospital_name, address, city, state, zip_code, county
    from {{ ref('stg_hospital__attributes') }}
),

hvbp_hospitals as (
    select distinct ccn, hospital_name, city, state, zip_code, county
    from {{ ref('stg_hvbp__scores') }}
),

all_ccns as (
    select ccn from ed_hospitals
    union
    select ccn from hvbp_hospitals
),

combined as (
    select
        a.ccn,
        coalesce(e.hospital_name, h.hospital_name)  as hospital_name,
        e.address,
        coalesce(e.city, h.city)                    as city,
        coalesce(e.state, h.state)                  as state,
        coalesce(e.zip_code, h.zip_code)             as zip_code,
        coalesce(e.county, h.county)                as county,
        e.ccn is not null                            as present_in_ed,
        h.ccn is not null                             as present_in_hvbp
    from all_ccns a
    left join ed_hospitals e on a.ccn = e.ccn
    left join hvbp_hospitals h on a.ccn = h.ccn
)

select
    {{ dbt_utils.generate_surrogate_key(['ccn']) }} as hospital_key,
    ccn,
    hospital_name,
    address,
    city,
    state,
    zip_code,
    county,
    present_in_hvbp,
    present_in_ed
from combined
