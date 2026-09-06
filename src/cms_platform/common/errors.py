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


class InvalidQueryParameterError(CmsPlatformError):
    """A `filter`, `sort`, or `cursor` query parameter is not on the API's whitelist.

    Raised instead of building SQL from the raw parameter value — see
    api/query_params.py for the whitelist that replaces string interpolation.
    """

    def __init__(self, parameter: str, value: str, allowed: list[str] | None = None):
        allowed_note = f" Allowed values: {sorted(allowed)}." if allowed else ""
        super().__init__(f"Invalid value {value!r} for query parameter {parameter!r}.{allowed_note}")
        self.parameter = parameter
        self.value = value
        self.allowed = allowed


class InvalidCursorError(CmsPlatformError):
    """A `cursor` query parameter could not be decoded, or was issued for a different sort/filter."""

    def __init__(self, detail: str):
        super().__init__(detail)
