"""Request correlation and latency logging.

WHAT THIS WOULD HAVE CHANGED
============================
During the connection-leak outage the only signal anyone had was a tester
saying "it says check your connection". There was no way to join that report to
a server log line, and nothing recorded that requests had gone from ~600ms to
30s — the 30-second wall was only discovered by timing curl by hand.

Both of those are one middleware:

  * every response carries `X-Request-ID`, so a client error report names the
    exact server log line;
  * every request logs its duration, and anything crossing SLOW_REQUEST_MS
    logs at WARNING — so a latency cliff announces itself instead of waiting
    to be noticed by users.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.errors import REQUEST_ID_HEADER

logger = logging.getLogger("elizade.access")

#: Above this, a request is logged at WARNING rather than INFO. 1s is well
#: clear of normal (measured ~600ms for the heaviest read) and well under the
#: client's 20s abort, so the log fires while there is still time to act.
SLOW_REQUEST_MS = 1000

#: Health checks run constantly and would drown the log.
_QUIET_PATHS = frozenset({"/health", "/metrics"})

#: An inbound id is honoured so a trace survives across services — but it is
#: attacker-controlled text that lands in logs, so it is length-capped and
#: charset-checked rather than trusted.
_MAX_INBOUND_ID = 64


def _inbound_id(request: Request) -> str | None:
    raw = request.headers.get(REQUEST_ID_HEADER)
    if not raw or len(raw) > _MAX_INBOUND_ID:
        return None
    # Log-injection guard: no newlines, no control characters, nothing exotic.
    if not all(c.isalnum() or c in "-_" for c in raw):
        return None
    return raw


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, echoes it, and times the request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        rid = _inbound_id(request) or uuid.uuid4().hex
        request.state.request_id = rid

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers build the body; this only records the
            # timing, then re-raises so they still run.
            elapsed = (time.perf_counter() - started) * 1000
            logger.error(
                "rid=%s %s %s -> raised in %.0fms",
                rid, request.method, request.url.path, elapsed,
            )
            raise

        elapsed = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = rid

        if request.url.path not in _QUIET_PATHS:
            # Path template, not the raw URL: query strings carry emails and
            # tokens, and access logs are the last place those should live.
            level = logging.WARNING if elapsed >= SLOW_REQUEST_MS else logging.INFO
            logger.log(
                level,
                "rid=%s %s %s -> %s in %.0fms%s",
                rid,
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
                "  SLOW" if elapsed >= SLOW_REQUEST_MS else "",
            )
        return response
