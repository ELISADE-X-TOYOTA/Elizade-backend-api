"""Two notifications that were catalogued and never sent.

RECALL is the serious one. `notify_recall` stamped `notified_at` on every
affected vehicle, sent nothing, and returned `notifiedCount` — so an admin
pressed "notify owners" on a SAFETY RECALL, read "47 notified", and no owner
heard. Reporting success is worse than failing: stamping the column also meant
a second attempt found nothing pending and sent nothing again, so the mistake
was self-concealing and permanent.

CONTACT CHANGE is a security alert. Someone could change the email on an
account and the person losing it was never told.
"""

from datetime import datetime, timezone

import pytest

from app.domains.customers.models import OwnedVehicle
from app.domains.notifications.models import UserNotification
from app.domains.shared.enums import RecallSeverity
from app.domains.users.schemas import UserProfileUpdateIn
from app.domains.users import service as users_service
from app.domains.warranty import service as warranty_service
from app.domains.warranty.models import RecallCampaign, RecallVehicle


def _alerts(db_session, user):
    db_session.flush()
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .count()
    )


@pytest.fixture
def recalled(db_session, customer_user):
    """A live recall with one affected, un-notified owner."""
    car = OwnedVehicle(
        user_id=customer_user.id,
        vin="JTDBT923000999111",
        make="Toyota",
        model="Corolla",
        trim="LE",
        color="White",
        year=2023,
        registration_number="ABC-999",
    )
    db_session.add(car)
    db_session.flush()

    recall = RecallCampaign(
        reference_code="RC-2026-01",
        title="Front airbag inflator",
        description="Inflator may rupture.",
        severity=RecallSeverity.critical,
        affected_models=["Corolla"],
    )
    db_session.add(recall)
    db_session.flush()

    link = RecallVehicle(recall_id=recall.id, owned_vehicle_id=car.id, user_id=customer_user.id)
    db_session.add(link)
    db_session.commit()
    return recall, link


def test_notifying_a_recall_actually_reaches_the_owner(db_session, customer_user, recalled):
    recall, _ = recalled
    before = _alerts(db_session, customer_user)

    result = warranty_service.notify_recall(db_session, recall.id)

    assert result.notifiedCount == 1
    assert _alerts(db_session, customer_user) == before + 1, (
        "the owner of a recalled vehicle was not told"
    )


def test_the_alert_names_the_vehicle_and_the_recall(db_session, customer_user, recalled):
    recall, _ = recalled
    warranty_service.notify_recall(db_session, recall.id)

    row = (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == customer_user.id)
        .order_by(UserNotification.created_at.desc())
        .first()
    )
    text = f"{row.title} {row.body}"
    assert "Corolla" in text, text
    assert "{" not in text, f"unrendered placeholder: {text}"


def test_an_owner_who_was_not_reached_is_not_marked_notified(
    db_session, customer_user, recalled, monkeypatch
):
    """THE CORE OF THE BUG.

    `notified_at` used to be stamped unconditionally, so a failed campaign
    looked complete and could never be retried — the rows were no longer
    pending. It must only be stamped for owners actually reached.
    """
    recall, link = recalled

    def nothing_sent(*a, **kw):
        from app.domains.notifications.notify import NotifyResult

        return NotifyResult(notification_id=None, sent=[], suppressed=[], failed=["in_app"])

    monkeypatch.setattr(warranty_service, "notify", nothing_sent)

    result = warranty_service.notify_recall(db_session, recall.id)

    assert result.notifiedCount == 0, "it must not claim to have notified anyone"
    db_session.expire_all()
    assert db_session.get(RecallVehicle, link.id).notified_at is None, (
        "an unreached owner must stay pending so the campaign can be retried"
    )


def test_one_failure_does_not_stop_the_campaign(db_session, customer_user, recalled):
    """A safety recall must keep going past a single unreachable owner."""
    recall, _ = recalled
    calls = {"n": 0}
    real = warranty_service.notify

    def boom_once(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transport down")
        return real(*a, **kw)

    warranty_service.notify = boom_once
    try:
        result = warranty_service.notify_recall(db_session, recall.id)
    finally:
        warranty_service.notify = real

    assert result.notifiedCount == 0
    assert calls["n"] == 1, "the loop should have continued rather than raised"


def test_already_notified_owners_are_not_told_twice(db_session, customer_user, recalled):
    recall, link = recalled
    warranty_service.notify_recall(db_session, recall.id)
    before = _alerts(db_session, customer_user)

    again = warranty_service.notify_recall(db_session, recall.id)

    assert again.notifiedCount == 0
    assert _alerts(db_session, customer_user) == before


# ── Contact details ──────────────────────────────────────────────────────


def test_changing_the_email_alerts_the_account(db_session, customer_user):
    before = _alerts(db_session, customer_user)

    users_service.update_profile(
        db_session, customer_user, UserProfileUpdateIn(email="moved@elizade.com")
    )

    assert _alerts(db_session, customer_user) == before + 1, (
        "an email change is a security event and must not be silent"
    )


def test_changing_a_harmless_field_does_not_alert(db_session, customer_user):
    """Updating a city is not a security event; do not cry wolf."""
    before = _alerts(db_session, customer_user)
    users_service.update_profile(db_session, customer_user, UserProfileUpdateIn(city="Abuja"))
    assert _alerts(db_session, customer_user) == before


def test_the_previous_address_is_warned_too(db_session, customer_user, monkeypatch):
    """The address being REPLACED is the one an attacker has just cut off.

    Telling only the new address is useless to the person losing the account.
    """
    sent: list[str] = []

    def capture(*, to_email, subject, body, category, html_body=None):
        sent.append(to_email)

    monkeypatch.setattr(users_service.email_service, "send_notification", capture)
    old = customer_user.email

    users_service.update_profile(
        db_session, customer_user, UserProfileUpdateIn(email="attacker@elsewhere.com")
    )

    assert old in sent, f"the previous address was never warned; sent to {sent}"
