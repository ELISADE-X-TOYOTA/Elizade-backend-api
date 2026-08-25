"""The single entry point domain services use to notify a customer.

    notify(db, user=customer, event=catalog.TICKET_STAFF_REPLIED, context={...})

Everything downstream — copy, category, deep link, channel selection,
preferences, delivery logging — is decided here so a caller never has to think
about it.

TRANSACTION SAFETY: call this AFTER the work it describes is committed. A
notification is a side effect of something that already happened; if the send
raises, the booking it announced must not roll back with it. Every failure here
is caught and logged to `notification_deliveries` rather than propagated.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domains.notifications import catalog
from app.domains.notifications.catalog import EventSpec, MissingContext
from app.domains.notifications.models import (
    NotificationDelivery,
    NotificationPreference,
    UserNotification,
)
from app.domains.shared.enums import NotificationCategory
from app.domains.users.models import User
from app.services.email import EmailDeliveryError, email_service
from app.services.push import push_service
from app.services.sms import SmsDeliveryError, sms_service

logger = logging.getLogger("elizade.notify")

STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SUPPRESSED = "suppressed"


@dataclass
class NotifyResult:
    notification_id: str | None
    sent: list[str]
    suppressed: list[str]
    failed: list[str]


def _channel_allowed(
    db: Session,
    user: User,
    channel: str,
    category: NotificationCategory,
    *,
    force: bool,
) -> bool:
    """Per-category preference, falling back to the global toggles.

    `force` bypasses everything: security notices and safety recalls are not
    things a customer opts out of, and treating them as optional is how an
    account takeover or an open recall goes unnoticed.
    """
    if force or channel == catalog.IN_APP:
        # In-app is the record. If it could be disabled, a customer who muted
        # everything would have nowhere to look.
        return True

    row = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user.id,
            NotificationPreference.category == category,
            NotificationPreference.channel == channel,
        )
        .one_or_none()
    )
    if row is not None:
        return row.enabled

    prefs = user.preferences or {}
    if channel == catalog.EMAIL and not prefs.get("email_enabled", True):
        return False
    if channel == catalog.PUSH and not prefs.get("push_enabled", True):
        return False
    if channel == catalog.SMS and not prefs.get("sms_enabled", True):
        return False
    # Promotions are opt-IN; everything else is opt-out.
    if category == NotificationCategory.promo and not prefs.get("marketing_opt_in", False):
        return False
    return True


def _log(
    db: Session,
    *,
    user_id: str,
    notification_id: str | None,
    event_key: str | None,
    channel: str,
    status: str,
    error: str | None = None,
) -> None:
    db.add(
        NotificationDelivery(
            user_id=user_id,
            notification_id=notification_id,
            event_key=event_key,
            channel=channel,
            status=status,
            error=error,
            attempts=1 if status != STATUS_SUPPRESSED else 0,
            sent_at=datetime.now(timezone.utc) if status == STATUS_SENT else None,
        )
    )


def notify(
    db: Session,
    *,
    user: User,
    event: EventSpec,
    context: dict[str, Any] | None = None,
    commit: bool = True,
) -> NotifyResult:
    """Render `event` for `user` and deliver it on the event's channels."""
    ctx = context or {}

    try:
        rendered = catalog.render(event, ctx)
    except MissingContext:
        # A caller bug. Log loudly and give up — half-rendered copy with a
        # literal "{reference}" in it is worse than no notification.
        logger.exception("notification context incomplete for %s", event.key)
        return NotifyResult(notification_id=None, sent=[], suppressed=[], failed=list(event.channels))

    sent: list[str] = []
    suppressed: list[str] = []
    failed: list[str] = []
    notification_id: str | None = None

    # In-app first and synchronously: it is a local insert that cannot fail
    # slowly, and it guarantees the notification exists even if every remote
    # transport is down.
    if catalog.IN_APP in rendered.channels:
        row = UserNotification(
            user_id=user.id,
            title=rendered.title,
            body=rendered.body,
            category=rendered.category,
            deep_link=rendered.deep_link,
            is_read=False,
        )
        db.add(row)
        db.flush()  # need the id for the delivery rows
        notification_id = row.id
        _log(
            db,
            user_id=user.id,
            notification_id=notification_id,
            event_key=rendered.key,
            channel=catalog.IN_APP,
            status=STATUS_SENT,
        )
        sent.append(catalog.IN_APP)

    for channel in rendered.channels:
        if channel == catalog.IN_APP:
            continue

        if not _channel_allowed(db, user, channel, rendered.category, force=rendered.force):
            _log(
                db,
                user_id=user.id,
                notification_id=notification_id,
                event_key=rendered.key,
                channel=channel,
                status=STATUS_SUPPRESSED,
            )
            suppressed.append(channel)
            continue

        try:
            if channel == catalog.EMAIL:
                if not user.email:
                    raise EmailDeliveryError("No email address on this account")
                email_service.send_notification(
                    to_email=user.email,
                    subject=rendered.title,
                    body=rendered.body,
                    category=rendered.category.value,
                )
            elif channel == catalog.PUSH:
                push_service.send(
                    user_id=user.id,
                    title=rendered.title,
                    body=rendered.body,
                    deep_link=rendered.deep_link,
                    db=db,
                )
            elif channel == catalog.SMS:
                if not user.phone_display:
                    raise SmsDeliveryError("No phone number on this account")
                sms_service.send(to=user.phone_display, body=rendered.body)
            else:
                raise ValueError(f"Unknown channel {channel!r}")

            _log(
                db,
                user_id=user.id,
                notification_id=notification_id,
                event_key=rendered.key,
                channel=channel,
                status=STATUS_SENT,
            )
            sent.append(channel)

        except Exception as exc:  # noqa: BLE001 — a transport must never break the caller
            logger.warning("notify %s: %s delivery failed for %s: %s", rendered.key, channel, user.id, exc)
            _log(
                db,
                user_id=user.id,
                notification_id=notification_id,
                event_key=rendered.key,
                channel=channel,
                status=STATUS_FAILED,
                error=str(exc)[:500],
            )
            failed.append(channel)

    if commit:
        db.commit()

    return NotifyResult(
        notification_id=notification_id,
        sent=sent,
        suppressed=suppressed,
        failed=failed,
    )


def safe_notify(
    db: Session,
    *,
    user: User | None,
    event: EventSpec,
    context: dict[str, Any] | None = None,
) -> None:
    """`notify` that never raises and never rolls the caller back.

    Use from domain services. A notification is a side effect: if it fails, the
    booking, reply or claim it describes must still stand.
    """
    if user is None:
        return
    try:
        notify(db, user=user, event=event, context=context)
    except Exception:  # noqa: BLE001
        logger.exception("notification failed for event %s", event.key)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
