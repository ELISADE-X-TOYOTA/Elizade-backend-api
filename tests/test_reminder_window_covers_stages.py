"""The 30-day service reminder that could never fire.

`evaluate_rule` read the query window as
`int(config.get("days_before", max(stages)))` — the widest stage was used only
when `days_before` was ABSENT. Production's live rule is

    {"title": ..., "deep_link": "/service/book", "days_before": 14}

with no `stages` key, so stages fell back to the documented default
(30, 7, 1, 0) while the query window stayed 14. A vehicle 30 days out was
never selected, so the 30-day step could not fire for anybody, ever.

Production's dispatch log is the proof: 23 reminders sent, at stages 7, 0 and
-7. Not one at 30.

QA reported exactly this — the 30-day reminder never arrives — and it is not
reachable by hand, because seeing it requires a vehicle due in precisely 30
days on the day you happen to test.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.customers.models import OwnedVehicle
from app.domains.notifications.cadence import DEFAULT_STAGES
from app.domains.notifications.models import NotificationRule, ReminderDispatch
from app.domains.notifications.service import evaluate_rule


def _vehicle(db_session, user, *, days_until_service: int, plate: str):
    car = OwnedVehicle(
        user_id=user.id,
        vin=f"JTDBT9230009{plate}",
        make="Toyota",
        model="Corolla",
        trim="LE",
        color="White",
        year=2023,
        registration_number=f"REG-{plate}",
        mileage=30_000,
        next_service_due=datetime.now(timezone.utc) + timedelta(days=days_until_service),
    )
    db_session.add(car)
    db_session.commit()
    return car


@pytest.fixture
def production_shaped_rule(db_session):
    """The rule as it is actually configured in production."""
    rule = NotificationRule(
        name="Service due reminder",
        trigger_key="service_due_soon",
        channels=["in_app"],
        cadence="daily",
        is_active=True,
        config={"title": "Your Toyota is due for service", "days_before": 14},
    )
    db_session.add(rule)
    db_session.commit()
    return rule


def _dispatched_stages(db_session, rule):
    db_session.flush()
    return sorted(
        s for (s,) in db_session.query(ReminderDispatch.stage)
        .filter(ReminderDispatch.rule_id == rule.id)
        .all()
    )


# ── The bug ──────────────────────────────────────────────────────────────


def test_the_thirty_day_reminder_fires(db_session, customer_user, production_shaped_rule):
    """THE REPORTED DEFECT.

    A vehicle 30 days out, under the production rule, must be reminded.
    """
    _vehicle(db_session, customer_user, days_until_service=30, plate="0030")

    evaluate_rule(db_session, production_shaped_rule.id)

    assert 30 in _dispatched_stages(db_session, production_shaped_rule), (
        "the 30-day step never fired — days_before capped the query window "
        "below it, exactly as in production"
    )


def test_days_before_can_no_longer_disable_a_stage(db_session, customer_user, production_shaped_rule):
    """`days_before: 14` must not silently switch off the 30-day step.

    A stage that is configured is a stage that gets queried, or the cadence
    means something other than what it says.
    """
    _vehicle(db_session, customer_user, days_until_service=max(DEFAULT_STAGES), plate="0031")

    result = evaluate_rule(db_session, production_shaped_rule.id)

    assert result.matchedUsers == 1, "the vehicle was never even selected"
    assert result.notificationsCreated == 1


def test_a_wider_days_before_is_still_honoured(db_session, customer_user):
    """An operator widening the window keeps working — it only cannot narrow
    below the stages."""
    rule = NotificationRule(
        name="Wide",
        trigger_key="service_due_soon",
        channels=["in_app"],
        cadence="daily",
        is_active=True,
        # 90-day window with an explicit 60-day step.
        config={"days_before": 90, "stages": [60, 7]},
    )
    db_session.add(rule)
    db_session.commit()
    _vehicle(db_session, customer_user, days_until_service=60, plate="0060")

    evaluate_rule(db_session, rule.id)

    assert 60 in _dispatched_stages(db_session, rule)


# ── Still bounded ────────────────────────────────────────────────────────


def test_a_vehicle_outside_every_stage_is_left_alone(db_session, customer_user, production_shaped_rule):
    """Widening the window must not turn the sweep into a broadcast."""
    _vehicle(db_session, customer_user, days_until_service=120, plate="0120")

    result = evaluate_rule(db_session, production_shaped_rule.id)

    assert result.notificationsCreated == 0
    assert _dispatched_stages(db_session, production_shaped_rule) == []


def test_each_stage_is_sent_once_only(db_session, customer_user, production_shaped_rule):
    """The de-duplication that makes a daily cron safe still holds.

    Without it a daily job tells the same owner their service is due every
    single day — which is not a reminder, it is a reason to uninstall.
    """
    _vehicle(db_session, customer_user, days_until_service=30, plate="0032")

    first = evaluate_rule(db_session, production_shaped_rule.id)
    second = evaluate_rule(db_session, production_shaped_rule.id)

    assert first.notificationsCreated == 1
    assert second.notificationsCreated == 0, "the same step was sent twice"
    assert _dispatched_stages(db_session, production_shaped_rule) == [30]


def test_the_cadence_escalates_as_the_date_approaches(db_session, customer_user, production_shaped_rule):
    """30, then 7, then 1, then 0 — each once, as the clock advances.

    The clock moves, not the due date: the due date is the de-duplication key,
    so shifting it would read as the customer rescheduling and start a fresh
    cycle every run.
    """
    car = _vehicle(db_session, customer_user, days_until_service=30, plate="0033")
    due = car.next_service_due

    for days_out in (30, 7, 1, 0):
        evaluate_rule(db_session, production_shaped_rule.id, now=due - timedelta(days=days_out))

    assert _dispatched_stages(db_session, production_shaped_rule) == [0, 1, 7, 30]
