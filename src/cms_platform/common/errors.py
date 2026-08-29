"""Shared exception types raised by ingestion and served as structured errors by the API."""

from __future__ import annotations


class CmsPlatformError(Exception):
    """Base class for all platform errors."""


class SourceConfigError(CmsPlatformError):
    """A source YAML config is missing, malformed, or references a missing file."""


class ValidationFailedError(CmsPlatformError):
    """One or more required data-validation checks failed."""

    def __init__(self, message: str, failures: list[str]):
        super().__init__(message)
        self.failures = failures


class HospitalNotFoundError(CmsPlatformError):
    """No hospital exists for the given CCN."""

    def __init__(self, ccn: str):
        super().__init__(f"No hospital found for CCN {ccn!r}")
        self.ccn = ccn
