"""Requesting a quote must actually notify the customer.

THE REPORTED BUG: the app's success sheet says "A formal quotation ... will be
sent to your email and appear in Support shortly", the row was written with
`status=sent`, and nothing was sent. There was no failing worker and no queue
to repair — `sales.quotation_issued` sat in the notification catalog, with its
copy written and its channels declared, and no code path had ever fired it.

The load-bearing test here is the last one: a quote must survive a notification
failure. A customer would rather have a quote and no email than a 500 and
neither.
"""

from decimal import Decimal

import pytest

from app.domains.notifications.models import UserNotification
from app.domains.sales import service as sales_service
from app.domains.sales.schemas import QuotationRequestIn
from app.domains.shared.enums import AvailabilityStatus


@pytest.fixture
def vehicle(vehicle_factory):
    return vehicle_factory(
        make="Toyota", model="RAV4", year=2024,
        price=Decimal("48500000.00"), availability=AvailabilityStatus.available,
    )


def _request(db_session, user, vehicle, notes=None):
    return sales_service.request_quotation(
        db_session, user, QuotationRequestIn(vehicleId=vehicle.id, notes=notes)
    )


def _notifications(db_session, user):
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .all()
    )


def test_requesting_a_quote_notifies_the_customer(db_session, customer_user, vehicle):
    """The promise the app makes on screen."""
    before = len(_notifications(db_session, customer_user))
    _request(db_session, customer_user, vehicle)

    rows = _notifications(db_session, customer_user)
    assert len(rows) == before + 1, "no notification was created for the quote"


def test_the_notification_names_the_vehicle_and_expiry(db_session, customer_user, vehicle):
    """Copy with a literal '{vehicle_label}' in it would be worse than none.

    `notify` refuses to render on missing context, so this also proves the
    context keys match what the catalog entry requires.
    """
    _request(db_session, customer_user, vehicle)
    row = _notifications(db_session, customer_user)[-1]

    assert "RAV4" in row.body, row.body
    assert "{" not in row.body, f"unrendered placeholder in copy: {row.body}"
    assert row.title


def test_the_quote_still_exists_when_notification_fails(
    db_session, customer_user, vehicle, monkeypatch
):
    """THE ONE THAT MATTERS.

    Notification is a side effect. If Postmark is down, or the catalog entry
    is mis-keyed, the customer must still get their quote — not a 500 and no
    quote at all.
    """
    def boom(*a, **kw):
        raise RuntimeError("email provider unavailable")

    monkeypatch.setattr(sales_service, "safe_notify", boom, raising=True)

    with pytest.raises(RuntimeError):
        # `safe_notify` is what swallows failures; replacing it proves the
        # quote is committed BEFORE the notification is attempted.
        _request(db_session, customer_user, vehicle)

    from app.domains.sales.models import Quotation

    assert (
        db_session.query(Quotation).filter(Quotation.user_id == customer_user.id).count() == 1
    ), "the quotation must be committed before any notification is attempted"


def test_two_quotes_produce_two_notifications(db_session, customer_user, vehicle_factory):
    """Nothing dedupes or suppresses a genuine second request."""
    a = vehicle_factory(model="Corolla", availability=AvailabilityStatus.available)
    b = vehicle_factory(model="Camry", availability=AvailabilityStatus.available)
    _request(db_session, customer_user, a)
    _request(db_session, customer_user, b)

    bodies = " ".join(n.body for n in _notifications(db_session, customer_user))
    assert "Corolla" in bodies and "Camry" in bodies
