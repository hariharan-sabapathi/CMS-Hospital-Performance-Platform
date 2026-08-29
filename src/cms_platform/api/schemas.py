"""Pydantic request/response models for the read API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MeasureValue(BaseModel):
    measure_id: str
    measure_name: str | None = None
    domain: str | None = None
    direction: str | None = None
    unit: str | None = None
    reported_value: float | None = None
    score_raw: str | None = None


class HospitalProfile(BaseModel):
    ccn: str = Field(..., description="6-character CMS Certification Number.")
    hospital_name: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    present_in_ed: bool
    present_in_hvbp: bool
    total_performance_score: float | None = None
    synthetic_tier_label: str | None = None
    estimated_dollar_impact_synthetic: float | None = Field(
        None,
        description="Modeling assumption, not a CMS-published figure. See README data limitations.",
    )
    payment_adjustment_factor: float | None = Field(
        None,
        description="Real CMS payment adjustment factor (IPPS Table 16B). Null in this build.",
    )
    measures: list[MeasureValue] = Field(default_factory=list)


class PeerHospital(BaseModel):
    ccn: str
    hospital_name: str | None = None
    state: str | None = None
    ed_volume_category: str | None = None
    ed_boarding_time_minutes: float | None = None
    total_performance_score: float | None = None


class PeerComparison(BaseModel):
    ccn: str
    ed_boarding_time_minutes: float | None = None
    boarding_time_percentile_in_state: float | None = None
    boarding_time_percentile_in_volume_peer_group: float | None = None
    state_peers: list[PeerHospital]
    volume_peers: list[PeerHospital]


class HospitalListItem(BaseModel):
    ccn: str
    hospital_name: str | None = None
    state: str | None = None
    total_performance_score: float | None = None
    ed_volume_category: str | None = None


class HospitalListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[HospitalListItem]


class HealthResponse(BaseModel):
    status: str
    duckdb_path: str
    row_count: int


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str
