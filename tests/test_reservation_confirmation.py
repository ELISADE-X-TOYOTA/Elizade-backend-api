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


def test_the_receipt_ignores_the_sales_opt_out(db_session, customer_user, vehicle, outbox):
    """"We have emailed you the details" has to be true for everyone.

    The 12 September tester who lost four quotations to their sales opt-out
    lost their reservation receipt the same way — the one carrying the
    reference they would quote at the branch. A hold on a car is not a sales
    notification the customer can be said to have declined.
    """
    from app.domains.notifications.models import NotificationPreference
    from app.domains.shared.enums import NotificationCategory

    db_session.add(NotificationPreference(
        user_id=customer_user.id, category=NotificationCategory.sales, channel="email", enabled=False,
    ))
    db_session.commit()

    _reserve(db_session, customer_user, vehicle)
    assert len(outbox) == 1, "the reservation receipt was suppressed by a sales preference"


# ── Releasing a hold ─────────────────────────────────────────────────────
#
# A reservation could be created and then only ended by the seven-day
# timeout, so a customer who changed their mind kept a car off the showroom
# for a week with no way to say otherwise.

from datetime import datetime, timedelta, timezone

from app.domains.inventory.models import Vehicle
from app.domains.sales.models import Reservation
from app.domains.shared.enums import AvailabilityStatus, LeadStatus, ReservationStatus

SALES = "/api/v1/sales"


def _reserve_via_api(client, headers, vehicle):
    res = client.post(
        f"{SALES}/reservations",
        headers=headers,
        json={"vehicleId": vehicle.id, "depositAmount": "2000000"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_cancelling_releases_the_vehicle(client, customer_headers, vehicle, db_session):
    row = _reserve_via_api(client, customer_headers, vehicle)
    db_session.expire_all()
    assert db_session.get(Vehicle, vehicle.id).availability is AvailabilityStatus.reserved

    res = client.post(f"{SALES}/reservations/{row['id']}/cancel", headers=customer_headers)
    assert res.status_code == 200, res.text

    db_session.expire_all()
    assert db_session.get(Reservation, row["id"]).status is ReservationStatus.cancelled
    assert db_session.get(Vehicle, vehicle.id).availability is AvailabilityStatus.available, (
        "the car must go back on sale, or cancelling is worse than doing nothing"
    )


def test_cancelling_closes_the_lead(client, customer_headers, vehicle, db_session):
    from app.domains.leads.models import Lead

    row = _reserve_via_api(client, customer_headers, vehicle)
    client.post(f"{SALES}/reservations/{row['id']}/cancel", headers=customer_headers)

    db_session.expire_all()
    lead_id = db_session.get(Reservation, row["id"]).lead_id
    assert db_session.get(Lead, lead_id).status is LeadStatus.lost


def test_cancelling_tells_the_customer(client, customer_headers, vehicle, outbox):
    row = _reserve_via_api(client, customer_headers, vehicle)
    before = len(outbox)
    client.post(f"{SALES}/reservations/{row['id']}/cancel", headers=customer_headers)
    assert len(outbox) == before + 1, "releasing a hold on a car worth millions must be acknowledged"


def test_a_reservation_that_is_not_yours_is_a_404(client, customer_headers):
    """Not a 403 — whether it exists is not this customer's business.

    (Staff get 403 before reaching this code at all: the route is
    customer-only, and the role gate answers first.)
    """
    import uuid

    res = client.post(
        f"{SALES}/reservations/{uuid.uuid4()}/cancel", headers=customer_headers
    )
    assert res.status_code == 404


def test_cancelling_twice_is_refused(client, customer_headers, vehicle):
    row = _reserve_via_api(client, customer_headers, vehicle)
    assert client.post(f"{SALES}/reservations/{row['id']}/cancel", headers=customer_headers).status_code == 200
    second = client.post(f"{SALES}/reservations/{row['id']}/cancel", headers=customer_headers)
    assert second.status_code == 409


def test_a_paid_hold_is_not_a_button(client, customer_headers, vehicle, db_session):
    """Money taken is a refund conversation with the branch, not a tap."""
    row = _reserve_via_api(client, customer_headers, vehicle)
    db_session.expire_all()
    held = db_session.get(Reservation, row["id"])
    held.status = ReservationStatus.deposit_paid
    db_session.commit()

    res = client.post(f"{SALES}/reservations/{row['id']}/cancel", headers=customer_headers)
    assert res.status_code == 409
    assert "branch" in res.json()["detail"].lower()


def test_a_second_hold_keeps_the_car_off_the_market(client, customer_headers, staff_headers, vehicle, db_session, staff_user):
    """One hold lapsing must not release a car another still holds."""
    mine = _reserve_via_api(client, customer_headers, vehicle)

    other = Reservation(
        user_id=staff_user.id,
        vehicle_id=vehicle.id,
        status=ReservationStatus.confirmed,
        deposit_amount=0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(other)
    db_session.commit()

    client.post(f"{SALES}/reservations/{mine['id']}/cancel", headers=customer_headers)
    db_session.expire_all()
    assert db_session.get(Vehicle, vehicle.id).availability is AvailabilityStatus.reserved
