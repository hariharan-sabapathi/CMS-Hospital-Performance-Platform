"""DuckDB access for the API — one shared read-only connection per process."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from cms_platform.common.settings import DUCKDB_PATH

_connection: duckdb.DuckDBPyConnection | None = None


def _resolve_path() -> Path:
    override = os.environ.get("CMS_API_DUCKDB_PATH")
    return Path(override) if override else DUCKDB_PATH


def get_connection() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        path = _resolve_path()
        if not path.exists():
            raise FileNotFoundError(
                f"DuckDB database not found at {path}. Run 'dbt build --profiles-dir dbt' first."
            )
        _connection = duckdb.connect(str(path), read_only=True)
    return _connection


def reset_connection() -> None:
    """Used by tests to force a reconnect against a fixture database."""
    global _connection
    if _connection is not None:
        _connection.close()
    _connection = None
