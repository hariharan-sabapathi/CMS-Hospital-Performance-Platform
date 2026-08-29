"""
Centralized configuration: project root resolution and storage-mode switch.

Generalizes repo 4's original `pipelines/config.py` (local vs. S3) to the
merged platform. Every module resolves paths through this file rather than
hardcoding them, so the project can be retargeted (new bucket, new local
layout) by changing environment variables only.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

STORAGE_MODE = os.environ.get("CMS_STORAGE_MODE", "local").lower()
S3_BUCKET = os.environ.get("CMS_S3_BUCKET", "cms-hospital-performance-platform")

_LOCAL_ROOTS = {
    "raw": PROJECT_ROOT / "data" / "raw",
    "standardized": PROJECT_ROOT / "data" / "standardized",
    "bronze": PROJECT_ROOT / "data" / "bronze",
}

SOURCE_CONFIG_DIR = PROJECT_ROOT / "src" / "cms_platform" / "config" / "sources"

DUCKDB_PATH = PROJECT_ROOT / "dbt" / "cms_platform.duckdb"

API_KEY = os.environ.get("CMS_API_KEY", "dev-local-key")


def get_dir(layer: str) -> Path | str:
    """Resolve a named storage layer to a local path or s3a:// URI."""
    if layer not in _LOCAL_ROOTS:
        raise ValueError(f"Unknown storage layer: {layer!r}. Expected one of {list(_LOCAL_ROOTS)}.")

    if STORAGE_MODE == "s3":
        return f"s3a://{S3_BUCKET}/{layer}"
    if STORAGE_MODE == "local":
        return _LOCAL_ROOTS[layer]
    raise ValueError(f"Unknown CMS_STORAGE_MODE: {STORAGE_MODE!r}. Expected 'local' or 's3'.")


def is_local() -> bool:
    return STORAGE_MODE == "local"
