"""Pydantic request/response models for the read API.

`model_config["json_schema_extra"]["examples"]` on each model is what
populates the example values shown in /docs (OpenAPI) — every response
model below carries one drawn from real (or fixture) hospital data.
"""

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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "measure_id": "OP_18a",
                    "measure_name": "Median time all patients spent in the ED",
                    "domain": "Time-Based",
                    "direction": "lower_is_better",
                    "unit": "minutes",
                    "reported_value": 218.0,
                    "score_raw": "218",
                }
            ]
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ccn": "010001",
                    "hospital_name": "SOUTHEAST HEALTH MEDICAL CENTER",
                    "city": "DOTHAN",
                    "state": "AL",
                    "zip_code": "36301",
                    "present_in_ed": True,
                    "present_in_hvbp": True,
                    "total_performance_score": 32.17,
                    "synthetic_tier_label": "Average",
                    "estimated_dollar_impact_synthetic": 0.0,
                    "payment_adjustment_factor": None,
                    "measures": [
                        {
                            "measure_id": "OP_18a",
                            "reported_value": 218.0,
                            "unit": "minutes",
                            "direction": "lower_is_better",
                        }
                    ],
                }
            ]
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ccn": "010001",
                    "ed_boarding_time_minutes": 314.0,
                    "boarding_time_percentile_in_state": 0.6,
                    "boarding_time_percentile_in_volume_peer_group": 0.2,
                    "state_peers": [
                        {
                            "ccn": "010005",
                            "hospital_name": "MARSHALL MEDICAL CENTERS",
                            "state": "AL",
                            "ed_volume_category": "high",
                            "ed_boarding_time_minutes": 271.0,
                            "total_performance_score": 20.92,
                        }
                    ],
                    "volume_peers": [],
                }
            ]
        }
    }


class HospitalListItem(BaseModel):
    ccn: str
    hospital_name: str | None = None
    state: str | None = None
    total_performance_score: float | None = None
    ed_volume_category: str | None = None


class PaginationMeta(BaseModel):
    limit: int = Field(..., description="Page size that was applied.")
    next_cursor: str | None = Field(
        None,
        description="Opaque cursor for the next page. Null when there are no more results. "
        "Pass it back as `?cursor=...` with the *same* `sort` and filters used to obtain it.",
    )
    has_more: bool = Field(..., description="Whether another page exists after this one.")

    model_config = {
        "json_schema_extra": {
            "examples": [{"limit": 50, "next_cursor": "eyJ2IjoxLCJmIjoiY2NuIiwiZCI6ZmFsc2UsImx2IjoiMDEwMDA1IiwibGMiOiIwMTAwMDUifQ", "has_more": True}]
        }
    }


class HospitalListResponse(BaseModel):
    data: list[HospitalListItem]
    pagination: PaginationMeta

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "ccn": "010001",
                            "hospital_name": "SOUTHEAST HEALTH MEDICAL CENTER",
                            "state": "AL",
                            "total_performance_score": 32.17,
                            "ed_volume_category": "very high",
                        }
                    ],
                    "pagination": {"limit": 50, "next_cursor": None, "has_more": False},
                }
            ]
        }
    }


class HealthzResponse(BaseModel):
    status: str = Field(..., description="Liveness status. 'ok' as long as the process can handle requests.")

    model_config = {"json_schema_extra": {"examples": [{"status": "ok"}]}}


class ReadyzResponse(BaseModel):
    status: str = Field(..., description="Readiness status. 'ok' only if the DuckDB warehouse is queryable.")
    duckdb_path: str
    row_count: int

    model_config = {
        "json_schema_extra": {
            "examples": [{"status": "ok", "duckdb_path": "/app/dbt/cms_platform.duckdb", "row_count": 2455}]
        }
    }


class ProblemDetail(BaseModel):
    """RFC 7807 `application/problem+json` error body. Identical shape for every error the API returns."""

    type: str = Field(..., description="A URI identifying the problem type. Not required to be dereferenceable.")
    title: str = Field(..., description="A short, fixed summary of the problem type.")
    status: int = Field(..., description="The HTTP status code for this occurrence.")
    detail: str = Field(..., description="A human-readable explanation specific to this occurrence.")
    instance: str = Field(..., description="The request path that produced this problem.")
    request_id: str = Field(..., description="Correlates this error with the server's structured logs.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "https://cms-platform.dev/problems/hospital-not-found",
                    "title": "Hospital Not Found",
                    "status": 404,
                    "detail": "No hospital found for CCN '999999'.",
                    "instance": "/hospitals/999999",
                    "request_id": "b3f1c2e4-9a3b-4b8b-9c1a-1e2f3a4b5c6d",
                }
            ]
        }
    }
