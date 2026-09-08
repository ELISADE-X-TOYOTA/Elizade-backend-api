"""A test drive nobody could confirm, cancel or complete.

`/sales` exposed list and create, both for the customer. There was NO staff
endpoint for test drives of any kind, so a booking was written as `requested`
and nothing in the system could ever move it — the customer's own screen
worked around this by showing the linked LEAD's stage instead of the booking's
own status.

It is also why `TEST_DRIVE_CONFIRMED` and `TEST_DRIVE_CANCELLED` had never
fired once. Both were written, catalogued and wired to three channels, and no
action existed that could reach them.

And customers could not call one off: service appointments have had cancel and
reschedule since they were built, test drives had neither, so someone who
could no longer make it had no way to say so and the branch kept the slot held.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.notifications.models import UserNotification
from app.domains.sales.models import TestDriveBooking
from app.domains.shared.enums import AvailabilityStatus, TestDriveStatus

SALES = "/api/v1/sales"


@pytest.fixture
def vehicle(vehicle_factory):
    return vehicle_factory(
        make="Toyota", model="Corolla", year=2024, availability=AvailabilityStatus.available
    )


@pytest.fixture
def booking(client, customer_headers, vehicle, branch, db_session):
    res = client.post(
        f"{SALES}/test-drives",
        headers=customer_headers,
        json={
            "vehicleId": vehicle.id,
            "branchId": branch.id,
            "scheduledAt": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _alerts(db_session, user, contains: str | None = None):
    rows = (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .all()
    )
    if contains is None:
        return rows
    return [r for r in rows if contains.lower() in f"{r.title} {r.body}".lower()]


def _status(db_session, booking_id) -> TestDriveStatus:
    db_session.expire_all()
    return db_session.get(TestDriveBooking, booking_id).status


# ── Staff transitions ────────────────────────────────────────────────────


def test_staff_can_confirm_a_test_drive(client, staff_headers, booking, db_session):
    """THE MISSING ACTION. Nothing could move a booking off `requested`."""
    res = client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "confirm"},
    )

    assert res.status_code == 200, res.text
    assert _status(db_session, booking["id"]) is TestDriveStatus.confirmed


def test_confirming_notifies_the_customer(client, staff_headers, booking, customer_user, db_session):
    """`TEST_DRIVE_CONFIRMED` had never been sent, for want of a trigger."""
    before = len(_alerts(db_session, customer_user, "confirmed"))

    client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "confirm"},
    )

    after = _alerts(db_session, customer_user, "confirmed")
    assert len(after) == before + 1, "confirming a test drive told the customer nothing"
    assert "{" not in after[-1].body, f"unrendered placeholder: {after[-1].body}"


def test_staff_can_cancel_and_the_customer_is_told(
    client, staff_headers, booking, customer_user, db_session
):
    before = len(_alerts(db_session, customer_user, "cancelled"))

    res = client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "cancel"},
    )

    assert res.status_code == 200, res.text
    assert _status(db_session, booking["id"]) is TestDriveStatus.cancelled
    assert len(_alerts(db_session, customer_user, "cancelled")) == before + 1


def test_completing_does_not_notify(client, staff_headers, booking, customer_user, db_session):
    """They were there. Telling someone their test drive happened is noise."""
    before = len(_alerts(db_session, customer_user))

    client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "complete"},
    )

    assert _status(db_session, booking["id"]) is TestDriveStatus.completed
    assert len(_alerts(db_session, customer_user)) == before


def test_a_finished_booking_cannot_be_reopened(client, staff_headers, booking):
    """Reopening one would resurrect a slot the branch has given away."""
    client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "cancel"},
    )

    again = client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "confirm"},
    )
    assert again.status_code == 409, again.text


def test_an_unknown_action_is_refused(client, staff_headers, booking):
    res = client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=staff_headers,
        json={"action": "reschedule"},
    )
    assert res.status_code == 422


def test_a_customer_cannot_drive_the_staff_endpoint(client, customer_headers, booking):
    res = client.patch(
        f"{SALES}/test-drives/{booking['id']}/status",
        headers=customer_headers,
        json={"action": "confirm"},
    )
    assert res.status_code in (401, 403), res.text


# ── Customer cancellation ────────────────────────────────────────────────


def test_a_customer_can_call_off_their_own_test_drive(
    client, customer_headers, booking, db_session
):
    res = client.post(f"{SALES}/test-drives/{booking['id']}/cancel", headers=customer_headers)

    assert res.status_code == 200, res.text
    assert _status(db_session, booking["id"]) is TestDriveStatus.cancelled


def test_cancelling_twice_is_refused(client, customer_headers, booking):
    client.post(f"{SALES}/test-drives/{booking['id']}/cancel", headers=customer_headers)
    again = client.post(f"{SALES}/test-drives/{booking['id']}/cancel", headers=customer_headers)
    assert again.status_code == 409


def test_one_customer_cannot_cancel_anothers_booking(
    client, booking, db_session, staff_headers
):
    """Answered as 404: whether someone else's booking exists is not this
    customer's business."""
    from app.core.security import create_access_token
    from app.domains.users.models import User, UserRole

    other = User(
        phone_normalized="2348109999111",
        phone_display="08109999111",
        email="other@elizade.test",
        first_name="Other",
        last_name="Customer",
        role=UserRole.customer,
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()

    res = client.post(
        f"{SALES}/test-drives/{booking['id']}/cancel",
        headers={"Authorization": f"Bearer {create_access_token(other.id)}"},
    )
    assert res.status_code == 404, res.text


def test_cancelling_a_booking_that_does_not_exist(client, customer_headers):
    res = client.post(
        f"{SALES}/test-drives/00000000-0000-0000-0000-000000000000/cancel",
        headers=customer_headers,
    )
    assert res.status_code == 404


def test_the_cancelled_booking_leaves_the_upcoming_list(client, customer_headers, booking):
    """The customer's own list must reflect it immediately."""
    client.post(f"{SALES}/test-drives/{booking['id']}/cancel", headers=customer_headers)

    listed = client.get(f"{SALES}/test-drives", headers=customer_headers).json()
    row = next(b for b in listed if b["id"] == booking["id"])
    assert row["status"] == "cancelled"
