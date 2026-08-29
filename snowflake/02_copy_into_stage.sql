-- =============================================================================
-- 02_copy_into_stage.sql
-- Loads data/bronze/*.csv (the output of `python -m cms_platform.ingest.loader`)
-- into Snowflake's RAW schema. See 01_create_raw_schema.sql for why this
-- exists: DuckDB (the default dbt target) doesn't need it.
-- =============================================================================

USE WAREHOUSE CMS_PLATFORM_WH;
USE DATABASE CMS_PLATFORM;

-- -----------------------------------------------------------------------------
-- File format shared by every load.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FILE FORMAT CMS_PLATFORM.RAW.CSV_STANDARD
    TYPE = 'CSV'
    FIELD_DELIMITER = ','
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('', 'NULL')
    EMPTY_FIELD_AS_NULL = TRUE;

-- -----------------------------------------------------------------------------
-- Internal named stage (local dev). A production deployment would swap this
-- for an external stage backed by a storage integration pointed at wherever
-- data/bronze/ is published (see architecture/pipeline_overview.txt).
-- -----------------------------------------------------------------------------

CREATE OR REPLACE STAGE CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE
    FILE_FORMAT = CMS_PLATFORM.RAW.CSV_STANDARD;

-- Upload Bronze CSVs into the stage (run from SnowSQL CLI, or use
-- Snowsight's "Load Data" drag-and-drop instead of PUT during local dev):
--   PUT file://data/bronze/cms_hospital_reference.csv  @CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE;
--   PUT file://data/bronze/cms_ed_measures.csv          @CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE;
--   PUT file://data/bronze/cms_hvbp.csv                 @CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE;

-- -----------------------------------------------------------------------------
-- COPY INTO the RAW tables.
-- -----------------------------------------------------------------------------

COPY INTO CMS_PLATFORM.RAW.CMS_HOSPITAL_REFERENCE
FROM @CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE/cms_hospital_reference.csv
FILE_FORMAT = (FORMAT_NAME = CMS_PLATFORM.RAW.CSV_STANDARD)
ON_ERROR = 'ABORT_STATEMENT';

COPY INTO CMS_PLATFORM.RAW.CMS_ED_MEASURES
FROM @CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE/cms_ed_measures.csv
FILE_FORMAT = (FORMAT_NAME = CMS_PLATFORM.RAW.CSV_STANDARD)
ON_ERROR = 'ABORT_STATEMENT';

COPY INTO CMS_PLATFORM.RAW.CMS_HVBP
FROM @CMS_PLATFORM.RAW.BRONZE_LOCAL_STAGE/cms_hvbp.csv
FILE_FORMAT = (FORMAT_NAME = CMS_PLATFORM.RAW.CSV_STANDARD)
ON_ERROR = 'ABORT_STATEMENT';

-- -----------------------------------------------------------------------------
-- Quick load sanity check.
-- -----------------------------------------------------------------------------

SELECT 'CMS_HOSPITAL_REFERENCE' AS table_name, COUNT(*) AS row_count FROM CMS_PLATFORM.RAW.CMS_HOSPITAL_REFERENCE
UNION ALL
SELECT 'CMS_ED_MEASURES', COUNT(*) FROM CMS_PLATFORM.RAW.CMS_ED_MEASURES
UNION ALL
SELECT 'CMS_HVBP', COUNT(*) FROM CMS_PLATFORM.RAW.CMS_HVBP;

-- Next step: point dbt/macros/read_bronze.sql's staging callers at
-- {{ source('raw', table_name) }} for the snowflake target, then:
--   cd dbt && DBT_TARGET=snowflake dbt build --profiles-dir .
