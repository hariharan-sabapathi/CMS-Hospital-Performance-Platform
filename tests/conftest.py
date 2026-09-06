from __future__ import annotations

import os

import duckdb
import pytest


@pytest.fixture()
def fixture_db(tmp_path):
    """A small hand-built DuckDB database with the same tables the API queries,
    so API tests don't depend on a full dbt build."""
    db_path = tmp_path / "fixture.duckdb"
    con = duckdb.connect(str(db_path))

    con.execute("create schema if not exists main")
    con.execute(
        """
        create table main.dim_hospital (
            hospital_key varchar, ccn varchar, hospital_name varchar,
            address varchar, city varchar, state varchar, zip_code varchar,
            county varchar, present_in_hvbp boolean, present_in_ed boolean
        )
        """
    )
    con.execute(
        "insert into main.dim_hospital values "
        "('h1','010001','SOUTHEAST HEALTH MEDICAL CENTER','1108 ROSS CLARK CIRCLE','DOTHAN','AL','36301','HOUSTON', true, true),"
        "('h2','010005','MARSHALL MEDICAL CENTERS',null,'BOAZ','AL','35957','MARSHALL', true, true)"
    )

    con.execute(
        """
        create table main.mart_ed_performance_vs_hvbp (
            hospital_key varchar, ccn varchar, hospital_name varchar, address varchar,
            city varchar, state varchar, zip_code varchar, county varchar,
            present_in_ed boolean, present_in_hvbp boolean,
            ed_volume_category varchar, median_arrival_to_departure_minutes double,
            median_time_excl_transfers_minutes double, median_time_psych_minutes double,
            ed_boarding_time_minutes double, left_without_being_seen_pct double,
            head_ct_timely_pct double, fiscal_year integer, total_performance_score double,
            clinical_outcomes_score double, safety_score double, person_community_score double,
            efficiency_score double, synthetic_tier_label varchar,
            estimated_dollar_impact_synthetic double, payment_adjustment_factor double,
            boarding_time_percentile_in_state double, boarding_time_percentile_in_volume_peer_group double
        )
        """
    )
    con.execute(
        """
        insert into main.mart_ed_performance_vs_hvbp values
        ('h1','010001','SOUTHEAST HEALTH MEDICAL CENTER','1108 ROSS CLARK CIRCLE','DOTHAN','AL','36301','HOUSTON',
         true, true, 'very high', 218.0, 217.0, null, 314.0, 1.2, 82.0,
         2026, 32.17, 6.0, 12.9, 10.75, 2.5, 'Average', 0.0, null, 0.6, 0.2),
        ('h2','010005','MARSHALL MEDICAL CENTERS',null,'BOAZ','AL','35957','MARSHALL',
         true, true, 'high', 145.0, 141.0, 280.0, 271.0, 0.5, 64.0,
         2026, 20.92, 1.25, 7.9, 9.25, 2.5, 'High Risk', -100000.0, null, 0.3, 0.4),
        ('h3','020001','ED ONLY HOSPITAL',null,'HOUSTON','TX','77002','HARRIS',
         true, false, 'medium', 190.0, 188.0, null, null, 0.8, 70.0,
         2026, null, null, null, null, null, null, null, null, null, null)
        """
    )

    con.execute(
        "create table main.dim_measure (measure_key varchar, measure_id varchar, measure_name varchar, source varchar, domain varchar, direction varchar, unit varchar)"
    )
    con.execute(
        "insert into main.dim_measure values ('m1','OP_18a','Median time all patients spent in the ED','ed_throughput','Time-Based','lower_is_better','minutes')"
    )

    con.execute(
        "create table main.fact_ed_measure (hospital_key varchar, measure_key varchar, period_key varchar, reported_value double, score_raw varchar, sample_size integer, footnote_code varchar)"
    )
    con.execute("insert into main.fact_ed_measure values ('h1','m1','p1', 218.0, '218', 406, null)")

    con.execute(
        "create table main.fact_hvbp_domain_score (hospital_key varchar, measure_key varchar, fiscal_period_key varchar, fiscal_year integer, domain varchar, domain_score double)"
    )
    con.execute("insert into main.fact_hvbp_domain_score values ('h1','m1','p1', 2026, 'hvbp_clinical_outcomes', 6.0)")

    con.close()

    prev_path = os.environ.get("CMS_API_DUCKDB_PATH")
    os.environ["CMS_API_DUCKDB_PATH"] = str(db_path)

    from cms_platform.api import db as db_module

    db_module.reset_connection()

    yield db_path

    db_module.reset_connection()
    if prev_path is None:
        os.environ.pop("CMS_API_DUCKDB_PATH", None)
    else:
        os.environ["CMS_API_DUCKDB_PATH"] = prev_path


@pytest.fixture()
def api_client(fixture_db, monkeypatch):
    monkeypatch.setenv("CMS_API_KEY", "test-key")

    import cms_platform.common.settings as settings_module

    monkeypatch.setattr(settings_module, "API_KEY", "test-key")

    import cms_platform.api.security as security_module

    monkeypatch.setattr(security_module, "API_KEY", "test-key")

    from cms_platform.api.cache import hospital_cache, list_cache

    hospital_cache.clear()
    list_cache.clear()

    from fastapi.testclient import TestClient

    from cms_platform.api.main import app

    with TestClient(app) as client:
        yield client
