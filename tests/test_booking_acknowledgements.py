"""Booking something and hearing nothing back.

Booking a test drive sent no notification of any kind. The only test-drive
event in the catalogue was `TEST_DRIVE_CONFIRMED`, and nothing fires it,
because there is no staff endpoint to confirm a test drive — so a customer
chose a slot, submitted, and heard nothing from anywhere, ever.

Booking a service was the same: `SERVICE_APPOINTMENT_CONFIRMED` fires only
from the staff `confirm` action, so the customer heard nothing until somebody
in the branch got round to it.

QA reported it as "booking confirmation notification not received". It was
never sent.

The copy says REQUESTED, not confirmed, and that distinction is the point: the
row is created with status `requested` and no human has seen it. Telling
someone their test drive is confirmed is how a customer arrives at a showroom
that is not expecting them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.notifications.models import UserNotification
from app.domains.sales import service as sales_service
from app.domains.sales.schemas import TestDriveCreateIn
from app.domains.shared.enums import AvailabilityStatus

SERVICE = "/api/v1/service"


def _alerts(db_session, user):
    db_session.flush()
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .order_by(UserNotification.created_at.desc())
        .all()
    )


@pytest.fixture
def vehicle(vehicle_factory):
    return vehicle_factory(
        make="Toyota", model="Corolla", year=2024, availability=AvailabilityStatus.available
    )


def _book_test_drive(db_session, user, vehicle, branch, *, days_ahead=3):
    return sales_service.create_test_drive(
        db_session,
        user,
        TestDriveCreateIn(
            vehicleId=vehicle.id,
            branchId=branch.id,
            scheduledAt=(datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat(),
        ),
    )


# ── Test drive ───────────────────────────────────────────────────────────


def test_booking_a_test_drive_notifies_the_customer(db_session, customer_user, vehicle, branch):
    """THE REPORTED DEFECT. Booking produced silence."""
    before = len(_alerts(db_session, customer_user))

    _book_test_drive(db_session, customer_user, vehicle, branch)

    assert len(_alerts(db_session, customer_user)) == before + 1, (
        "booking a test drive sent the customer nothing"
    )


def test_the_test_drive_alert_names_the_car_the_time_and_the_branch(
    db_session, customer_user, vehicle, branch
):
    _book_test_drive(db_session, customer_user, vehicle, branch)
    row = _alerts(db_session, customer_user)[0]
    text = f"{row.title} {row.body}"

    assert "Corolla" in text, text
    assert branch.name in text, text
    assert "{" not in text, f"unrendered placeholder: {text}"


def test_the_test_drive_alert_does_not_claim_to_be_confirmed(
    db_session, customer_user, vehicle, branch
):
    """A booking nobody has looked at yet is REQUESTED.

    Saying "confirmed" is how someone drives to a showroom that is not
    expecting them.
    """
    _book_test_drive(db_session, customer_user, vehicle, branch)
    row = _alerts(db_session, customer_user)[0]

    assert "confirmed" not in f"{row.title} {row.body}".lower(), row.body


def test_a_failed_notification_does_not_cost_the_booking(
    db_session, customer_user, vehicle, branch, monkeypatch
):
    """The booking is committed before anything is sent."""
    def boom(*a, **kw):
        raise RuntimeError("transport down")

    monkeypatch.setattr(sales_service, "safe_notify", boom)

    from app.domains.sales.models import TestDriveBooking

    with pytest.raises(RuntimeError):
        _book_test_drive(db_session, customer_user, vehicle, branch)

    assert (
        db_session.query(TestDriveBooking)
        .filter(TestDriveBooking.user_id == customer_user.id)
        .count()
        == 1
    ), "the booking must survive a notification failure"


def test_two_bookings_produce_two_alerts(db_session, customer_user, vehicle, branch, vehicle_factory):
    other = vehicle_factory(model="Camry", availability=AvailabilityStatus.available)
    before = len(_alerts(db_session, customer_user))

    _book_test_drive(db_session, customer_user, vehicle, branch, days_ahead=3)
    _book_test_drive(db_session, customer_user, other, branch, days_ahead=4)

    assert len(_alerts(db_session, customer_user)) == before + 2


# ── Service appointment ──────────────────────────────────────────────────


def test_booking_a_service_notifies_the_customer(
    client, customer_headers, customer_user, db_session, branch, owned_vehicle_factory
):
    """Same silence, other domain: the confirmation only fired for staff."""
    car = owned_vehicle_factory()
    before = len(_alerts(db_session, customer_user))

    res = client.post(
        f"{SERVICE}/appointments",
        headers=customer_headers,
        json={
            "ownedVehicleId": car.id,
            "branchId": branch.id,
            "serviceType": "periodic",
            "scheduledAt": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "issueDescription": "Routine service, no faults reported.",
            "mileageAtBooking": 31000,
        },
    )

    assert res.status_code in (200, 201), res.text
    assert len(_alerts(db_session, customer_user)) == before + 1, (
        "booking a service sent the customer nothing"
    )


def test_the_service_alert_does_not_claim_to_be_confirmed(
    client, customer_headers, customer_user, db_session, branch, owned_vehicle_factory
):
    car = owned_vehicle_factory()

    client.post(
        f"{SERVICE}/appointments",
        headers=customer_headers,
        json={
            "ownedVehicleId": car.id,
            "branchId": branch.id,
            "serviceType": "periodic",
            "scheduledAt": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "issueDescription": "Routine service, no faults reported.",
            "mileageAtBooking": 31000,
        },
    )

    row = _alerts(db_session, customer_user)[0]
    text = f"{row.title} {row.body}"
    assert "confirmed" not in text.lower(), text
    assert "{" not in text, f"unrendered placeholder: {text}"
