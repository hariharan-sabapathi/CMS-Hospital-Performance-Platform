"""ETag generation and If-None-Match handling for read endpoints.

Every GET on a mart-backed resource is deterministic for a given DuckDB
build (the warehouse only changes when `dbt build` reruns), so a strong
ETag over the serialized response body is exact: same bytes in, same ETag
out, and a byte-for-byte-unchanged resource can be told apart from a
changed one with no extra query.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel


def compute_etag(payload: Any) -> str:
    encoded = jsonable_encoder(payload)
    body = _canonical_json(encoded)
    digest = hashlib.sha256(body).hexdigest()
    return f'"{digest}"'


def _canonical_json(value: Any) -> bytes:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _none_match_hit(if_none_match: str, etag: str) -> bool:
    if if_none_match.strip() == "*":
        return True
    candidates = [tag.strip() for tag in if_none_match.split(",")]
    return etag in candidates


def conditional_response(request: Request, model: BaseModel, *, status_code: int = 200) -> Response:
    """Return 304 (no body) if the request's If-None-Match matches, else the JSON body with an ETag header."""
    etag = compute_etag(model)
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and _none_match_hit(if_none_match, etag):
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(model),
        headers={"ETag": etag},
    )
