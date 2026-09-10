"""Reserving a vehicle told the customer nothing.

The app's success sheet said "A confirmation has been sent to your email".
Nothing was sent: there was no reservation event in the notification catalogue
at all — no failing worker, no template, no call. A customer was told a receipt
existed for a hold on a car worth millions of naira, and nothing arrived.

The same sheet printed "Deposit Paid" beside an amount nobody had paid, which
is the mistake this email must not repeat: the hold is real, the payment is not.
"""

from decimal import Decimal

import pytest

from app.domains.notifications.models import UserNotification
from app.domains.sales.models import Reservation
from app.domains.sales import service as sales_service
from app.domains.sales.schemas import ReservationCreateIn
from app.domains.shared.enums import AvailabilityStatus

SALES = "/api/v1/sales"


@pytest.fixture
def vehicle(vehicle_factory, branch):
    return vehicle_factory(
        make="Toyota", model="Sienna", year=2025,
        price=Decimal("40000000.00"), availability=AvailabilityStatus.available,
    )


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []
    from app.domains.notifications import notify as notify_module

    def capture(*, to_email, subject, body, category, html_body=None):
        sent.append({"to_email": to_email, "subject": subject, "body": body,
                     "category": category, "html_body": html_body})

    monkeypatch.setattr(notify_module.email_service, "send_notification", capture)
    return sent


def _reserve(db_session, user, vehicle, deposit="2000000"):
    return sales_service.create_reservation(
        db_session, user, ReservationCreateIn(vehicleId=vehicle.id, depositAmount=deposit)
    )


def _alerts(db_session, user):
    db_session.flush()
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .order_by(UserNotification.created_at.desc())
        .all()
    )


def test_reserving_notifies_the_customer(db_session, customer_user, vehicle):
    """THE REPORTED DEFECT."""
    before = len(_alerts(db_session, customer_user))
    _reserve(db_session, customer_user, vehicle)
    assert len(_alerts(db_session, customer_user)) == before + 1


def test_an_email_actually_goes_out(db_session, customer_user, vehicle, outbox):
    _reserve(db_session, customer_user, vehicle)
    assert len(outbox) == 1, f"expected one reservation email, got {len(outbox)}"
    assert outbox[0]["to_email"] == customer_user.email


def test_the_email_carries_the_hold_details(db_session, customer_user, vehicle, outbox):
    _reserve(db_session, customer_user, vehicle)
    text = outbox[0]["body"]

    assert "Sienna" in text, text
    assert "{" not in text, f"unrendered placeholder: {text}"
    assert "2,000,000" in text, "the deposit figure is missing"


def test_the_email_does_not_claim_the_deposit_was_paid(db_session, customer_user, vehicle, outbox):
    """THE ONE THAT MATTERS. No payment is taken at this point.

    The app printed "Deposit Paid" beside an amount nobody had paid; a receipt
    repeating that would be worse, because a receipt is what people keep.
    """
    _reserve(db_session, customer_user, vehicle)
    text = outbox[0]["body"].lower()

    assert "no payment has been taken" in text, outbox[0]["body"]
    assert "deposit paid" not in text, outbox[0]["body"]
    assert "deposit to pay" in text


def test_a_reservation_with_no_deposit_says_so(db_session, customer_user, vehicle, outbox):
    _reserve(db_session, customer_user, vehicle, deposit="0")
    text = outbox[0]["body"].lower()

    assert "no deposit has been taken" in text, outbox[0]["body"]
    assert "deposit to pay" not in text


def test_the_email_carries_a_quotable_reference(db_session, customer_user, vehicle, outbox):
    reservation = _reserve(db_session, customer_user, vehicle)
    expected = sales_service._reservation_reference(reservation.id)
    assert expected in outbox[0]["body"], outbox[0]["body"]


def test_the_email_has_an_html_part(db_session, customer_user, vehicle, outbox):
    _reserve(db_session, customer_user, vehicle)
    html = outbox[0]["html_body"]

    assert html, "no HTML alternative was attached"
    assert "Sienna" in html
    assert "{" not in html.split("<style")[0], "unrendered placeholder in the HTML head"


def test_the_hold_survives_a_mail_failure(db_session, customer_user, vehicle, monkeypatch):
    """A reservation must not be lost because Postmark is down."""
    from app.domains.notifications import notify as notify_module

    def boom(**kw):
        raise RuntimeError("postmark down")

    monkeypatch.setattr(notify_module.email_service, "send_notification", boom)

    reservation = _reserve(db_session, customer_user, vehicle)

    assert reservation.id
    assert db_session.query(Reservation).filter(Reservation.id == reservation.id).count() == 1


def test_the_in_app_notification_stays_short(db_session, customer_user, vehicle, outbox):
    """The receipt belongs in the email, not the notification tray."""
    _reserve(db_session, customer_user, vehicle)
    row = _alerts(db_session, customer_user)[0]

    assert "2,000,000" not in row.body
    assert len(row.body) < 200, row.body
