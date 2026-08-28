"""Per-category, per-channel notification preferences.

Storage holds only DEVIATIONS from the default; the API always returns the full
matrix. That keeps a new category or channel working without backfilling a row
for every user, while a settings screen still gets a complete picture without
having to know the defaults itself.
"""

from sqlalchemy.orm import Session

from app.domains.notifications import catalog
from app.domains.notifications.models import NotificationPreference
from app.domains.notifications.schemas import PreferenceItem
from app.domains.shared.enums import NotificationCategory
from app.domains.users.models import User

#: Channels a customer can actually control. In-app is deliberately absent —
#: it is the permanent record, and a customer who muted everything would
#: otherwise have nowhere to look.
CONTROLLABLE = (catalog.PUSH, catalog.EMAIL, catalog.SMS)

#: Defaults per category. Promotions are opt-IN; SMS is opt-in everywhere
#: because it costs money per message and Nigerian customers often pay to
#: receive. Everything else is opt-out.
DEFAULTS: dict[NotificationCategory, dict[str, bool]] = {
    NotificationCategory.service: {catalog.PUSH: True, catalog.EMAIL: True, catalog.SMS: False},
    NotificationCategory.sales: {catalog.PUSH: True, catalog.EMAIL: True, catalog.SMS: False},
    NotificationCategory.warranty: {catalog.PUSH: True, catalog.EMAIL: True, catalog.SMS: False},
    NotificationCategory.support: {catalog.PUSH: True, catalog.EMAIL: True, catalog.SMS: False},
    NotificationCategory.promo: {catalog.PUSH: False, catalog.EMAIL: False, catalog.SMS: False},
    NotificationCategory.system: {catalog.PUSH: True, catalog.EMAIL: True, catalog.SMS: False},
}


def default_for(category: NotificationCategory, channel: str) -> bool:
    return DEFAULTS.get(category, {}).get(channel, True)


def get_matrix(db: Session, user_id: str) -> list[PreferenceItem]:
    """The complete matrix: stored deviations layered over the defaults."""
    stored = {
        (row.category, row.channel): row.enabled
        for row in db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id)
    }
    items: list[PreferenceItem] = []
    for category in NotificationCategory:
        for channel in CONTROLLABLE:
            enabled = stored.get((category, channel), default_for(category, channel))
            items.append(PreferenceItem(category=category.value, channel=channel, enabled=enabled))
    return items


def set_matrix(db: Session, user: User, items: list[PreferenceItem]) -> list[PreferenceItem]:
    """Upsert the supplied entries. Anything not supplied is left alone."""
    for item in items:
        try:
            category = NotificationCategory(item.category)
        except ValueError:
            continue  # unknown category from an older or newer client
        if item.channel not in CONTROLLABLE:
            continue

        row = (
            db.query(NotificationPreference)
            .filter(
                NotificationPreference.user_id == user.id,
                NotificationPreference.category == category,
                NotificationPreference.channel == item.channel,
            )
            .one_or_none()
        )
        if row is None:
            db.add(
                NotificationPreference(
                    user_id=user.id,
                    category=category,
                    channel=item.channel,
                    enabled=item.enabled,
                )
            )
        else:
            row.enabled = item.enabled

    db.commit()
    return get_matrix(db, user.id)
