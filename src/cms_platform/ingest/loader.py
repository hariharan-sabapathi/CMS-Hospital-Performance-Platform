"""
Config-driven loader — the one ingestion engine for both CMS sources.

Reads a source YAML (src/cms_platform/config/sources/*.yml), applies dtype
hints *at CSV-read time* (not after — see the CCN bug note below), runs the
validation engine, normalizes CCN columns, and lands the result to Bronze
(data/bronze/*.csv).

The CCN bug this replaces: the original repo-3 loader called
`pd.read_csv(path)` with no dtype hints. Facility ID is written unquoted in
the raw CMS CSV (e.g. `010001`), so pandas' type inference reads it as an
integer and silently drops the leading zero — every downstream join on CCN
was then wrong. `dtype_hint: str` in a source config is passed straight into
`read_csv(dtype=...)`, so the column is never given the chance to be
inferred as numeric in the first place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from cms_platform.common.errors import SourceConfigError, ValidationFailedError
from cms_platform.common.logging import get_logger
from cms_platform.common.settings import PROJECT_ROOT, SOURCE_CONFIG_DIR
from cms_platform.ingest.validate import (
    ValidationResult,
    run_schema_range_checks,
    run_validation_rules,
)

LOGGER = get_logger("cms_platform.ingest.loader")

_TYPE_MAP = {"string": str, "int": "Int64", "float": "float64"}


def load_source_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SourceConfigError(f"Source config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if "source" not in config:
        raise SourceConfigError(f"Source config {path} is missing required key 'source'")
    return config


def _dtype_overrides(schema: dict[str, Any], column_map: dict[str, str] | None) -> dict[str, type]:
    """Build the `dtype=` mapping passed straight into pandas.read_csv.

    This is what actually fixes the CCN bug: forcing string dtype at parse
    time means pandas never gets to infer facility_id as an integer.
    """
    reverse_map = {v: k for k, v in (column_map or {}).items()}
    overrides: dict[str, type] = {}
    for canonical_name, spec in schema.items():
        if spec.get("dtype_hint") == "str":
            raw_name = reverse_map.get(canonical_name, canonical_name)
            overrides[raw_name] = str
    return overrides


def normalize_ccn(series: pd.Series) -> pd.Series:
    """Zero-pad a CCN column to the canonical 6-character CMS Certification Number."""
    return series.astype(str).str.strip().str.zfill(6)


def _cast_schema(df: pd.DataFrame, schema: dict[str, Any]) -> pd.DataFrame:
    df = df.copy()
    for column, spec in schema.items():
        if column not in df.columns:
            continue
        py_type = _TYPE_MAP.get(spec["type"])
        if py_type is None:
            continue
        if spec["type"] == "string":
            df[column] = df[column].astype(str).str.strip()
        else:
            df[column] = pd.to_numeric(df[column], errors="coerce")
            if spec["type"] == "int":
                df[column] = df[column].astype("Int64")
    return df


def _log_results(results: list[ValidationResult], table_name: str) -> list[str]:
    failures = []
    for r in results:
        if r.passed:
            LOGGER.info("[PASS] %s.%s — %s", table_name, r.check_name, r.details)
        else:
            LOGGER.warning("[FAIL] %s.%s — %s", table_name, r.check_name, r.details)
            failures.append(f"{table_name}.{r.check_name}: {r.details}")
    return failures


def load_table(table_config: dict[str, Any], table_name: str, halt_on_failure: bool) -> pd.DataFrame:
    schema = table_config["schema"]
    column_map = table_config.get("column_map")
    file_path = PROJECT_ROOT / table_config["file"]

    if not file_path.exists():
        raise SourceConfigError(f"Input file for '{table_name}' not found: {file_path}")

    dtype_overrides = _dtype_overrides(schema, column_map)
    LOGGER.info("Reading %s (dtype overrides: %s)", file_path, dtype_overrides)
    df = pd.read_csv(file_path, dtype=dtype_overrides)

    if column_map:
        present = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=present)

    df = _cast_schema(df, schema)

    ccn_column = table_config.get("_is_ccn")
    if ccn_column and ccn_column in df.columns:
        df[ccn_column] = normalize_ccn(df[ccn_column])

    results = run_validation_rules(df, table_config.get("validation", []))
    results += run_schema_range_checks(df, schema)
    failures = _log_results(results, table_name)

    if failures and halt_on_failure:
        raise ValidationFailedError(f"Validation failed for '{table_name}'", failures)

    output_path = PROJECT_ROOT / table_config["output"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    LOGGER.info("Landed %d rows to %s", len(df), output_path)
    return df


def load_source(config_path: Path, halt_on_failure: bool = True) -> dict[str, pd.DataFrame]:
    """Load every table declared in a source config and land each to Bronze."""
    config = load_source_config(config_path)
    is_ccn = config.get("is_ccn")

    if "tables" in config:
        tables = config["tables"]
    else:
        tables = {config["source"]: {k: v for k, v in config.items() if k != "tables"}}

    results: dict[str, pd.DataFrame] = {}
    for name, table_config in tables.items():
        table_config = dict(table_config)
        table_config["_is_ccn"] = is_ccn
        results[name] = load_table(table_config, f"{config['source']}.{name}", halt_on_failure)
    return results


def load_all_sources(halt_on_failure: bool = True) -> dict[str, dict[str, pd.DataFrame]]:
    """Discover and load every *.yml under config/sources/."""
    all_results: dict[str, dict[str, pd.DataFrame]] = {}
    for config_path in sorted(SOURCE_CONFIG_DIR.glob("*.yml")):
        config = load_source_config(config_path)
        LOGGER.info("=== Loading source: %s ===", config["source"])
        all_results[config["source"]] = load_source(config_path, halt_on_failure)
    return all_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the config-driven CMS ingestion loader.")
    parser.add_argument("--source", type=str, default=None, help="Load a single source by name (e.g. cms_hvbp).")
    parser.add_argument(
        "--no-halt-on-failure",
        action="store_true",
        help="Log validation failures but continue landing to Bronze.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    halt = not args.no_halt_on_failure
    try:
        if args.source:
            load_source(SOURCE_CONFIG_DIR / f"{args.source}.yml", halt_on_failure=halt)
        else:
            load_all_sources(halt_on_failure=halt)
    except ValidationFailedError as exc:
        LOGGER.error("Ingestion halted: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
