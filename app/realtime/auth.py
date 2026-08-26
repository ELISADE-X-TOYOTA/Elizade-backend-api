"""Authenticating a WebSocket handshake.

WHY THE TOKEN COMES IN THE QUERY STRING: the browser WebSocket API cannot set
request headers, so `Authorization: Bearer ...` is simply unavailable to the
admin console. The two portable options are a query parameter or smuggling the
token through `Sec-WebSocket-Protocol`; the query parameter is the one every
client and proxy handles correctly.

The cost is that query strings turn up in access logs and proxy logs. That is
mitigated, not ignored:
  * the ACCESS token is what travels, never the refresh token, so a leaked log
    line expires on its own rather than granting a standing session;
  * the connection is rejected before the socket opens, so an invalid token
    never reaches application code.

React Native CAN send headers on a WebSocket, so the mobile client uses the
Authorization header and the query parameter is accepted only as a fallback.
"""

from __future__ import annotations

import logging

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.domains.users.models import User

logger = logging.getLogger("elizade.realtime")


def _token_from(websocket: WebSocket) -> str | None:
    """Header first, query parameter second."""
    header = websocket.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None

    token = websocket.query_params.get("token")
    return token.strip() if token else None


def authenticate(websocket: WebSocket, db: Session) -> User | None:
    """Resolve the connecting user, or None to refuse the handshake.

    Returns None rather than raising: the caller must close the socket with a
    policy-violation code, and an exception mid-handshake leaves the client
    unable to tell "wrong token" from "server broken" — which decides whether
    it should refresh and retry or stop reconnecting.
    """
    token = _token_from(websocket)
    if not token:
        return None

    user_id = decode_access_token(token)
    if not user_id:
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None

    return user
