from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.notifications import service
from app.domains.notifications.schemas import MarkAllReadOut, MarkReadOut, UserNotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[UserNotificationOut])
def list_notifications(
    current_user: CurrentUser,
    unread_only: bool = Query(default=False, alias="unreadOnly"),
    db: Session = Depends(get_db),
) -> list[UserNotificationOut]:
    return service.list_user_notifications(db, current_user.id, unread_only=unread_only)


@router.post("/read-all", response_model=MarkAllReadOut)
def mark_all_read(current_user: CurrentUser, db: Session = Depends(get_db)) -> MarkAllReadOut:
    updated = service.mark_all_notifications_read(db, current_user.id)
    return MarkAllReadOut(updated=updated)


@router.post("/{notification_id}/read", response_model=MarkReadOut)
def mark_read(
    notification_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> MarkReadOut:
    return service.mark_notification_read(db, current_user.id, notification_id)
