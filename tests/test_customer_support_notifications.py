"""Customer Support & Notifications — isolation, bulk read, and business rules.

These cover the parts of the customer-facing Support and Notification contracts
that the existing suites leave open:

  * `POST /notifications/read-all` had no coverage at all.
  * Cross-customer ticket access had none either. That one matters most — the
    endpoints scope every query by `user_id`, but nothing asserted it, so a
    refactor that dropped the filter would have shipped green while exposing
    one customer's support thread to another.
  * The reply/rate state machine (409 on a closed ticket, 400 before
    resolution, 422 outside 1–5) was likewise unasserted.
"""

import pytest

from app.core.security import create_access_token
from app.domains.notifications.models import UserNotification
from app.domains.shared.enums import NotificationCategory
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

SUPPORT = "/api/v1/support/tickets"
NOTIFS = "/api/v1/notifications"


@pytest.fixture
def other_customer(db_session) -> User:
    """A second, unrelated customer — the one who must never see the first's data."""
    user = User(
        phone_normalized="8100000009",
        phone_display="08100000009",
        first_name="Ngozi",
        last_name="Okafor",
        email="other.customer@elizade.test",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_customer_headers(other_customer) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_customer.id)}"}


def _open_ticket(client, headers, subject="Air conditioning fault") -> str:
    res = client.post(
        SUPPORT,
        headers=headers,
        json={
            "category": "service",
            "subject": subject,
            "body": "The AC stopped cooling two days after the last service.",
            "priority": "medium",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _unread(db_session, user_id: str, title: str) -> UserNotification:
    n = UserNotification(
        user_id=user_id,
        title=title,
        body="body",
        category=NotificationCategory.system,
        is_read=False,
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    return n


# ── Support: one customer must never reach another's ticket ──────────────


def test_ticket_detail_is_scoped_to_owner(client, customer_headers, other_customer_headers):
    ticket_id = _open_ticket(client, customer_headers)

    # 404 rather than 403 on purpose: a 403 would confirm the id exists.
    assert client.get(f"{SUPPORT}/{ticket_id}", headers=other_customer_headers).status_code == 404
    assert client.get(f"{SUPPORT}/{ticket_id}", headers=customer_headers).status_code == 200


def test_ticket_list_never_leaks_across_customers(client, customer_headers, other_customer_headers):
    ticket_id = _open_ticket(client, customer_headers)

    theirs = client.get(SUPPORT, headers=other_customer_headers)
    assert theirs.status_code == 200
    assert all(t["id"] != ticket_id for t in theirs.json())


def test_non_owner_cannot_reply_or_rate(client, customer_headers, other_customer_headers):
    ticket_id = _open_ticket(client, customer_headers)

    assert (
        client.post(
            f"{SUPPORT}/{ticket_id}/messages",
            headers=other_customer_headers,
            json={"body": "Injecting a message into someone else's thread."},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{SUPPORT}/{ticket_id}/rate",
            headers=other_customer_headers,
            json={"rating": 1},
        ).status_code
        == 404
    )


# ── Support: reply / rate state machine ──────────────────────────────────


def test_rating_before_resolution_is_rejected(client, customer_headers):
    ticket_id = _open_ticket(client, customer_headers)
    res = client.post(f"{SUPPORT}/{ticket_id}/rate", headers=customer_headers, json={"rating": 5})
    assert res.status_code == 400


@pytest.mark.parametrize("rating", [0, 6, -1, 99])
def test_rating_outside_one_to_five_is_rejected(
    client, customer_headers, staff_headers, rating
):
    ticket_id = _open_ticket(client, customer_headers)
    client.post(f"/api/v1/admin/support/tickets/{ticket_id}/resolve", headers=staff_headers)

    res = client.post(f"{SUPPORT}/{ticket_id}/rate", headers=customer_headers, json={"rating": rating})
    assert res.status_code == 422


def test_replying_to_a_resolved_ticket_is_rejected(client, customer_headers, staff_headers):
    ticket_id = _open_ticket(client, customer_headers)
    client.post(f"/api/v1/admin/support/tickets/{ticket_id}/resolve", headers=staff_headers)

    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "One more thing…"},
    )
    assert res.status_code == 409


# ── Notifications: read-all ──────────────────────────────────────────────


def test_read_all_marks_every_unread_and_reports_the_count(
    client, customer_headers, customer_user, db_session
):
    for i in range(3):
        _unread(db_session, customer_user.id, f"Notice {i}")

    assert len(client.get(f"{NOTIFS}?unreadOnly=true", headers=customer_headers).json()) == 3

    res = client.post(f"{NOTIFS}/read-all", headers=customer_headers)
    assert res.status_code == 200
    assert res.json()["updated"] == 3

    assert client.get(f"{NOTIFS}?unreadOnly=true", headers=customer_headers).json() == []
    # The notifications still exist — read-all marks, it does not delete.
    assert len(client.get(NOTIFS, headers=customer_headers).json()) == 3


def test_read_all_is_idempotent(client, customer_headers, customer_user, db_session):
    _unread(db_session, customer_user.id, "Only one")

    assert client.post(f"{NOTIFS}/read-all", headers=customer_headers).json()["updated"] == 1
    # Nothing left to mark — must report 0, not re-count or error.
    assert client.post(f"{NOTIFS}/read-all", headers=customer_headers).json()["updated"] == 0


def test_read_all_only_touches_the_calling_user(
    client, customer_headers, customer_user, other_customer, other_customer_headers, db_session
):
    _unread(db_session, customer_user.id, "Mine")
    _unread(db_session, other_customer.id, "Theirs")

    assert client.post(f"{NOTIFS}/read-all", headers=customer_headers).json()["updated"] == 1

    # The other customer's feed must be untouched.
    still_unread = client.get(f"{NOTIFS}?unreadOnly=true", headers=other_customer_headers).json()
    assert len(still_unread) == 1
    assert still_unread[0]["title"] == "Theirs"


def test_read_all_requires_authentication(client):
    assert client.post(f"{NOTIFS}/read-all").status_code == 401


def test_read_all_rejects_staff(client, staff_headers):
    assert client.post(f"{NOTIFS}/read-all", headers=staff_headers).status_code == 403
