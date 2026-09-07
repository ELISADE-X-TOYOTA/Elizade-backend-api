"""The reservation expiry sweep.

WHY THESE MATTER: `create_reservation` writes `expires_at` and takes the
vehicle off sale, and until now nothing ever read that column back. Testing
alone left 12 of 30 vehicles stuck as `reserved` with no path to recovery, and
a customer tapping Reserve a second time got a 409 that looked like a broken
button.

Every case here is one a timeout sweep can get catastrophically wrong: putting
a paid-for car back on sale, or releasing one that somebody else still holds.
Neither is reachable by clicking around, and both are silent.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.sales.models import Reservation
from app.domains.shared.enums import AvailabilityStatus, ReservationStatus
from app.jobs.expire_reservations import expire_due

NOW = datetime.now(timezone.utc)


@pytest.fixture
def hold(db_session, customer_user, vehicle_factory):
    """A vehicle held by one reservation, with the vehicle marked reserved."""
    def _make(status: ReservationStatus, days: float) -> Reservation:
        vehicle = vehicle_factory(availability=AvailabilityStatus.reserved)
        row = Reservation(
            user_id=customer_user.id,
            vehicle_id=vehicle.id,
            status=status,
            deposit_amount=Decimal("2600000"),
            expires_at=NOW + timedelta(days=days),
        )
        db_session.add(row)
        db_session.commit()
        return row

    return _make


def _availability(db_session, reservation):
    from app.domains.inventory.models import Vehicle

    db_session.expire_all()
    return db_session.get(Vehicle, reservation.vehicle_id).availability


def test_a_lapsed_hold_puts_the_vehicle_back_on_sale(db_session, hold):
    r = hold(ReservationStatus.pending, -1)
    expired, released = expire_due(db_session, now=NOW)

    assert (expired, released) == (1, 1)
    db_session.expire_all()
    assert db_session.get(Reservation, r.id).status is ReservationStatus.expired
    assert _availability(db_session, r) is AvailabilityStatus.available


def test_a_hold_still_within_its_window_is_untouched(db_session, hold):
    r = hold(ReservationStatus.pending, +3)
    assert expire_due(db_session, now=NOW) == (0, 0)
    assert _availability(db_session, r) is AvailabilityStatus.reserved


def test_a_paid_deposit_is_never_released_by_a_timeout(db_session, hold):
    """The one that would cost real money.

    `deposit_paid` means the customer has handed over funds. Selling that car
    to somebody else because a timer elapsed is not a bug you get to explain.
    """
    r = hold(ReservationStatus.deposit_paid, -30)
    assert expire_due(db_session, now=NOW) == (0, 0)
    assert _availability(db_session, r) is AvailabilityStatus.reserved


def test_a_confirmed_sale_is_never_released_by_a_timeout(db_session, hold):
    r = hold(ReservationStatus.confirmed, -30)
    assert expire_due(db_session, now=NOW) == (0, 0)
    assert _availability(db_session, r) is AvailabilityStatus.reserved


def test_one_lapsed_hold_does_not_release_a_car_someone_else_holds(
    db_session, customer_user, hold
):
    """Two holds, one lapsed, one live — the car must stay off sale.

    Releasing on the first expiry would hand the vehicle back to the catalogue
    while a confirmed buyer still has a claim on it.
    """
    lapsed = hold(ReservationStatus.pending, -1)
    db_session.add(
        Reservation(
            user_id=customer_user.id,
            vehicle_id=lapsed.vehicle_id,
            status=ReservationStatus.confirmed,
            deposit_amount=Decimal("2600000"),
            expires_at=NOW + timedelta(days=9),
        )
    )
    db_session.commit()

    expired, released = expire_due(db_session, now=NOW)
    assert expired == 1, "the lapsed hold itself should still expire"
    assert released == 0, "but the vehicle is still claimed"
    assert _availability(db_session, lapsed) is AvailabilityStatus.reserved


def test_a_sold_vehicle_is_not_walked_back_to_available(db_session, hold, vehicle_factory):
    """`sold` outranks a stale hold: the car is gone, whatever the timer says."""
    r = hold(ReservationStatus.pending, -1)
    from app.domains.inventory.models import Vehicle

    db_session.get(Vehicle, r.vehicle_id).availability = AvailabilityStatus.sold
    db_session.commit()

    expired, released = expire_due(db_session, now=NOW)
    assert expired == 1
    assert released == 0
    assert _availability(db_session, r) is AvailabilityStatus.sold


def test_dry_run_reports_without_changing_anything(db_session, hold):
    r = hold(ReservationStatus.pending, -1)
    expired, released = expire_due(db_session, now=NOW, dry_run=True)

    assert (expired, released) == (1, 1), "it should still report what it would do"
    db_session.expire_all()
    assert db_session.get(Reservation, r.id).status is ReservationStatus.pending
    assert _availability(db_session, r) is AvailabilityStatus.reserved


def test_running_twice_is_a_no_op(db_session, hold):
    """A scheduler runs this repeatedly; the second pass must find nothing."""
    hold(ReservationStatus.pending, -1)
    assert expire_due(db_session, now=NOW) == (1, 1)
    assert expire_due(db_session, now=NOW) == (0, 0)


def test_nothing_due_is_not_an_error(db_session):
    assert expire_due(db_session, now=NOW) == (0, 0)
