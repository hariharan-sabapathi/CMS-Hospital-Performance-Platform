-- =============================================================================
-- 01_create_raw_schema.sql
--
-- Documented alternate warehouse target for dbt (see README "Architecture").
-- DuckDB is the default target and needs none of this — its staging models
-- read data/bronze/*.csv directly. To use Snowflake instead: run this script
-- and 02_copy_into_stage.sql to land the same Bronze CSVs into RAW tables,
-- then point dbt/macros/read_bronze.sql's staging callers at
-- {{ source('raw', table_name) }} instead of read_csv() for the Snowflake
-- target. Everything downstream of staging (intermediate, marts, tests) is
-- unchanged either way.
-- =============================================================================

CREATE WAREHOUSE IF NOT EXISTS CMS_PLATFORM_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Compute for the CMS Hospital Performance Platform';

CREATE DATABASE IF NOT EXISTS CMS_PLATFORM
    COMMENT = 'HVBP financial impact + ED throughput, merged';

CREATE SCHEMA IF NOT EXISTS CMS_PLATFORM.RAW
    COMMENT = 'Landing schema mirroring data/bronze/*.csv, the output of ingest/loader.py';

USE WAREHOUSE CMS_PLATFORM_WH;
USE DATABASE CMS_PLATFORM;

-- -----------------------------------------------------------------------------
-- RAW schema: mirrors data/bronze/*.csv exactly. No dimensional modeling,
-- surrogate keys, or business logic belong on these tables -- that's dbt's
-- job (see dbt/models/staging and dbt/models/marts).
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TABLE RAW.CMS_HOSPITAL_REFERENCE (
    facility_id         VARCHAR(6)      NOT NULL,
    facility_name       VARCHAR(200)    NOT NULL,
    address             VARCHAR(200),
    city                VARCHAR(100),
    state               VARCHAR(2),
    zip_code            VARCHAR(10),
    county              VARCHAR(100),
    telephone_number    VARCHAR(20)
);

CREATE OR REPLACE TABLE RAW.CMS_ED_MEASURES (
    facility_id         VARCHAR(6)      NOT NULL,
    measure_id          VARCHAR(50)     NOT NULL,
    measure_name        VARCHAR(500),
    start_date          DATE,
    end_date            DATE,
    score_numeric       FLOAT,
    score_raw           VARCHAR(50),
    score_available     BOOLEAN,
    sample_size         VARCHAR(50),
    footnote            VARCHAR(10)
);

CREATE OR REPLACE TABLE RAW.CMS_HVBP (
    facility_id                    VARCHAR(6)      NOT NULL,
    fiscal_year                    INTEGER         NOT NULL,
    facility_name                  VARCHAR(200)    NOT NULL,
    state                          VARCHAR(2)      NOT NULL,
    city                           VARCHAR(100),
    zip_code                       VARCHAR(10),
    county                         VARCHAR(100),
    clinical_outcomes_score        FLOAT,
    safety_score                   FLOAT,
    person_community_score         FLOAT,
    efficiency_score                FLOAT,
    total_performance_score        FLOAT       NOT NULL
);
