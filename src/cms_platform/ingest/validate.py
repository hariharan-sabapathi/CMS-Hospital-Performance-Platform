"""
Generic, config-driven validation engine.

Rules are declared in a source YAML's `validation:` list and evaluated
against the DataFrame after schema casting. Never raises by itself — callers
decide whether a failed check halts the pipeline (see loader.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ValidationResult:
    check_name: str
    passed: bool
    failure_count: int
    details: str


def check_unique(df: pd.DataFrame, columns: list[str]) -> ValidationResult:
    dupes = int(df.duplicated(subset=columns).sum())
    return ValidationResult(
        check_name=f"unique[{','.join(columns)}]",
        passed=dupes == 0,
        failure_count=dupes,
        details=f"{dupes} duplicate rows on {columns}",
    )


def check_not_null(df: pd.DataFrame, columns: list[str]) -> ValidationResult:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        return ValidationResult(
            check_name=f"not_null[{','.join(columns)}]",
            passed=False,
            failure_count=-1,
            details=f"Column(s) not found: {missing}",
        )
    nulls = int(df[columns].isnull().any(axis=1).sum())
    return ValidationResult(
        check_name=f"not_null[{','.join(columns)}]",
        passed=nulls == 0,
        failure_count=nulls,
        details=f"{nulls} rows with a null in {columns}",
    )


def check_row_count_min(df: pd.DataFrame, minimum: int) -> ValidationResult:
    count = len(df)
    return ValidationResult(
        check_name=f"row_count_min[{minimum}]",
        passed=count >= minimum,
        failure_count=0 if count >= minimum else minimum - count,
        details=f"{count} rows (minimum required: {minimum})",
    )


def check_range(df: pd.DataFrame, column: str, minimum: float | None, maximum: float | None) -> ValidationResult:
    if column not in df.columns:
        return ValidationResult(f"range[{column}]", False, -1, f"Column not found: {column}")
    series = df[column].dropna()
    mask = pd.Series(False, index=series.index)
    if minimum is not None:
        mask |= series < minimum
    if maximum is not None:
        mask |= series > maximum
    out_of_range = series[mask]
    return ValidationResult(
        check_name=f"range[{column}]",
        passed=len(out_of_range) == 0,
        failure_count=len(out_of_range),
        details=f"{len(out_of_range)} rows outside [{minimum}, {maximum}] in {column}",
    )


def run_validation_rules(df: pd.DataFrame, rules: list[dict]) -> list[ValidationResult]:
    """Evaluate every rule in a source config's `validation:` list."""
    results: list[ValidationResult] = []
    for rule in rules:
        if "unique" in rule:
            results.append(check_unique(df, rule["unique"]))
        elif "not_null" in rule:
            results.append(check_not_null(df, rule["not_null"]))
        elif "row_count_min" in rule:
            results.append(check_row_count_min(df, rule["row_count_min"]))
        else:
            raise ValueError(f"Unrecognized validation rule: {rule}")
    return results


def run_schema_range_checks(df: pd.DataFrame, schema: dict) -> list[ValidationResult]:
    """Evaluate min/max bounds declared per-column in a source config's `schema:`."""
    results: list[ValidationResult] = []
    for column, spec in schema.items():
        if "min" in spec or "max" in spec:
            results.append(check_range(df, column, spec.get("min"), spec.get("max")))
    return results
