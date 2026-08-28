import io
from datetime import datetime, timedelta, timezone

from app.domains.shared.enums import AppointmentStatus


CUSTOMER_SERVICE = "/api/v1/service"
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _future_slot(days: int = 1) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def test_booking_persists_attachment_urls(client, customer_headers, owned_vehicle_factory, branch):
    response = client.post(
        f"{CUSTOMER_SERVICE}/appointments",
        headers=customer_headers,
        json={
            "ownedVehicleId": owned_vehicle_factory().id,
            "branchId": branch.id,
            "serviceType": "periodic",
            "scheduledAt": _future_slot().isoformat(),
            "mileageAtBooking": 15000,
            "issueDescription": "Please inspect the warning light",
            "attachmentUrls": ["/media/documents/inspection.png"],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["attachmentUrls"] == ["/media/documents/inspection.png"]


def test_customer_can_reschedule_own_future_appointment(
    client, customer_headers, appointment_factory
):
    appointment = appointment_factory(status=AppointmentStatus.requested, scheduled_at=_future_slot())
    new_slot = _future_slot(2)

    response = client.patch(
        f"{CUSTOMER_SERVICE}/appointments/{appointment.id}/reschedule",
        headers=customer_headers,
        json={"scheduledAt": new_slot.isoformat()},
    )

    assert response.status_code == 200, response.text
    assert response.json()["scheduledAt"].startswith(new_slot.isoformat()[:19])


def test_reschedule_rejects_past_time_and_conflicting_slot(
    client, customer_headers, appointment_factory, owned_vehicle_factory
):
    vehicle = owned_vehicle_factory()
    first = appointment_factory(
        owned_vehicle=vehicle, status=AppointmentStatus.confirmed, scheduled_at=_future_slot()
    )
    second_slot = _future_slot(2)
    appointment_factory(
        owned_vehicle=vehicle, status=AppointmentStatus.confirmed, scheduled_at=second_slot
    )

    past = client.patch(
        f"{CUSTOMER_SERVICE}/appointments/{first.id}/reschedule",
        headers=customer_headers,
        json={"scheduledAt": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
    )
    conflict = client.patch(
        f"{CUSTOMER_SERVICE}/appointments/{first.id}/reschedule",
        headers=customer_headers,
        json={"scheduledAt": second_slot.isoformat()},
    )

    assert past.status_code == 400
    assert conflict.status_code == 409


def test_customer_cannot_change_another_customers_appointment(
    client, customer_headers, appointment_factory, db_session
):
    from tests.conftest import _make_user
    from app.domains.users.models import UserRole

    other = _make_user(
        db_session,
        role=UserRole.customer,
        phone="8099988777",
        email="appointment.other@test.com",
        first="Other",
        last="Customer",
    )
    appointment = appointment_factory(user_id=other.id, status=AppointmentStatus.confirmed)

    response = client.post(
        f"{CUSTOMER_SERVICE}/appointments/{appointment.id}/cancel",
        headers=customer_headers,
    )

    assert response.status_code == 404


def test_customer_cancel_requires_changeable_status(client, customer_headers, appointment_factory):
    appointment = appointment_factory(status=AppointmentStatus.in_progress)

    response = client.post(
        f"{CUSTOMER_SERVICE}/appointments/{appointment.id}/cancel",
        headers=customer_headers,
    )

    assert response.status_code == 409


def test_customer_can_cancel_own_requested_appointment(client, customer_headers, appointment_factory):
    appointment = appointment_factory(status=AppointmentStatus.requested)

    response = client.post(
        f"{CUSTOMER_SERVICE}/appointments/{appointment.id}/cancel",
        headers=customer_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


def test_service_attachment_upload_uses_document_storage(client, customer_headers):
    response = client.post(
        f"{CUSTOMER_SERVICE}/attachments/upload",
        headers=customer_headers,
        files={"file": ("inspection.png", io.BytesIO(PNG_BYTES), "image/png")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("/media/documents/")
