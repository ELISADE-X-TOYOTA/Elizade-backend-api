"""One error shape for the whole API.

WHY THIS EXISTS
===============
Before this, a client had to understand three different error bodies:

    HTTPException      ->  {"detail": "Ticket not found"}
    validation (422)   ->  {"detail": [{"loc": [...], "msg": "...", ...}]}
    anything unhandled ->  no JSON at all, just a 500 from Starlette

So `detail` was sometimes a string, sometimes a list of objects, and sometimes
absent. Every client grew its own defensive unwrapping — see the mobile app's
`typeof data?.detail === 'string' ? ... : Array.isArray(...) ? ...` — and any
client that guessed wrong showed the user nothing useful.

THE `detail` KEY IS DELIBERATELY STILL HERE
===========================================
There are release APKs in testers' hands that read `detail` and cannot be
force-updated. Dropping it would silently downgrade every one of them to a
generic status message. So the envelope is ADDITIVE: new fields for new
clients, `detail` preserved for shipped ones. It can be removed once the
installed base has moved on, and not before.

CAPACITY FAILURES ARE 503, NOT 500
==================================
A pool timeout is not a bug in the request that happened to hit it — it is the
service being out of capacity, and it is retryable. Returning 500 for it (which
is what happened during the connection-leak outage) tells the client "this
request is broken, don't bother retrying" and tells whoever is on call to go
looking for a code fault. 503 + Retry-After says the true thing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLATimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("elizade.errors")

#: Header carrying the correlation id, on every response including errors.
REQUEST_ID_HEADER = "X-Request-ID"

#: Seconds to advertise on a capacity failure. Short: the condition is usually
#: a brief pool contention spike, not a planned outage.
RETRY_AFTER_SECONDS = 5


# ── Machine-readable codes ───────────────────────────────────────────────
#
# `message` is for a human and may be reworded at any time. `code` is the
# contract: clients branch on it, so these strings are frozen once shipped.
class ErrorCode:
    BAD_REQUEST = "bad_request"
    VALIDATION_FAILED = "validation_failed"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    RATE_LIMITED = "rate_limited"
    INTERNAL = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"


_STATUS_CODES = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}

#: Sent instead of the real exception text on an unhandled error. The real
#: detail goes to the log, addressed by request id.
_OPAQUE_500 = "Something went wrong on our end. Please try again."
_OPAQUE_503 = "The service is briefly over capacity. Please try again in a moment."


def _code_for(status_code: int) -> str:
    if status_code in _STATUS_CODES:
        return _STATUS_CODES[status_code]
    return ErrorCode.INTERNAL if status_code >= 500 else ErrorCode.BAD_REQUEST


def request_id(request: Request) -> str:
    """The current request's correlation id, or a fresh one if unset.

    Never raises: an error handler that itself fails is the worst possible
    failure mode, so this degrades to a new id rather than an AttributeError.
    """
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def build_error(
    *,
    status_code: int,
    message: str,
    code: str | None = None,
    details: Any = None,
    rid: str | None = None,
) -> dict[str, Any]:
    """The canonical body. See the module docstring for why `detail` remains."""
    return {
        "code": code or _code_for(status_code),
        "message": message,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "requestId": rid,
        # ── legacy, for shipped clients — do not remove without a migration ──
        "detail": message,
    }


def _json(status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None):
    merged = {REQUEST_ID_HEADER: body.get("requestId") or ""}
    if headers:
        merged.update(headers)
    return JSONResponse(status_code=status_code, content=body, headers=merged)


# ── Handlers ─────────────────────────────────────────────────────────────


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = request_id(request)
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    body = build_error(status_code=exc.status_code, message=detail, rid=rid)
    # A 401 must keep its challenge header or clients cannot tell an expired
    # token from a missing one.
    headers = dict(getattr(exc, "headers", None) or {})
    return _json(exc.status_code, body, headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 with the field errors kept — but flattened and trimmed.

    The raw Pydantic list carries an `input` echo of what was submitted, which
    on an auth route is the password or OTP the caller just sent. Echoing that
    back into a response body (and from there into client logs and crash
    reports) is how credentials end up somewhere they were never meant to be.
    So only location and reason survive.
    """
    rid = request_id(request)
    details = [
        {
            "field": ".".join(str(p) for p in err.get("loc", ()) if p != "body") or "body",
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "invalid"),
        }
        for err in exc.errors()
    ]
    first = details[0]["message"] if details else "Some details are invalid."
    body = build_error(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=first,
        details=details,
        rid=rid,
    )
    return _json(status.HTTP_422_UNPROCESSABLE_ENTITY, body)


async def capacity_exception_handler(request: Request, exc: Exception):
    """Pool exhaustion and lost connections — retryable, so 503 not 500."""
    rid = request_id(request)
    logger.warning(
        "capacity failure rid=%s %s %s: %s",
        rid, request.method, request.url.path, exc.__class__.__name__,
    )
    body = build_error(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        message=_OPAQUE_503,
        rid=rid,
    )
    return _json(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        body,
        {"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last resort. The client gets an opaque message and an id; the log gets
    the traceback. Those two are joined by the request id — which is the whole
    point of it, and the thing that was missing when testers could only report
    "it says check your connection"."""
    rid = request_id(request)
    logger.exception(
        "unhandled error rid=%s %s %s", rid, request.method, request.url.path
    )
    body = build_error(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=_OPAQUE_500,
        rid=rid,
    )
    return _json(status.HTTP_500_INTERNAL_SERVER_ERROR, body)


def install_error_handlers(app: FastAPI) -> None:
    """Register everything. Order does not matter; FastAPI dispatches on type,
    most specific first, so the bare `Exception` entry is the fallback."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLATimeoutError, capacity_exception_handler)
    app.add_exception_handler(OperationalError, capacity_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
