"""Notify Me — a subscriber hears about a change however it was made.

Notify Me was not broken. `_notify_availability_subscribers` worked, and the
dedicated admin status endpoint called it. But that was never the only way the
column moved:

  * the reservation-expiry sweep returned lapsed holds to `available`
  * reserving a car set it from the sales service
  * approving an ownership claim set it to `sold`

each with a bare assignment that told nobody — so the single most valuable
moment, a held car coming back on sale, was silent.

(I first assumed the general admin PATCH was a fourth gap. It is not:
`VehicleUpdateIn` exposes no availability field, so that path never wrote the
column. The guard in `update_vehicle` stays as a tripwire for the day someone
adds one.)

These tests pin the invariant: every route through `set_availability` alerts,
and no route can fail its own operation because mail was down.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.inventory import service as inventory_service
from app.domains.inventory.models import VehicleAvailabilitySubscription
from app.domains.notifications.models import UserNotification
from app.domains.shared.enums import AvailabilityStatus, ReservationStatus


@pytest.fixture
def held_vehicle(vehicle_factory):
    return vehicle_factory(availability=AvailabilityStatus.reserved)


@pytest.fixture
def watcher(db_session, customer_user, held_vehicle):
    """A customer waiting to hear about this vehicle."""
    sub = VehicleAvailabilitySubscription(
        user_id=customer_user.id, vehicle_id=held_vehicle.id, is_active=True
    )
    db_session.add(sub)
    db_session.commit()
    return sub


def _alerts(db_session, user):
    # The test session is built with autoflush=False, so a notification that
    # `set_availability` has added but not committed is invisible to a count
    # until it is flushed. Nothing to do with the feature under test.
    db_session.flush()
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .count()
    )


def test_the_admin_status_endpoint_alerts_and_closes_the_subscription(
    db_session, customer_user, held_vehicle, watcher
):
    """The path that always worked — pinned so it stays working."""
    before = _alerts(db_session, customer_user)

    inventory_service.set_availability(
        db_session, held_vehicle, AvailabilityStatus.available
    )

    assert _alerts(db_session, customer_user) == before + 1
    db_session.expire_all()
    assert db_session.get(VehicleAvailabilitySubscription, watcher.id).is_active is False


def test_reserving_a_vehicle_alerts_subscribers(
    db_session, customer_user, vehicle_factory, staff_user
):
    """A REAL GAP. `create_reservation` set `reserved` with a bare assignment,
    so someone tracking the car was never told it had just been taken."""
    from app.domains.sales.schemas import ReservationCreateIn
    from app.domains.sales import service as sales_service

    car = vehicle_factory(availability=AvailabilityStatus.available)
    db_session.add(
        VehicleAvailabilitySubscription(
            user_id=customer_user.id, vehicle_id=car.id, is_active=True
        )
    )
    db_session.commit()
    before = _alerts(db_session, customer_user)

    # Reserved by somebody else — the watcher is the one who must hear.
    sales_service.create_reservation(
        db_session, staff_user, ReservationCreateIn(vehicleId=car.id, depositAmount=1)
    )

    assert _alerts(db_session, customer_user) == before + 1


def test_a_lapsed_reservation_returning_a_car_alerts_subscribers(
    db_session, customer_user, held_vehicle, watcher
):
    """THE MOMENT THAT MATTERS MOST — and it was silent."""
    from app.domains.sales.models import Reservation
    from app.jobs.expire_reservations import expire_due

    db_session.add(
        Reservation(
            user_id=customer_user.id,
            vehicle_id=held_vehicle.id,
            status=ReservationStatus.pending,
            deposit_amount=Decimal("1"),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    db_session.commit()
    before = _alerts(db_session, customer_user)

    expired, released = expire_due(db_session)
    assert (expired, released) == (1, 1)
    assert _alerts(db_session, customer_user) == before + 1, (
        "the car came back on sale and the person waiting for it was not told"
    )


def test_no_alert_when_the_status_does_not_actually_change(
    db_session, customer_user, held_vehicle, watcher
):
    """Saving a listing without touching availability must not spam anyone."""
    before = _alerts(db_session, customer_user)
    changed = inventory_service.set_availability(
        db_session, held_vehicle, AvailabilityStatus.reserved
    )
    assert changed is False
    assert _alerts(db_session, customer_user) == before


def test_a_mail_outage_does_not_abort_the_release(
    db_session, customer_user, held_vehicle, watcher, monkeypatch
):
    """THE BUG THIS NEARLY INTRODUCED.

    `_notify_availability_subscribers` deliberately lets delivery errors abort
    the enclosing transaction, which is right for an admin who can retry. Wired
    into the expiry sweep unguarded, one Postmark outage would leave every
    lapsed car locked. `strict_notify=False` is what stops that.
    """
    def boom(*a, **kw):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr(inventory_service, "_notify_availability_subscribers", boom)

    changed = inventory_service.set_availability(
        db_session, held_vehicle, AvailabilityStatus.available, strict_notify=False
    )

    assert changed is True
    # Not expire_all() here: `set_availability` deliberately does not commit,
    # so reloading would discard the very change being asserted.
    assert held_vehicle.availability is AvailabilityStatus.available, (
        "the release must stand even though the alert failed"
    )


def test_strict_callers_still_surface_a_mail_failure(
    db_session, held_vehicle, watcher, monkeypatch
):
    """An admin acting on a screen should see the failure, not a silent miss."""
    def boom(*a, **kw):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr(inventory_service, "_notify_availability_subscribers", boom)

    with pytest.raises(RuntimeError):
        inventory_service.set_availability(
            db_session, held_vehicle, AvailabilityStatus.available
        )


def test_an_inactive_subscription_is_not_alerted_again(
    db_session, customer_user, held_vehicle, watcher
):
    """One-shot: a closed subscription must not fire on later changes."""
    watcher.is_active = False
    db_session.commit()
    before = _alerts(db_session, customer_user)

    inventory_service.set_availability(db_session, held_vehicle, AvailabilityStatus.available)
    assert _alerts(db_session, customer_user) == before
