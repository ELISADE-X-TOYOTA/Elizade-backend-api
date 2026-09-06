import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import CustomerUser
from app.core.security import decode_access_token
from app.domains.notifications import preferences, service
from app.domains.users.models import User, UserRole
from app.domains.notifications.models import DeviceToken
from app.domains.notifications.schemas import (
    DeviceTokenIn,
    DeviceTokenOut,
    MarkAllReadOut,
    MarkReadOut,
    PreferencesOut,
    PreferencesUpdateIn,
    UnreadCountOut,
    UserNotificationOut,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[UserNotificationOut])
def list_notifications(
    current_user: CustomerUser,
    unread_only: bool = Query(default=False, alias="unreadOnly"),
    db: Session = Depends(get_db),
) -> list[UserNotificationOut]:
    return service.list_user_notifications(db, current_user.id, unread_only=unread_only)


@router.post("/read-all", response_model=MarkAllReadOut)
def mark_all_read(current_user: CustomerUser, db: Session = Depends(get_db)) -> MarkAllReadOut:
    updated = service.mark_all_notifications_read(db, current_user.id)
    return MarkAllReadOut(updated=updated)


@router.post("/{notification_id}/read", response_model=MarkReadOut)
def mark_read(
    notification_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> MarkReadOut:
    return service.mark_notification_read(db, current_user.id, notification_id)


# ── Device tokens (push) ─────────────────────────────────────────────────
@router.post("/devices", response_model=DeviceTokenOut, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceTokenIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> DeviceTokenOut:
    """Register (or re-register) this installation for push.

    Idempotent on the token. The same token can move between accounts — a
    shared device, or someone signing out and back in as somebody else — so a
    re-registration reassigns ownership rather than erroring, otherwise the
    previous owner keeps receiving the new user's notifications.
    """
    existing = db.query(DeviceToken).filter(DeviceToken.token == payload.token).one_or_none()
    if existing is not None:
        existing.user_id = current_user.id
        existing.platform = payload.platform
        existing.last_seen_at = datetime.now(timezone.utc)
    else:
        db.add(
            DeviceToken(
                user_id=current_user.id,
                token=payload.token,
                platform=payload.platform,
            )
        )
    db.commit()
    return DeviceTokenOut(registered=True)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    token: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> Response:
    """Called on sign-out so a shared handset stops receiving the last user's alerts."""
    db.query(DeviceToken).filter(
        DeviceToken.token == token, DeviceToken.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Preferences ──────────────────────────────────────────────────────────
@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(current_user: CustomerUser, db: Session = Depends(get_db)) -> PreferencesOut:
    return PreferencesOut(items=preferences.get_matrix(db, current_user.id))


# PATCH, not PUT: unsupplied entries are left alone, so this is a partial
# update by definition.
@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(
    payload: PreferencesUpdateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> PreferencesOut:
    return PreferencesOut(items=preferences.set_matrix(db, current_user, payload.items))


# ── Real-time ────────────────────────────────────────────────────────────
@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(current_user: CustomerUser, db: Session = Depends(get_db)) -> UnreadCountOut:
    return UnreadCountOut(unread=service.unread_count(db, current_user.id))


#: Seconds between unread-count polls on an open stream.
#
#: Was 1. At one query per second per connected phone this was the heaviest
#: single source of load on the database, for a number that changes a few times
#: a day. Five seconds is still immediate to a customer and cuts the query rate
#: by 80%.
STREAM_POLL_SECONDS = 5
#: ~10 minutes, after which the client reconnects transparently.
STREAM_POLLS = 120


def authenticate_stream_user(db: Session, authorization: str | None) -> User:
    """`require_customer` by hand, against a session the caller owns.

    The dependency version cannot be used here: FastAPI would hold its session
    open for the life of the stream, which is the leak this endpoint exists to
    avoid. The rules and the status codes are deliberately identical to
    `get_current_user` + `require_customer` so a client cannot tell the two
    paths apart.
    """
    scheme, _, credentials = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = decode_access_token(credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    if user.role != UserRole.customer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer access only")

    return user


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events: nudges a connected client to refresh.

    SSE rather than a WebSocket because this traffic only ever goes one way.
    The browser and RN clients both reconnect on their own, and there is no
    sticky-session requirement.

    The payload is deliberately thin — just the unread count. A fat event can
    race the database write and show a toast for a notification the list does
    not yet contain; the client refetches instead.

    WHY THIS ENDPOINT TAKES NO `Depends(get_db)` AND NO AUTH DEPENDENCY
    ===================================================================
    THIS OUTAGE. FastAPI holds a request's dependencies open until the RESPONSE
    is finished, and a streaming response is not finished until the stream ends.
    So `Depends(get_db)` on a ten-minute stream pinned a database connection for
    ten minutes — and the auth dependency, which takes `get_db` of its own,
    pinned a second one.

    Two connections per connected phone, against a pool of
    `pool_size=5 + max_overflow=10`. Seven testers with the app open consumed
    every connection a worker had; every other request then waited out
    SQLAlchemy's 30-second `pool_timeout` and returned 500. That is precisely
    what testers saw as "the request timed out" on the login screen, on every
    network, at the same moment.

    So the session is opened per poll and closed immediately, and the customer
    is authenticated by hand against a session that is likewise released at
    once. Between polls this endpoint holds NO connection at all.
    """
    # Authenticate against a session that is closed before streaming starts.
    db = SessionLocal()
    try:
        user = authenticate_stream_user(db, request.headers.get("authorization"))
        user_id = user.id
        # Nothing is written, but a read still opened a transaction.
        db.rollback()
    finally:
        db.close()

    async def events():
        last: int | None = None
        # A bounded loop: a request that never returns ties up a worker, and
        # the client reconnects transparently when the stream ends.
        for _ in range(STREAM_POLLS):
            # Disconnected clients are common on mobile. Noticing here frees the
            # worker immediately instead of polling into a closed socket.
            if await request.is_disconnected():
                return

            poll_db = SessionLocal()
            try:
                current = service.unread_count(poll_db, user_id)
                # A read still opens a transaction; without this the connection
                # sits `idle in transaction` and holds its slot on the server.
                poll_db.rollback()
            finally:
                poll_db.close()

            if current != last:
                last = current
                yield f"event: unread\ndata: {{\"unread\": {current}}}\n\n"
            else:
                yield ": keep-alive\n\n"  # comment frame keeps proxies from timing out
            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
