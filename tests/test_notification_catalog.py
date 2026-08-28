"""The notification event catalogue.

Pure data and string formatting, so these run without a database — which is
the point: the copy customers read should be checkable in a second, not gated
on Postgres being up.

The rendering tests matter more than they look. A template that silently emits
"Reply on ticket {reference}" is the kind of bug that reaches a customer and
nobody notices until they screenshot it.
"""

import pytest

from app.domains.notifications import catalog
from app.domains.notifications.catalog import MissingContext
from app.domains.notifications.preferences import CONTROLLABLE, DEFAULTS, default_for
from app.domains.shared.enums import NotificationCategory


# ── Catalogue integrity ──────────────────────────────────────────────────


def test_event_keys_are_unique():
    keys = [e.key for e in catalog.ALL_EVENTS]
    assert len(keys) == len(set(keys))


def test_every_event_is_reachable_by_key():
    assert set(catalog.BY_KEY) == {e.key for e in catalog.ALL_EVENTS}


def test_every_event_delivers_in_app():
    """In-app is the permanent record — an event that skips it leaves no trace."""
    for event in catalog.ALL_EVENTS:
        assert catalog.IN_APP in event.channels, f"{event.key} has no in-app channel"


def test_every_channel_is_one_the_dispatcher_knows():
    valid = {catalog.IN_APP, catalog.EMAIL, catalog.PUSH, catalog.SMS}
    for event in catalog.ALL_EVENTS:
        assert set(event.channels) <= valid, f"{event.key} names an unknown channel"


def test_every_category_is_a_real_enum_member():
    for event in catalog.ALL_EVENTS:
        assert isinstance(event.category, NotificationCategory)


def test_only_security_and_safety_events_bypass_preferences():
    """`force` overrides a customer's choice, so it must stay a short list."""
    forced = {e.key for e in catalog.ALL_EVENTS if e.force}
    assert forced == {
        "auth.new_device_sign_in",
        "auth.contact_details_changed",
        "warranty.recall_affects_vehicle",
    }


def test_no_promotional_event_is_forced():
    for event in catalog.ALL_EVENTS:
        if event.category == NotificationCategory.promo:
            assert not event.force, f"{event.key} would ignore the marketing opt-out"


# ── Rendering ────────────────────────────────────────────────────────────

FULL_CONTEXT = {
    "field": "email address",
    "vehicle_label": "2022 Toyota Hilux",
    "when": "14 Aug at 09:30",
    "branch": "Elizade Ikeja",
    "valid_until": "30 Aug 2026",
    "amount": "NGN 4,500,000",
    "model": "Land Cruiser",
    "service_type": "Periodic Maintenance",
    "due_date": "2 Sep 2026",
    "description": "Rear brake discs",
    "appointment_id": "appt-1",
    "claim_type": "Powertrain",
    "reason": "Outside the mileage limit",
    "severity": "critical",
    "recall_title": "Airbag inflator",
    "vin": "JTDB1234567890001",
    "details": "a clearer photo of the vehicle licence",
    "request_id": "req-1",
    "reference": "SUP-1042",
    "subject": "Warning light on dashboard",
    "sla_hours": 4,
    "ticket_id": "tk-1",
    "agent_name": "Amaka",
}


@pytest.mark.parametrize("event", catalog.ALL_EVENTS, ids=lambda e: e.key)
def test_every_event_renders_with_no_leftover_placeholders(event):
    rendered = catalog.render(event, FULL_CONTEXT)
    for field in (rendered.title, rendered.body, rendered.deep_link or ""):
        assert "{" not in field and "}" not in field, f"{event.key} left a placeholder in {field!r}"
    assert rendered.title.strip()
    assert rendered.body.strip()


@pytest.mark.parametrize("event", catalog.ALL_EVENTS, ids=lambda e: e.key)
def test_requires_lists_every_key_the_templates_use(event):
    """A template key missing from `requires` escapes the guard and raises later."""
    if not event.requires:
        # No placeholders expected anywhere.
        joined = f"{event.title}{event.body}{event.deep_link or ''}"
        assert "{" not in joined, f"{event.key} interpolates but declares no requires"
        return
    catalog.render(event, {k: "x" for k in event.requires})


def test_missing_context_raises_rather_than_emitting_a_placeholder():
    with pytest.raises(MissingContext):
        catalog.render(catalog.TICKET_STAFF_REPLIED, {"reference": "SUP-1"})


def test_empty_string_counts_as_missing():
    """An empty agent name would render "  replied to your ticket"."""
    context = dict(FULL_CONTEXT, agent_name="")
    with pytest.raises(MissingContext):
        catalog.render(catalog.TICKET_STAFF_REPLIED, context)


def test_deep_links_are_interpolated_too():
    rendered = catalog.render(catalog.TICKET_RESOLVED, FULL_CONTEXT)
    assert rendered.deep_link == "/ticket/tk-1"


def test_rendered_event_carries_the_spec_metadata():
    rendered = catalog.render(catalog.RECALL_AFFECTS_VEHICLE, FULL_CONTEXT)
    assert rendered.force is True
    assert rendered.category == NotificationCategory.warranty
    assert catalog.SMS in rendered.channels


# ── Preference defaults ──────────────────────────────────────────────────


def test_in_app_is_not_customer_controllable():
    """It is the record; muting it would leave nowhere to look."""
    assert catalog.IN_APP not in CONTROLLABLE


def test_promotions_are_opt_in_on_every_channel():
    for channel in CONTROLLABLE:
        assert default_for(NotificationCategory.promo, channel) is False


def test_sms_is_opt_in_everywhere():
    """It costs money per message and recipients may be charged."""
    for category in NotificationCategory:
        assert default_for(category, catalog.SMS) is False


def test_transactional_categories_default_to_push_and_email():
    for category in (
        NotificationCategory.service,
        NotificationCategory.sales,
        NotificationCategory.warranty,
        NotificationCategory.support,
    ):
        assert default_for(category, catalog.PUSH) is True
        assert default_for(category, catalog.EMAIL) is True


def test_every_category_has_defaults():
    for category in NotificationCategory:
        assert category in DEFAULTS
