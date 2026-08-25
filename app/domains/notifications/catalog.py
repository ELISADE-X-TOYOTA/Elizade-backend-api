"""The notification event catalogue.

One place that turns a domain event into the words a customer reads, the
category it files under, where tapping it goes, and which channels carry it.

WHY A CATALOGUE RATHER THAN INLINE STRINGS: copy lives where someone can review
it without reading service code, the same event always renders the same way, and
adding a channel to "ticket replied" is a one-line change here instead of a hunt
through the support domain.

Pure data and formatting — no database, no I/O — so the whole catalogue is
testable without a running Postgres.
"""

from dataclasses import dataclass, field
from typing import Any

from app.domains.shared.enums import NotificationCategory

# Channel identifiers, mirroring dispatcher.VALID_CHANNELS.
IN_APP = "in_app"
EMAIL = "email"
PUSH = "push"
SMS = "sms"


@dataclass(frozen=True)
class EventSpec:
    """How one domain event becomes a notification."""

    key: str
    category: NotificationCategory
    #: `str.format`-style templates rendered against the event context.
    title: str
    body: str
    #: In-app route the notification opens. `None` for events with nowhere to go.
    deep_link: str | None = None
    channels: tuple[str, ...] = (IN_APP,)
    #: Security and account events ignore user preferences — see `dispatcher`.
    #: A customer does not opt out of being told their account was accessed.
    force: bool = False
    #: Context keys the templates need. Missing ones raise at render time
    #: rather than emitting a notification with a literal "{model}" in it.
    requires: tuple[str, ...] = field(default=())


def _spec(*args: Any, **kwargs: Any) -> EventSpec:
    return EventSpec(*args, **kwargs)


# ── Security & account ───────────────────────────────────────────────────
# `force=True`: never suppressed, on any channel, by any preference.

NEW_DEVICE_SIGN_IN = _spec(
    key="auth.new_device_sign_in",
    category=NotificationCategory.system,
    title="New sign-in to your account",
    body="Your Elizade Connect account was signed in to on a new device. If this wasn't you, contact us straight away.",
    deep_link="/profile",
    channels=(IN_APP, EMAIL),
    force=True,
)

CONTACT_DETAILS_CHANGED = _spec(
    key="auth.contact_details_changed",
    category=NotificationCategory.system,
    title="Your contact details changed",
    body="The {field} on your Elizade Connect account was updated. If this wasn't you, contact us straight away.",
    deep_link="/profile",
    channels=(IN_APP, EMAIL),
    force=True,
    requires=("field",),
)

# ── Sales ────────────────────────────────────────────────────────────────

TEST_DRIVE_CONFIRMED = _spec(
    key="sales.test_drive_confirmed",
    category=NotificationCategory.sales,
    title="Test drive confirmed",
    body="Your test drive of the {vehicle_label} is confirmed for {when} at {branch}.",
    deep_link="/(tabs)/bookings",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("vehicle_label", "when", "branch"),
)

TEST_DRIVE_CANCELLED = _spec(
    key="sales.test_drive_cancelled",
    category=NotificationCategory.sales,
    title="Test drive cancelled",
    body="Your test drive of the {vehicle_label} has been cancelled. Book another time whenever suits you.",
    deep_link="/(tabs)/bookings",
    channels=(IN_APP, PUSH),
    requires=("vehicle_label",),
)

QUOTATION_ISSUED = _spec(
    key="sales.quotation_issued",
    category=NotificationCategory.sales,
    title="Your quote is ready",
    body="We've prepared your quote for the {vehicle_label}. It's valid until {valid_until}.",
    deep_link="/(tabs)/shop",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("vehicle_label", "valid_until"),
)

TRADE_IN_VALUED = _spec(
    key="sales.trade_in_valued",
    category=NotificationCategory.sales,
    title="Trade-in valuation ready",
    body="Your {vehicle_label} has been valued at {amount}. An adviser will confirm after a physical inspection.",
    deep_link="/trade-in",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("vehicle_label", "amount"),
)

WATCHED_MODEL_AVAILABLE = _spec(
    key="sales.watched_model_available",
    category=NotificationCategory.sales,
    title="{model} now in stock",
    body="A {model} you're tracking has arrived at {branch}.",
    deep_link="/(tabs)/shop",
    channels=(IN_APP, PUSH),
    requires=("model", "branch"),
)

# ── Service ──────────────────────────────────────────────────────────────

SERVICE_APPOINTMENT_CONFIRMED = _spec(
    key="service.appointment_confirmed",
    category=NotificationCategory.service,
    title="Service appointment confirmed",
    body="Your {service_type} for the {vehicle_label} is confirmed for {when} at {branch}.",
    deep_link="/(tabs)/service",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("service_type", "vehicle_label", "when", "branch"),
)

SERVICE_REMINDER_DUE = _spec(
    key="service.reminder_due",
    category=NotificationCategory.service,
    title="Service due soon",
    body="Your {vehicle_label} is due for service on {due_date}. Book a slot at your nearest branch.",
    deep_link="/book-service",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("vehicle_label", "due_date"),
)

EXTRA_WORK_NEEDS_APPROVAL = _spec(
    key="service.extra_work_needs_approval",
    category=NotificationCategory.service,
    title="Approval needed on your service",
    body="Our technician found additional work on your {vehicle_label}: {description} ({amount}). Work is paused until you approve.",
    deep_link="/service-detail/{appointment_id}",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("vehicle_label", "description", "amount", "appointment_id"),
)

VEHICLE_READY_FOR_COLLECTION = _spec(
    key="service.vehicle_ready",
    category=NotificationCategory.service,
    title="Your vehicle is ready",
    body="Your {vehicle_label} is ready for collection at {branch}.",
    deep_link="/service-detail/{appointment_id}",
    channels=(IN_APP, PUSH, SMS),
    requires=("vehicle_label", "branch", "appointment_id"),
)

SERVICE_INVOICE_ISSUED = _spec(
    key="service.invoice_issued",
    category=NotificationCategory.service,
    title="Your service invoice",
    body="The invoice for your {vehicle_label} service comes to {amount}.",
    deep_link="/service-detail/{appointment_id}",
    channels=(IN_APP, EMAIL),
    requires=("vehicle_label", "amount", "appointment_id"),
)

# ── Warranty ─────────────────────────────────────────────────────────────

WARRANTY_CLAIM_RECEIVED = _spec(
    key="warranty.claim_received",
    category=NotificationCategory.warranty,
    title="Warranty claim received",
    body="We've received your {claim_type} claim for the {vehicle_label}. Our warranty team will review it shortly.",
    deep_link="/warranty",
    channels=(IN_APP, EMAIL),
    requires=("claim_type", "vehicle_label"),
)

WARRANTY_CLAIM_APPROVED = _spec(
    key="warranty.claim_approved",
    category=NotificationCategory.warranty,
    title="Warranty claim approved",
    body="Your {claim_type} claim for the {vehicle_label} has been approved. Your branch will be in touch to arrange the work.",
    deep_link="/warranty",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("claim_type", "vehicle_label"),
)

WARRANTY_CLAIM_REJECTED = _spec(
    key="warranty.claim_rejected",
    category=NotificationCategory.warranty,
    title="Warranty claim decision",
    body="Your {claim_type} claim for the {vehicle_label} was not approved. Reason: {reason}",
    deep_link="/warranty",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("claim_type", "vehicle_label", "reason"),
)

RECALL_AFFECTS_VEHICLE = _spec(
    key="warranty.recall_affects_vehicle",
    category=NotificationCategory.warranty,
    title="Safety recall on your vehicle",
    body="A {severity} recall applies to your {vehicle_label}: {recall_title}. Please book an inspection.",
    deep_link="/warranty",
    channels=(IN_APP, PUSH, SMS),
    # Safety, not marketing — a customer should not be able to mute a recall.
    force=True,
    requires=("severity", "vehicle_label", "recall_title"),
)

# ── Ownership ────────────────────────────────────────────────────────────

OWNERSHIP_CLAIM_APPROVED = _spec(
    key="ownership.claim_approved",
    category=NotificationCategory.system,
    title="Vehicle added to your garage",
    body="Your {vehicle_label} has been verified and added to your garage.",
    deep_link="/garage",
    channels=(IN_APP, PUSH),
    requires=("vehicle_label",),
)

OWNERSHIP_CLAIM_REJECTED = _spec(
    key="ownership.claim_rejected",
    category=NotificationCategory.system,
    title="Ownership request declined",
    body="We couldn't verify your ownership request for chassis {vin}. Reason: {reason}",
    deep_link="/garage",
    channels=(IN_APP, PUSH),
    requires=("vin", "reason"),
)

# ── Support ──────────────────────────────────────────────────────────────

TICKET_OPENED = _spec(
    key="support.ticket_opened",
    category=NotificationCategory.support,
    title="Ticket {reference} opened",
    body="We've received your message about \"{subject}\". Expect a first response within {sla_hours} hours.",
    deep_link="/ticket/{ticket_id}",
    channels=(IN_APP, EMAIL),
    requires=("reference", "subject", "sla_hours", "ticket_id"),
)

TICKET_STAFF_REPLIED = _spec(
    key="support.staff_replied",
    category=NotificationCategory.support,
    title="Reply on ticket {reference}",
    body="{agent_name} replied to your ticket about \"{subject}\".",
    deep_link="/ticket/{ticket_id}",
    channels=(IN_APP, PUSH, EMAIL),
    requires=("reference", "agent_name", "subject", "ticket_id"),
)

TICKET_RESOLVED = _spec(
    key="support.ticket_resolved",
    category=NotificationCategory.support,
    title="Ticket {reference} resolved",
    body="Your ticket about \"{subject}\" has been marked resolved. Let us know how we did.",
    deep_link="/ticket/{ticket_id}",
    channels=(IN_APP, PUSH),
    requires=("reference", "subject", "ticket_id"),
)


ALL_EVENTS: tuple[EventSpec, ...] = (
    NEW_DEVICE_SIGN_IN,
    CONTACT_DETAILS_CHANGED,
    TEST_DRIVE_CONFIRMED,
    TEST_DRIVE_CANCELLED,
    QUOTATION_ISSUED,
    TRADE_IN_VALUED,
    WATCHED_MODEL_AVAILABLE,
    SERVICE_APPOINTMENT_CONFIRMED,
    SERVICE_REMINDER_DUE,
    EXTRA_WORK_NEEDS_APPROVAL,
    VEHICLE_READY_FOR_COLLECTION,
    SERVICE_INVOICE_ISSUED,
    WARRANTY_CLAIM_RECEIVED,
    WARRANTY_CLAIM_APPROVED,
    WARRANTY_CLAIM_REJECTED,
    RECALL_AFFECTS_VEHICLE,
    OWNERSHIP_CLAIM_APPROVED,
    OWNERSHIP_CLAIM_REJECTED,
    TICKET_OPENED,
    TICKET_STAFF_REPLIED,
    TICKET_RESOLVED,
)

BY_KEY: dict[str, EventSpec] = {e.key: e for e in ALL_EVENTS}


class MissingContext(KeyError):
    """A template referenced a key the caller did not supply."""


@dataclass(frozen=True)
class RenderedEvent:
    key: str
    category: NotificationCategory
    title: str
    body: str
    deep_link: str | None
    channels: tuple[str, ...]
    force: bool


def render(spec: EventSpec, context: dict[str, Any]) -> RenderedEvent:
    """Fill a spec's templates from `context`.

    Raises `MissingContext` rather than letting a half-rendered string reach a
    customer — "Reply on ticket {reference}" is worse than a caught error.
    """
    missing = [k for k in spec.requires if context.get(k) in (None, "")]
    if missing:
        raise MissingContext(f"{spec.key} needs: {', '.join(sorted(missing))}")

    def fill(template: str | None) -> str | None:
        if template is None:
            return None
        try:
            return template.format(**context)
        except KeyError as exc:  # a template key absent from `requires`
            raise MissingContext(f"{spec.key} template needs: {exc.args[0]}") from exc

    return RenderedEvent(
        key=spec.key,
        category=spec.category,
        title=fill(spec.title) or "",
        body=fill(spec.body) or "",
        deep_link=fill(spec.deep_link),
        channels=spec.channels,
        force=spec.force,
    )
