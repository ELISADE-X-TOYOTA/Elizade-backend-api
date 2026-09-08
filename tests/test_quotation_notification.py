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
from app.domains.sales.models import Quotation
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


# ── The email has to BE the quotation ────────────────────────────────
#
# The notification fired, and the mail it sent was the catalog nudge: "We've
# prepared your quote for the 2024 RAV4. It's valid until 21 September 2026."
# No price, no breakdown, no total. A customer who opened it still had no
# quotation, having been told on screen that a formal one was coming — which
# reads as "no mail received" all over again, one step later.


@pytest.fixture
def outbox(monkeypatch):
    """Capture what would actually leave the building."""
    sent: list[dict] = []

    from app.domains.notifications import notify as notify_module

    def capture(*, to_email, subject, body, category, html_body=None):
        sent.append(
            {
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "category": category,
                "html_body": html_body,
            }
        )

    monkeypatch.setattr(notify_module.email_service, "send_notification", capture)
    return sent


def test_an_email_is_actually_dispatched(db_session, customer_user, vehicle, outbox):
    _request(db_session, customer_user, vehicle)
    assert len(outbox) == 1, f"expected one quotation email, got {len(outbox)}"
    assert outbox[0]["to_email"] == customer_user.email


def test_the_email_contains_the_price(db_session, customer_user, vehicle, outbox):
    """THE CORE OF IT. A quote without figures is not a quote."""
    _request(db_session, customer_user, vehicle)
    text = outbox[0]["body"]

    assert "48,500,000" in text, f"the total is missing from the email:\n{text}"


def test_the_email_contains_the_vehicle_and_validity(db_session, customer_user, vehicle, outbox):
    _request(db_session, customer_user, vehicle)
    text = outbox[0]["body"]

    assert "RAV4" in text, text
    assert "2024" in text, text
    # The catalog renders the date as "21 September 2026"; the year is enough
    # to prove a real date reached the customer rather than a placeholder.
    assert "20" in text and "{" not in text, text


def test_the_email_carries_a_quotable_reference(db_session, customer_user, vehicle, outbox):
    """A customer ringing the sales desk needs something to quote."""
    quote = _request(db_session, customer_user, vehicle)
    text = outbox[0]["body"]

    expected = sales_service._quotation_reference(quote.id)
    assert expected in text, f"reference {expected} missing from:\n{text}"


def test_the_email_has_an_html_part(db_session, customer_user, vehicle, outbox):
    """Plain text alone renders as a wall of text next to the branded OTP mail."""
    _request(db_session, customer_user, vehicle)
    html = outbox[0]["html_body"]

    assert html, "no HTML alternative was attached"
    assert "48,500,000" in html
    assert "{" not in html.split("<style")[0], "unrendered placeholder in the HTML head"


def test_the_line_items_appear_individually(db_session, customer_user, vehicle, outbox):
    _request(db_session, customer_user, vehicle)
    text = outbox[0]["body"]
    row = db_session.query(Quotation).filter(Quotation.user_id == customer_user.id).one()

    for item in row.line_items:
        assert item.description in text, f"line item {item.description!r} missing from the email"


def test_the_subject_still_comes_from_the_catalog(db_session, customer_user, vehicle, outbox):
    """Only the BODY is overridden — event copy stays in one place."""
    from app.domains.notifications import catalog

    _request(db_session, customer_user, vehicle)
    assert outbox[0]["subject"] == catalog.QUOTATION_ISSUED.title


def test_the_in_app_notification_stays_short(db_session, customer_user, vehicle, outbox):
    """The document belongs in the email. A full quote in the notification
    tray would be unreadable."""
    _request(db_session, customer_user, vehicle)
    row = _notifications(db_session, customer_user)[-1]

    assert "48,500,000" not in row.body, "the in-app notification should nudge, not itemise"
    assert len(row.body) < 200, row.body


def test_a_delivery_row_records_the_email(db_session, customer_user, vehicle, outbox):
    """The row that would have answered 'was it sent?' without guessing.

    Production had zero of these for this event, which is how the silence was
    diagnosable at all.
    """
    from app.domains.notifications.models import NotificationDelivery

    _request(db_session, customer_user, vehicle)
    rows = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.user_id == customer_user.id,
            NotificationDelivery.event_key == "sales.quotation_issued",
            NotificationDelivery.channel == "email",
        )
        .all()
    )
    assert len(rows) == 1, "no delivery row was written for the quotation email"
    assert rows[0].status == "sent", rows[0].error


def test_the_quote_survives_an_email_failure(db_session, customer_user, vehicle, monkeypatch):
    """Building a richer email must not have made it a way to lose the quote."""
    from app.domains.notifications import notify as notify_module

    def boom(**kw):
        raise RuntimeError("postmark down")

    monkeypatch.setattr(notify_module.email_service, "send_notification", boom)

    quote = _request(db_session, customer_user, vehicle)

    assert quote.id
    assert db_session.query(Quotation).filter(Quotation.id == quote.id).count() == 1
