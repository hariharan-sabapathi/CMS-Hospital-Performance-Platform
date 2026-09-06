from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query, Request, Response

from cms_platform.api.cache import hospital_cache, list_cache
from cms_platform.api.db import get_connection
from cms_platform.api.etag import conditional_response
from cms_platform.api.query_params import (
    build_keyset_clause,
    decode_cursor,
    encode_cursor,
    order_by_clause,
    parse_filters,
    parse_sort,
)
from cms_platform.api.schemas import (
    HospitalListItem,
    HospitalListResponse,
    HospitalProfile,
    MeasureValue,
    PaginationMeta,
    PeerComparison,
    PeerHospital,
    ProblemDetail,
)
from cms_platform.api.security import require_api_key
from cms_platform.common.errors import HospitalNotFoundError

router = APIRouter(prefix="/hospitals", tags=["hospitals"], dependencies=[Depends(require_api_key)])

_PROFILE_COLUMNS = """
    ccn, hospital_name, city, state, zip_code, present_in_ed, present_in_hvbp,
    total_performance_score, synthetic_tier_label, estimated_dollar_impact_synthetic,
    payment_adjustment_factor, ed_boarding_time_minutes, ed_volume_category,
    boarding_time_percentile_in_state, boarding_time_percentile_in_volume_peer_group
"""

# Superset of every column a list-sort can order by (see query_params.ALLOWED_SORT_FIELDS)
# plus the columns shown in a list row. Kept as one list so every sortable
# column is guaranteed to be present when a cursor is built off the last row.
_LIST_COLUMNS = ["ccn", "hospital_name", "state", "total_performance_score", "ed_volume_category", "ed_boarding_time_minutes"]

_NOT_MODIFIED = {304: {"description": "Not Modified — the resource matches the ETag in If-None-Match."}}
_BAD_QUERY = {400: {"model": ProblemDetail, "description": "An unrecognized `filter` or `sort` field, or an invalid cursor."}}
_NOT_FOUND = {404: {"model": ProblemDetail, "description": "No hospital exists for this CCN."}}


def _fetch_hospital_row(con: duckdb.DuckDBPyConnection, ccn: str) -> dict | None:
    row = con.execute(
        f"select {_PROFILE_COLUMNS} from main.mart_ed_performance_vs_hvbp where ccn = ?",
        [ccn],
    ).fetchone()
    if row is None:
        return None
    columns = [c.strip() for c in _PROFILE_COLUMNS.strip().split(",")]
    return dict(zip(columns, row, strict=True))


def _fetch_measures(con: duckdb.DuckDBPyConnection, ccn: str) -> list[MeasureValue]:
    ed_rows = con.execute(
        """
        select dm.measure_id, dm.measure_name, dm.domain, dm.direction, dm.unit,
               fm.reported_value, fm.score_raw
        from main.fact_ed_measure fm
        join main.dim_measure dm on fm.measure_key = dm.measure_key
        join main.dim_hospital dh on fm.hospital_key = dh.hospital_key
        where dh.ccn = ?
        """,
        [ccn],
    ).fetchall()

    hvbp_rows = con.execute(
        """
        select dm.measure_id, dm.measure_name, dm.domain, dm.direction, dm.unit,
               fd.domain_score as reported_value, cast(fd.domain_score as varchar) as score_raw
        from main.fact_hvbp_domain_score fd
        join main.dim_measure dm on fd.measure_key = dm.measure_key
        join main.dim_hospital dh on fd.hospital_key = dh.hospital_key
        where dh.ccn = ?
        """,
        [ccn],
    ).fetchall()

    columns = ["measure_id", "measure_name", "domain", "direction", "unit", "reported_value", "score_raw"]
    return [MeasureValue(**dict(zip(columns, row, strict=True))) for row in [*ed_rows, *hvbp_rows]]


@router.get(
    "",
    response_model=HospitalListResponse,
    responses={**_NOT_MODIFIED, **_BAD_QUERY},
    summary="List hospitals with cursor pagination, whitelisted filters, and whitelisted sort.",
)
def list_hospitals(
    request: Request,
    state: str | None = Query(None, min_length=2, max_length=2, description="Two-letter state code filter."),
    ed_volume_category: str | None = Query(None, description="Filter by ED volume category (e.g. 'very high')."),
    synthetic_tier_label: str | None = Query(None, description="Filter by synthetic risk tier (e.g. 'Average')."),
    sort: str = Query(
        "ccn",
        description="Sort field, optionally prefixed with '-' for descending. "
        "Whitelisted: ccn, hospital_name, state, total_performance_score, ed_boarding_time_minutes.",
    ),
    cursor: str | None = Query(None, description="Opaque cursor from a previous response's `pagination.next_cursor`."),
    limit: int = Query(50, ge=1, le=500),
) -> Response:
    sort_spec = parse_sort(sort)
    state_upper = state.upper() if state else None
    filters = parse_filters(
        {"state": state_upper, "ed_volume_category": ed_volume_category, "synthetic_tier_label": synthetic_tier_label}
    )
    decoded_cursor = decode_cursor(cursor, sort_spec) if cursor else None

    cache_key = f"{sort}:{cursor}:{limit}:{sorted(filters.items())}"
    cached = list_cache.get(cache_key)
    if cached is None:
        con = get_connection()

        where_clauses: list[str] = []
        params: list = []
        for column, value in filters.items():
            where_clauses.append(f"{column} = ?")
            params.append(value)

        keyset_clause, keyset_params = build_keyset_clause(sort_spec, decoded_cursor)
        where_clauses.append(keyset_clause)
        params.extend(keyset_params)

        where_sql = " and ".join(where_clauses)
        columns_sql = ", ".join(_LIST_COLUMNS)

        rows = con.execute(
            f"""
            select {columns_sql}
            from main.mart_ed_performance_vs_hvbp
            where {where_sql}
            order by {order_by_clause(sort_spec)}
            limit ?
            """,
            [*params, limit + 1],
        ).fetchall()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        row_dicts = [dict(zip(_LIST_COLUMNS, row, strict=True)) for row in page_rows]

        next_cursor = None
        if has_more and row_dicts:
            last = row_dicts[-1]
            next_cursor = encode_cursor(sort_spec, last[sort_spec.column], last["ccn"])

        list_columns = ["ccn", "hospital_name", "state", "total_performance_score", "ed_volume_category"]
        cached = HospitalListResponse(
            data=[HospitalListItem(**{k: row[k] for k in list_columns}) for row in row_dicts],
            pagination=PaginationMeta(limit=limit, next_cursor=next_cursor, has_more=has_more),
        )
        list_cache.set(cache_key, cached)

    return conditional_response(request, cached)


@router.get(
    "/{ccn}",
    response_model=HospitalProfile,
    responses={**_NOT_MODIFIED, **_NOT_FOUND},
)
def get_hospital(ccn: str, request: Request) -> Response:
    cache_key = ccn
    cached = hospital_cache.get(cache_key)
    if cached is None:
        con = get_connection()
        row = _fetch_hospital_row(con, ccn)
        if row is None:
            raise HospitalNotFoundError(ccn)

        measures = _fetch_measures(con, ccn)
        cached = HospitalProfile(measures=measures, **{k: v for k, v in row.items() if k in HospitalProfile.model_fields})
        hospital_cache.set(cache_key, cached)

    return conditional_response(request, cached)


@router.get(
    "/{ccn}/peers",
    response_model=PeerComparison,
    responses={**_NOT_MODIFIED, **_NOT_FOUND},
)
def get_hospital_peers(ccn: str, request: Request, peer_limit: int = Query(10, ge=1, le=50)) -> Response:
    con = get_connection()
    row = _fetch_hospital_row(con, ccn)
    if row is None:
        raise HospitalNotFoundError(ccn)

    peer_columns = ["ccn", "hospital_name", "state", "ed_volume_category", "ed_boarding_time_minutes", "total_performance_score"]

    state_peer_rows = con.execute(
        """
        select ccn, hospital_name, state, ed_volume_category, ed_boarding_time_minutes, total_performance_score
        from main.mart_ed_performance_vs_hvbp
        where state = ? and ccn != ?
        order by ed_boarding_time_minutes nulls last
        limit ?
        """,
        [row["state"], ccn, peer_limit],
    ).fetchall()

    volume_peer_rows = con.execute(
        """
        select ccn, hospital_name, state, ed_volume_category, ed_boarding_time_minutes, total_performance_score
        from main.mart_ed_performance_vs_hvbp
        where ed_volume_category = ? and ccn != ?
        order by ed_boarding_time_minutes nulls last
        limit ?
        """,
        [row["ed_volume_category"], ccn, peer_limit],
    ).fetchall()

    comparison = PeerComparison(
        ccn=ccn,
        ed_boarding_time_minutes=row["ed_boarding_time_minutes"],
        boarding_time_percentile_in_state=row["boarding_time_percentile_in_state"],
        boarding_time_percentile_in_volume_peer_group=row["boarding_time_percentile_in_volume_peer_group"],
        state_peers=[PeerHospital(**dict(zip(peer_columns, r, strict=True))) for r in state_peer_rows],
        volume_peers=[PeerHospital(**dict(zip(peer_columns, r, strict=True))) for r in volume_peer_rows],
    )
    return conditional_response(request, comparison)
