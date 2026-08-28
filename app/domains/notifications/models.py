import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import BroadcastCampaignStatus, NotificationCategory


class NotificationRule(Base):
    """Automation rules for service reminders and triggered notifications."""

    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    cadence: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReminderDispatch(Base):
    """One row per reminder actually sent — the reason a cron can run daily.

    WITHOUT THIS, `evaluate_rule` re-sent to every matching customer on every
    run: the due-soon query has no lower bound, so a vehicle that is overdue
    matches forever. A daily job would have told the same owner their service
    was due every single day, indefinitely. That is not a reminder, it is a
    reason to uninstall the app.

    The uniqueness key is (rule, vehicle, milestone, stage):
      * `milestone` is the `next_service_due` value the reminder was sent FOR,
        so once the vehicle is serviced and the due date moves, the next cycle
        is legitimately a new reminder rather than a suppressed duplicate;
      * `stage` is the cadence step (30 / 7 / 1 / 0 days before), so the
        customer gets each step once and only once.
    """

    __tablename__ = "reminder_dispatches"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "owned_vehicle_id",
            "milestone",
            "stage",
            name="uq_reminder_dispatch_once",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("notification_rules.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    owned_vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=False, index=True
    )
    #: The service-due date this reminder was about.
    milestone: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Days-before bucket: 30, 7, 1, 0, or negative for an overdue nudge.
    stage: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BroadcastCampaign(Base):
    __tablename__ = "broadcast_campaigns"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    segment_key: Mapped[str] = mapped_column(String(100), nullable=False)
    channels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[BroadcastCampaignStatus] = mapped_column(
        Enum(BroadcastCampaignStatus, name="broadcast_campaign_status"),
        default=BroadcastCampaignStatus.draft,
        nullable=False,
    )
    reach_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserNotification(Base):
    """In-app notification feed for customers and staff."""

    __tablename__ = "user_notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[NotificationCategory] = mapped_column(
        Enum(NotificationCategory, name="notification_category"), nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deep_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("broadcast_campaigns.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="notifications")


class NotificationDelivery(Base):
    """Per-channel outcome for one notification.

    Without this a failed send is invisible: a bounced email or a dead push
    token leaves the customer uninformed and nobody any the wiser. It is also
    what makes retries possible and answers "why didn't they get it?" —
    a suppressed channel writes a row saying so rather than silently vanishing.
    """

    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("user_notifications.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    #: Catalogue event key, e.g. "support.staff_replied". Null for broadcasts.
    event_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeviceToken(Base):
    """A push token for one installation.

    Keyed on the token, not the user: the same person may have a phone and a
    tablet, and reinstalling issues a fresh token for the same device. Rows are
    pruned when the push provider reports the token as dead.
    """

    __tablename__ = "device_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationPreference(Base):
    """Per-category, per-channel opt-out.

    Absence means "use the catalogue default", so a new category or channel
    works without backfilling a row for every user. Only deviations are stored.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category", "channel", name="uq_notif_pref"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[NotificationCategory] = mapped_column(
        Enum(NotificationCategory, name="notification_category"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
