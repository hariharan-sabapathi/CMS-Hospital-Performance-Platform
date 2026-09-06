"""FastAPI read API for the CMS Hospital Performance Platform. No /predict — there's no model."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from cms_platform.api.db import get_connection
from cms_platform.api.problem import problem_response
from cms_platform.api.routers.hospitals import router as hospitals_router
from cms_platform.api.schemas import HealthzResponse, ProblemDetail, ReadyzResponse
from cms_platform.common.errors import (
    CmsPlatformError,
    HospitalNotFoundError,
    InvalidCursorError,
    InvalidQueryParameterError,
)
from cms_platform.common.logging import get_logger
from cms_platform.common.settings import DUCKDB_PATH

LOGGER = get_logger("cms_platform.api")

app = FastAPI(
    title="CMS Hospital Performance Platform API",
    description=(
        "Read-only API over the ED throughput + HVBP star schema. No prediction endpoint — no model.\n\n"
        "Errors follow RFC 7807 (`application/problem+json`) uniformly. List endpoints use cursor "
        "(keyset) pagination, and every filter/sort field is checked against a server-side whitelist "
        "before it ever reaches a SQL string — see the README's API Contract section."
    ),
    version="2.0.0",
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()

    response = await call_next(request)

    duration_ms = round((time.monotonic() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    LOGGER.info(
        "%s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.exception_handler(HospitalNotFoundError)
async def hospital_not_found_handler(request: Request, exc: HospitalNotFoundError):
    return problem_response(
        request,
        status=404,
        type_slug="hospital-not-found",
        title="Hospital Not Found",
        detail=str(exc),
    )


@app.exception_handler(InvalidQueryParameterError)
async def invalid_query_parameter_handler(request: Request, exc: InvalidQueryParameterError):
    return problem_response(
        request,
        status=400,
        type_slug="invalid-query-parameter",
        title="Invalid Query Parameter",
        detail=str(exc),
        extra={"parameter": exc.parameter, "allowed": exc.allowed} if exc.allowed else {"parameter": exc.parameter},
    )


@app.exception_handler(InvalidCursorError)
async def invalid_cursor_handler(request: Request, exc: InvalidCursorError):
    return problem_response(
        request,
        status=400,
        type_slug="invalid-cursor",
        title="Invalid Cursor",
        detail=str(exc),
    )


@app.exception_handler(CmsPlatformError)
async def platform_error_handler(request: Request, exc: CmsPlatformError):
    LOGGER.error("Unhandled platform error: %s", exc, extra={"request_id": getattr(request.state, "request_id", "unknown")})
    return problem_response(
        request,
        status=500,
        type_slug="internal-error",
        title="Internal Server Error",
        detail=str(exc),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in err["loc"] if p != "query"), "message": err["msg"]} for err in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        type_slug="validation-error",
        title="Validation Error",
        detail="The request parameters failed validation.",
        extra={"errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    slug = {401: "unauthorized", 403: "forbidden", 404: "not-found"}.get(exc.status_code, "request-error")
    title = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found"}.get(exc.status_code, "Request Error")
    return problem_response(
        request,
        status=exc.status_code,
        type_slug=slug,
        title=title,
        detail=str(exc.detail),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    LOGGER.error("Unhandled exception: %s", exc, extra={"request_id": getattr(request.state, "request_id", "unknown")})
    return problem_response(
        request,
        status=500,
        type_slug="internal-error",
        title="Internal Server Error",
        detail="An unexpected error occurred.",
    )


app.include_router(hospitals_router)


@app.get(
    "/healthz",
    response_model=HealthzResponse,
    tags=["ops"],
    summary="Liveness probe — always 200 if the process is up. Never touches the database.",
)
def healthz() -> HealthzResponse:
    return HealthzResponse(status="ok")


@app.get(
    "/readyz",
    response_model=ReadyzResponse,
    responses={503: {"model": ProblemDetail, "description": "The DuckDB warehouse is missing or unqueryable."}},
    tags=["ops"],
    summary="Readiness probe — 200 only if the DuckDB warehouse can be queried.",
)
def readyz(request: Request):
    try:
        con = get_connection()
        row_count = con.execute("select count(*) from main.mart_ed_performance_vs_hvbp").fetchone()[0]
    except Exception as exc:
        return problem_response(
            request,
            status=503,
            type_slug="not-ready",
            title="Service Not Ready",
            detail=f"DuckDB warehouse is not queryable: {exc}",
        )
    return ReadyzResponse(status="ok", duckdb_path=str(DUCKDB_PATH), row_count=row_count)
