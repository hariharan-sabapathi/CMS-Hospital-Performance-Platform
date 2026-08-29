from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query

from cms_platform.api.cache import hospital_cache, list_cache
from cms_platform.api.db import get_connection
from cms_platform.api.schemas import (
    HospitalListItem,
    HospitalListResponse,
    HospitalProfile,
    MeasureValue,
    PeerComparison,
    PeerHospital,
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


@router.get("", response_model=HospitalListResponse)
def list_hospitals(
    state: str | None = Query(None, min_length=2, max_length=2, description="Two-letter state code."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> HospitalListResponse:
    cache_key = f"{state}:{limit}:{offset}"
    cached = list_cache.get(cache_key)
    if cached is not None:
        return cached

    con = get_connection()
    state_upper = state.upper() if state else None

    total = con.execute(
        "select count(*) from main.mart_ed_performance_vs_hvbp where (? is null or state = ?)",
        [state_upper, state_upper],
    ).fetchone()[0]

    rows = con.execute(
        """
        select ccn, hospital_name, state, total_performance_score, ed_volume_category
        from main.mart_ed_performance_vs_hvbp
        where (? is null or state = ?)
        order by ccn
        limit ? offset ?
        """,
        [state_upper, state_upper, limit, offset],
    ).fetchall()

    columns = ["ccn", "hospital_name", "state", "total_performance_score", "ed_volume_category"]
    response = HospitalListResponse(
        total=total,
        limit=limit,
        offset=offset,
        results=[HospitalListItem(**dict(zip(columns, row, strict=True))) for row in rows],
    )
    list_cache.set(cache_key, response)
    return response


@router.get("/{ccn}", response_model=HospitalProfile)
def get_hospital(ccn: str) -> HospitalProfile:
    cache_key = ccn
    cached = hospital_cache.get(cache_key)
    if cached is not None:
        return cached

    con = get_connection()
    row = _fetch_hospital_row(con, ccn)
    if row is None:
        raise HospitalNotFoundError(ccn)

    measures = _fetch_measures(con, ccn)
    profile = HospitalProfile(measures=measures, **{k: v for k, v in row.items() if k in HospitalProfile.model_fields})
    hospital_cache.set(cache_key, profile)
    return profile


@router.get("/{ccn}/peers", response_model=PeerComparison)
def get_hospital_peers(ccn: str, peer_limit: int = Query(10, ge=1, le=50)) -> PeerComparison:
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

    return PeerComparison(
        ccn=ccn,
        ed_boarding_time_minutes=row["ed_boarding_time_minutes"],
        boarding_time_percentile_in_state=row["boarding_time_percentile_in_state"],
        boarding_time_percentile_in_volume_peer_group=row["boarding_time_percentile_in_volume_peer_group"],
        state_peers=[PeerHospital(**dict(zip(peer_columns, r, strict=True))) for r in state_peer_rows],
        volume_peers=[PeerHospital(**dict(zip(peer_columns, r, strict=True))) for r in volume_peer_rows],
    )
