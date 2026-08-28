"""The daily sweep, end to end.

The property under test is the one that decides whether this feature can be
switched on at all: running the sweep repeatedly must not repeatedly tell the
same customer the same thing.

Before the sent-log existed, `evaluate_rule` selected every vehicle whose
service was due within the window — with no lower bound — and dispatched to
all of them on every call. Nothing ran it, so nothing broke. The moment a cron
did, every owner with an overdue vehicle would have been mailed daily forever.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.notifications.cadence import DEFAULT_STAGES
from app.domains.notifications.models import (
    NotificationRule,
    ReminderDispatch,
    UserNotification,
)
from app.domains.notifications.service import evaluate_due_rules


@pytest.fixture
def owned_vehicle(owned_vehicle_factory):
    return owned_vehicle_factory()


@pytest.fixture
def reminder_rule(db_session):
    rule = NotificationRule(
        name="Service due reminder",
        trigger_key="service_due_soon",
        channels=["in_app"],
        cadence="daily",
        is_active=True,
        config={"stages": list(DEFAULT_STAGES)},
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


def _set_due(db_session, vehicle, *, days_from_now: float):
    vehicle.next_service_due = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    db_session.commit()
    db_session.refresh(vehicle)


def _notifications(db_session, user_id) -> list[UserNotification]:
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user_id)
        .all()
    )


def _dispatches(db_session) -> list[ReminderDispatch]:
    return db_session.query(ReminderDispatch).all()


# ── The core guarantee ───────────────────────────────────────────────────


def test_a_due_vehicle_is_reminded_once(db_session, customer_user, owned_vehicle, reminder_rule):
    _set_due(db_session, owned_vehicle, days_from_now=7)

    evaluate_due_rules(db_session)

    assert len(_notifications(db_session, customer_user.id)) == 1
    assert len(_dispatches(db_session)) == 1


def test_running_the_sweep_again_sends_nothing(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    """THE test. A daily cron calls this every day."""
    _set_due(db_session, owned_vehicle, days_from_now=7)

    evaluate_due_rules(db_session)
    evaluate_due_rules(db_session)
    evaluate_due_rules(db_session)

    assert len(_notifications(db_session, customer_user.id)) == 1, "the customer was told repeatedly"


def test_thirty_consecutive_days_produce_a_handful_not_thirty(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    """Simulates a month of daily cron runs against one vehicle.

    The due date is FIXED and the clock advances — which is what a cron does.
    Moving the due date instead would not be the same experiment: the due date
    is the de-duplication key, so shifting it daily reads as the customer
    rescheduling the service and legitimately starts a fresh cycle each time.
    (That is exactly the false negative this test caught in its first version.)

    The customer should cross 30 / 7 / 1 / 0 and the overdue nudge — five
    messages, not thirty.
    """
    _set_due(db_session, owned_vehicle, days_from_now=30)
    start = datetime.now(timezone.utc)

    for offset in range(33):
        evaluate_due_rules(db_session, now=start + timedelta(days=offset))

    count = len(_notifications(db_session, customer_user.id))
    assert count <= len(DEFAULT_STAGES) + 1, f"sent {count} reminders for one service"
    assert count >= 2, "escalation never fired"


# ── The overdue case that had no floor ───────────────────────────────────


def test_a_long_overdue_vehicle_is_left_alone(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    """Two years overdue used to match the query on every single run."""
    _set_due(db_session, owned_vehicle, days_from_now=-730)

    evaluate_due_rules(db_session)

    assert _notifications(db_session, customer_user.id) == []


def test_a_recently_overdue_vehicle_gets_one_nudge(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    _set_due(db_session, owned_vehicle, days_from_now=-2)

    evaluate_due_rules(db_session)
    evaluate_due_rules(db_session)

    assert len(_notifications(db_session, customer_user.id)) == 1


# ── Not yet due ──────────────────────────────────────────────────────────


def test_a_vehicle_outside_the_window_is_not_reminded(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    _set_due(db_session, owned_vehicle, days_from_now=90)

    evaluate_due_rules(db_session)

    assert _notifications(db_session, customer_user.id) == []


def test_a_vehicle_with_no_due_date_is_skipped(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    owned_vehicle.next_service_due = None
    db_session.commit()

    evaluate_due_rules(db_session)

    assert _notifications(db_session, customer_user.id) == []


# ── Servicing the vehicle starts a fresh cycle ───────────────────────────


def test_a_new_due_date_is_a_new_reminder_cycle(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    """Dedup keys on the milestone, so the NEXT service is not suppressed.

    Keying on (rule, vehicle) alone would silence the customer forever after
    their first ever reminder.
    """
    _set_due(db_session, owned_vehicle, days_from_now=1)
    evaluate_due_rules(db_session)
    first = len(_notifications(db_session, customer_user.id))
    assert first == 1

    # Serviced — the due date moves out six months, then comes round again.
    _set_due(db_session, owned_vehicle, days_from_now=180)
    evaluate_due_rules(db_session)
    assert len(_notifications(db_session, customer_user.id)) == 1, "too early, should be silent"

    _set_due(db_session, owned_vehicle, days_from_now=1)
    evaluate_due_rules(db_session)
    assert len(_notifications(db_session, customer_user.id)) == 2, "the new cycle was suppressed"


# ── Resilience ───────────────────────────────────────────────────────────


def test_an_inactive_rule_does_nothing(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    reminder_rule.is_active = False
    db_session.commit()
    _set_due(db_session, owned_vehicle, days_from_now=7)

    evaluate_due_rules(db_session)

    assert _notifications(db_session, customer_user.id) == []


def test_a_broken_rule_does_not_stop_the_others(
    db_session, customer_user, owned_vehicle, reminder_rule
):
    """One misconfigured rule must not silence every service reminder."""
    broken = NotificationRule(
        name="Broken",
        trigger_key="not_a_real_trigger",
        channels=["in_app"],
        cadence="daily",
        is_active=True,
        config={},
    )
    db_session.add(broken)
    db_session.commit()
    _set_due(db_session, owned_vehicle, days_from_now=7)

    summary = evaluate_due_rules(db_session)

    assert summary["errors"], "the broken rule was not reported"
    assert len(_notifications(db_session, customer_user.id)) == 1, "the good rule was skipped"


def test_the_sweep_reports_what_it_did(db_session, customer_user, owned_vehicle, reminder_rule):
    """The cron logs this line; it has to be meaningful."""
    _set_due(db_session, owned_vehicle, days_from_now=7)

    summary = evaluate_due_rules(db_session)

    assert summary["rulesEvaluated"] >= 1
    assert summary["notificationsCreated"] >= 1
