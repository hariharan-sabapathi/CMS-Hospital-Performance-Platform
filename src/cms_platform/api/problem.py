"""RFC 7807 (application/problem+json) error responses.

Every error the API returns — validation, auth, not-found, unhandled — goes
through `problem_response` so the shape is identical everywhere:

    {
      "type": "https://cms-platform.dev/problems/<slug>",
      "title": "<short, fixed summary>",
      "status": <http status>,
      "detail": "<this-occurrence explanation>",
      "instance": "<request path>",
      "request_id": "<uuid4, from the request-context middleware>"
    }

`type` and `title` are unlisted from the RFC 7807 spec as constants per
problem kind; `detail`, `instance`, and `request_id` vary per request.
`request_id` is a documented extension member (RFC 7807 section 3.2 allows
these) so a client can hand it back for support/log correlation.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

PROBLEM_BASE = "https://cms-platform.dev/problems"
PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_response(
    request: Request,
    *,
    status: int,
    type_slug: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    content: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}/{type_slug}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": request_id,
    }
    if extra:
        content.update(extra)
    return JSONResponse(status_code=status, content=content, media_type=PROBLEM_MEDIA_TYPE, headers=headers)
