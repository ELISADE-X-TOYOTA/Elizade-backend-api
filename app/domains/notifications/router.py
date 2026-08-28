import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.notifications import preferences, service
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


@router.get("/stream")
async def stream(current_user: CustomerUser, db: Session = Depends(get_db)) -> StreamingResponse:
    """Server-Sent Events: nudges a connected client to refresh.

    SSE rather than a WebSocket because this traffic only ever goes one way.
    The browser and RN clients both reconnect on their own, and there is no
    sticky-session requirement.

    The payload is deliberately thin — just the unread count. A fat event can
    race the database write and show a toast for a notification the list does
    not yet contain; the client refetches instead.
    """
    user_id = current_user.id

    async def events():
        last: int | None = None
        # A bounded loop: a request that never returns ties up a worker, and
        # the client reconnects transparently when the stream ends.
        for _ in range(600):  # ~10 minutes at 1s
            current = service.unread_count(db, user_id)
            if current != last:
                last = current
                yield f"event: unread\ndata: {{\"unread\": {current}}}\n\n"
            else:
                yield ": keep-alive\n\n"  # comment frame keeps proxies from timing out
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
