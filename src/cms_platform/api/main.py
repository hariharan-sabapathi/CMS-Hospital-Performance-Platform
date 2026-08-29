"""FastAPI read API for the CMS Hospital Performance Platform. No /predict — there's no model."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from cms_platform.api.db import get_connection
from cms_platform.api.routers.hospitals import router as hospitals_router
from cms_platform.api.schemas import HealthResponse
from cms_platform.common.errors import CmsPlatformError, HospitalNotFoundError
from cms_platform.common.logging import get_logger
from cms_platform.common.settings import DUCKDB_PATH

LOGGER = get_logger("cms_platform.api")

app = FastAPI(
    title="CMS Hospital Performance Platform API",
    description="Read-only API over the ED throughput + HVBP star schema. No prediction endpoint — no model.",
    version="1.0.0",
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
async def hospital_not_found_handler(request: Request, exc: HospitalNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "hospital_not_found",
            "detail": str(exc),
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


@app.exception_handler(CmsPlatformError)
async def platform_error_handler(request: Request, exc: CmsPlatformError) -> JSONResponse:
    LOGGER.error("Unhandled platform error: %s", exc, extra={"request_id": getattr(request.state, "request_id", "unknown")})
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": str(exc),
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "request_error", "detail": exc.detail, "request_id": request_id},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    LOGGER.error("Unhandled exception: %s", exc, extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "An unexpected error occurred.", "request_id": request_id},
    )


app.include_router(hospitals_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        con = get_connection()
        row_count = con.execute("select count(*) from main.mart_ed_performance_vs_hvbp").fetchone()[0]
        status = "ok"
    except Exception:
        row_count = 0
        status = "degraded"
    return HealthResponse(status=status, duckdb_path=str(DUCKDB_PATH), row_count=row_count)
