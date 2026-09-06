"""Whitelisted filtering, sorting, and keyset (cursor) pagination for list endpoints.

Every column name that reaches a SQL string in this module comes from one of
the dicts below — never from the raw query string. A request supplies a
*key* ("state", "-total_performance_score"); the key is looked up in a
whitelist and the *whitelist's own value* is what gets spliced into the
query. An unrecognized key is rejected before any SQL is built. Values (as
opposed to column names) are always passed as bound parameters, never
interpolated. See the README's "API Contract" section for the full
rationale — this is the one place that decision is implemented.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from cms_platform.common.errors import InvalidCursorError, InvalidQueryParameterError

# Query param name -> real column name on mart_ed_performance_vs_hvbp.
# Add a column here to make it filterable; nothing else needs to change.
ALLOWED_FILTERS: dict[str, str] = {
    "state": "state",
    "ed_volume_category": "ed_volume_category",
    "synthetic_tier_label": "synthetic_tier_label",
}

# Sort key -> real column name. Every sortable column must also have a
# total order guaranteed by the `ccn` tiebreaker added in build_keyset_clause.
ALLOWED_SORT_FIELDS: dict[str, str] = {
    "ccn": "ccn",
    "hospital_name": "hospital_name",
    "state": "state",
    "total_performance_score": "total_performance_score",
    "ed_boarding_time_minutes": "ed_boarding_time_minutes",
}

DEFAULT_SORT_FIELD = "ccn"
_CURSOR_VERSION = 1


@dataclass(frozen=True)
class SortSpec:
    field: str  # public sort key, e.g. "total_performance_score"
    column: str  # actual SQL column, e.g. "total_performance_score"
    descending: bool


@dataclass(frozen=True)
class Cursor:
    sort_field: str
    descending: bool
    last_value: object
    last_ccn: str


def parse_sort(sort: str | None) -> SortSpec:
    """Parse a `sort` query param like `total_performance_score` or `-total_performance_score`.

    Raises InvalidQueryParameterError if the field isn't on ALLOWED_SORT_FIELDS.
    """
    raw = sort or DEFAULT_SORT_FIELD
    descending = raw.startswith("-")
    field = raw[1:] if descending else raw
    column = ALLOWED_SORT_FIELDS.get(field)
    if column is None:
        raise InvalidQueryParameterError("sort", raw, allowed=list(ALLOWED_SORT_FIELDS))
    return SortSpec(field=field, column=column, descending=descending)


def parse_filters(raw_filters: dict[str, str | None]) -> dict[str, str]:
    """Validate a mapping of {query param name: value} against ALLOWED_FILTERS.

    Only non-None values are kept. Raises InvalidQueryParameterError for any
    key not on the whitelist (defensive — FastAPI's own Query(...) signature
    is what actually limits which keys can arrive here).
    """
    resolved: dict[str, str] = {}
    for key, value in raw_filters.items():
        if value is None:
            continue
        column = ALLOWED_FILTERS.get(key)
        if column is None:
            raise InvalidQueryParameterError("filter", key, allowed=list(ALLOWED_FILTERS))
        resolved[column] = value
    return resolved


def encode_cursor(sort: SortSpec, last_value: object, last_ccn: str) -> str:
    payload = {
        "v": _CURSOR_VERSION,
        "f": sort.field,
        "d": sort.descending,
        "lv": last_value,
        "lc": last_ccn,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, sort: SortSpec) -> Cursor:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:
        raise InvalidCursorError("Cursor is not a valid opaque cursor issued by this API.") from exc

    if payload.get("v") != _CURSOR_VERSION:
        raise InvalidCursorError("Cursor was issued by an incompatible API version.")
    if payload.get("f") != sort.field or payload.get("d") != sort.descending:
        raise InvalidCursorError(
            "Cursor was issued for a different `sort` value. Cursors are only valid for the sort they were issued with."
        )
    return Cursor(
        sort_field=payload["f"],
        descending=payload["d"],
        last_value=payload["lv"],
        last_ccn=payload["lc"],
    )


def build_keyset_clause(sort: SortSpec, cursor: Cursor | None) -> tuple[str, list]:
    """Build the WHERE fragment + bound params for keyset (seek) pagination.

    `sort.column` is whitelist-resolved SQL text, never a bound parameter
    (DuckDB can't bind identifiers) and never raw user input. `ccn` is
    always the tiebreaker column so pagination is stable even when the sort
    column has duplicate values.
    """
    if cursor is None:
        return "1 = 1", []

    op = "<" if cursor.descending else ">"
    clause = f"({sort.column}, ccn) {op} (?, ?)"
    return clause, [cursor.last_value, cursor.last_ccn]


def order_by_clause(sort: SortSpec) -> str:
    direction = "desc" if sort.descending else "asc"
    return f"{sort.column} {direction}, ccn {direction}"
