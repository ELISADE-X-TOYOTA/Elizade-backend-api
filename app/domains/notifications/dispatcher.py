from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domains.notifications.models import UserNotification
from app.domains.shared.enums import NotificationCategory
from app.domains.users.models import User
from app.services.email import email_service
from app.services.push import push_service

CHANNEL_IN_APP = "in_app"
CHANNEL_EMAIL = "email"
CHANNEL_PUSH = "push"
VALID_CHANNELS = {CHANNEL_IN_APP, CHANNEL_EMAIL, CHANNEL_PUSH}


@dataclass
class DispatchResult:
    in_app_created: bool
    email_sent: bool
    push_sent: bool


def _user_wants_channel(user: User, channel: str, category: NotificationCategory) -> bool:
    prefs = user.preferences or {}
    if channel == CHANNEL_EMAIL and not prefs.get("email_enabled", True):
        return False
    if channel == CHANNEL_PUSH and not prefs.get("push_enabled", True):
        return False
    if category == NotificationCategory.promo and not prefs.get("marketing_opt_in", False):
        return False
    return True


def dispatch_to_user(
    db: Session,
    *,
    user: User,
    title: str,
    body: str,
    category: NotificationCategory,
    channels: list[str],
    deep_link: str | None = None,
    campaign_id: str | None = None,
) -> DispatchResult:
    normalized = {c.strip().lower() for c in channels if c.strip()}
    invalid = normalized - VALID_CHANNELS
    if invalid:
        raise ValueError(f"Invalid channels: {', '.join(sorted(invalid))}")

    if not normalized:
        normalized = {CHANNEL_IN_APP}

    in_app_created = False
    email_sent = False
    push_sent = False

    if CHANNEL_IN_APP in normalized:
        notification = UserNotification(
            user_id=user.id,
            title=title,
            body=body,
            category=category,
            deep_link=deep_link,
            campaign_id=campaign_id,
            is_read=False,
        )
        db.add(notification)
        in_app_created = True

    if CHANNEL_EMAIL in normalized and user.email and _user_wants_channel(user, CHANNEL_EMAIL, category):
        email_service.send_notification(
            to_email=user.email,
            subject=title,
            body=body,
            category=category.value,
        )
        email_sent = True

    if CHANNEL_PUSH in normalized and _user_wants_channel(user, CHANNEL_PUSH, category):
        push_service.send(user_id=user.id, title=title, body=body, deep_link=deep_link)
        push_sent = True

    return DispatchResult(
        in_app_created=in_app_created,
        email_sent=email_sent,
        push_sent=push_sent,
    )
