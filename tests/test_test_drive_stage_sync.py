"""A test drive's stage must follow the lead it created.

THE REPORTED BUG: a customer books a test drive, sales advance the enquiry
through the pipeline, and the app still says "Requested" — for ever.

The cause is that booking a test drive writes TWO rows. `TestDriveBooking`
carries a status that is set to `requested` at creation and is then never
touched by anything in this codebase; there is not even an admin endpoint for
bookings. Staff advance the `Lead`. The app was reading the booking.

These tests assert the payload reports the LEAD's stage, so what the customer
sees tracks what the business actually did.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.leads.models import Lead
from app.domains.leads.tracking import TrackingStage
from app.domains.sales.models import TestDriveBooking
from app.domains.sales.service import list_my_test_drives
from app.domains.shared.enums import LeadStatus, TestDriveStatus


@pytest.fixture
def booking(db_session, customer_user, vehicle_factory, branch):
    """A booking and the lead it created, as `book_test_drive` makes them."""
    vehicle = vehicle_factory()
    lead = Lead(
        customer_id=customer_user.id,
        customer_name="Tunde Bello",
        email=customer_user.email,
        phone=customer_user.phone_display,
        source="Mobile app",
        status=LeadStatus.new,
        interested_model=f"{vehicle.year} {vehicle.make} {vehicle.model}",
    )
    db_session.add(lead)
    db_session.flush()

    row = TestDriveBooking(
        user_id=customer_user.id,
        vehicle_id=vehicle.id,
        branch_id=branch.id,
        lead_id=lead.id,
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
        status=TestDriveStatus.requested,
    )
    db_session.add(row)
    db_session.commit()
    return row, lead


def _only(db_session, user):
    rows = list_my_test_drives(db_session, user.id)
    assert len(rows) == 1
    return rows[0]


def test_a_new_booking_reports_the_first_stage(db_session, customer_user, booking):
    out = _only(db_session, customer_user)
    assert out.leadStage == TrackingStage.submitted.value
    assert out.leadStepIndex == 0
    assert out.leadStepCount and out.leadStepCount > 1


@pytest.mark.parametrize(
    "lead_status,expected",
    [
        (LeadStatus.contacted, TrackingStage.under_review),
        (LeadStatus.qualified, TrackingStage.under_review),
        (LeadStatus.proposal, TrackingStage.in_progress),
        (LeadStatus.negotiation, TrackingStage.in_progress),
        (LeadStatus.won, TrackingStage.converted),
        (LeadStatus.lost, TrackingStage.closed),
    ],
)
def test_advancing_the_lead_moves_the_customer_stage(
    db_session, customer_user, booking, lead_status, expected
):
    """The whole bug, one row per pipeline step."""
    _, lead = booking
    lead.status = lead_status
    db_session.commit()

    out = _only(db_session, customer_user)
    assert out.leadStage == expected.value, (
        f"lead moved to {lead_status.value} but the customer still sees "
        f"{out.leadStage}"
    )


def test_the_booking_status_itself_never_moves(db_session, customer_user, booking):
    """Documents WHY the bug existed, so nobody 'fixes' it by reading `status`.

    Nothing advances this column. Anything showing it to a customer is showing
    a value frozen at creation.
    """
    _, lead = booking
    lead.status = LeadStatus.won
    db_session.commit()

    out = _only(db_session, customer_user)
    assert out.status == TestDriveStatus.requested.value, "unchanged, as expected"
    assert out.leadStage == TrackingStage.converted.value, "the live one moved"


def test_a_booking_with_no_lead_reports_no_stage(
    db_session, customer_user, vehicle_factory, branch
):
    """Rows predating lead linking must not crash the list."""
    row = TestDriveBooking(
        user_id=customer_user.id,
        vehicle_id=vehicle_factory().id,
        branch_id=branch.id,
        lead_id=None,
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        status=TestDriveStatus.requested,
    )
    db_session.add(row)
    db_session.commit()

    out = _only(db_session, customer_user)
    assert out.leadStage is None
    assert out.leadStepIndex is None


def test_the_lead_id_is_exposed_so_the_card_can_open_the_tracker(
    db_session, customer_user, booking
):
    """The app routes to /lead/{id}, which already renders the full tracker."""
    _, lead = booking
    assert _only(db_session, customer_user).leadId == lead.id
