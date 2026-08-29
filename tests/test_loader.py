"""Unit tests for the config-driven loader and validation engine.

Includes the CCN regression test named in the Phase 0 build spec: "010001"
must survive the full ingest path unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from cms_platform.common.errors import SourceConfigError, ValidationFailedError
from cms_platform.ingest.loader import (
    _dtype_overrides,
    load_source,
    load_source_config,
    normalize_ccn,
)
from cms_platform.ingest.validate import (
    check_not_null,
    check_range,
    check_row_count_min,
    check_unique,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --- CCN bug regression -----------------------------------------------------


def test_ccn_leading_zero_survives_naive_pandas_read_when_dtype_forced(tmp_path):
    """Demonstrates the bug and its fix in one test: an unquoted CCN in a raw
    CSV is read as an int (losing the leading zero) unless dtype is forced."""
    csv_path = tmp_path / "raw.csv"
    csv_path.write_text("Facility ID,Total Performance Score\n010001,32.5\n")

    naive = pd.read_csv(csv_path)
    assert naive["Facility ID"].iloc[0] != "010001"  # the bug, reproduced

    fixed = pd.read_csv(csv_path, dtype={"Facility ID": str})
    assert fixed["Facility ID"].iloc[0] == "010001"  # the fix


def test_normalize_ccn_zero_pads_to_six_characters():
    series = pd.Series(["10001", "010001", "1", " 340113 "])
    result = normalize_ccn(series)
    assert list(result) == ["010001", "010001", "000001", "340113"]


def test_dtype_overrides_maps_canonical_name_back_to_raw_header():
    schema = {"facility_id": {"type": "string", "dtype_hint": "str"}}
    column_map = {"Facility ID": "facility_id"}
    overrides = _dtype_overrides(schema, column_map)
    assert overrides == {"Facility ID": str}


def test_full_ingest_path_preserves_ccn(tmp_path):
    """End-to-end: raw CSV with a bare 010001 -> loaded table has ccn == '010001'."""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "hvbp_total_performance.csv").write_text(
        "Fiscal Year,Facility ID,Facility Name,State,Total Performance Score\n"
        "2026,010001,SOUTHEAST HEALTH MEDICAL CENTER,AL,32.5\n"
        "2026,010005,MARSHALL MEDICAL CENTERS,AL,20.9\n"
    )
    bronze_dir = tmp_path / "data" / "bronze"

    config = {
        "source": "cms_hvbp_test",
        "file": "data/raw/hvbp_total_performance.csv",
        "output": "data/bronze/cms_hvbp.csv",
        "key": ["facility_id", "fiscal_year"],
        "is_ccn": "facility_id",
        "column_map": {
            "Fiscal Year": "fiscal_year",
            "Facility ID": "facility_id",
            "Facility Name": "facility_name",
            "State": "state",
            "Total Performance Score": "total_performance_score",
        },
        "schema": {
            "facility_id": {"type": "string", "required": True, "dtype_hint": "str"},
            "fiscal_year": {"type": "int", "required": True},
            "facility_name": {"type": "string", "required": True},
            "state": {"type": "string", "required": True},
            "total_performance_score": {"type": "float", "required": True, "min": 0, "max": 100},
        },
        "validation": [
            {"unique": ["facility_id", "fiscal_year"]},
            {"not_null": ["facility_id"]},
            {"row_count_min": 1},
        ],
    }
    config_path = tmp_path / "cms_hvbp_test.yml"
    config_path.write_text(yaml.safe_dump(config))

    import cms_platform.ingest.loader as loader_module

    original_root = loader_module.PROJECT_ROOT
    loader_module.PROJECT_ROOT = tmp_path
    try:
        results = load_source(config_path)
    finally:
        loader_module.PROJECT_ROOT = original_root

    df = results["cms_hvbp_test"]
    assert df["facility_id"].iloc[0] == "010001"

    landed = pd.read_csv(bronze_dir / "cms_hvbp.csv", dtype={"facility_id": str})
    assert landed["facility_id"].iloc[0] == "010001"
    assert (landed["facility_id"].str.len() == 6).all()


# --- Validation engine -------------------------------------------------------


def test_check_unique_detects_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    result = check_unique(df, ["a", "b"])
    assert result.passed is False
    assert result.failure_count == 1


def test_check_not_null_passes_on_clean_data():
    df = pd.DataFrame({"a": [1, 2, 3]})
    result = check_not_null(df, ["a"])
    assert result.passed is True


def test_check_not_null_reports_missing_column():
    df = pd.DataFrame({"a": [1, 2, 3]})
    result = check_not_null(df, ["missing_col"])
    assert result.passed is False
    assert result.failure_count == -1


def test_check_row_count_min():
    df = pd.DataFrame({"a": range(5)})
    assert check_row_count_min(df, 5).passed is True
    assert check_row_count_min(df, 6).passed is False


def test_check_range_flags_out_of_bounds():
    df = pd.DataFrame({"score": [10, 50, 150, -5]})
    result = check_range(df, "score", 0, 100)
    assert result.passed is False
    assert result.failure_count == 2


def test_source_config_error_on_missing_file(tmp_path):
    with pytest.raises(SourceConfigError):
        load_source_config(tmp_path / "does_not_exist.yml")


def test_validation_failure_halts_by_default(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "bad.csv").write_text("facility_id,total_performance_score\n1,200\n")

    config = {
        "source": "bad_source",
        "file": "data/raw/bad.csv",
        "output": "data/bronze/bad.csv",
        "key": ["facility_id"],
        "schema": {
            "facility_id": {"type": "string", "required": True},
            "total_performance_score": {"type": "float", "required": True, "min": 0, "max": 100},
        },
        "validation": [{"row_count_min": 10}],
    }
    config_path = tmp_path / "bad_source.yml"
    config_path.write_text(yaml.safe_dump(config))

    import cms_platform.ingest.loader as loader_module

    original_root = loader_module.PROJECT_ROOT
    loader_module.PROJECT_ROOT = tmp_path
    try:
        with pytest.raises(ValidationFailedError):
            load_source(config_path, halt_on_failure=True)
    finally:
        loader_module.PROJECT_ROOT = original_root
