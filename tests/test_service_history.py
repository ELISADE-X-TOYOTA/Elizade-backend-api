"""
Phase 4 — service history:
    GET    /api/v1/admin/service/history
    POST   /api/v1/admin/service/history
    DELETE /api/v1/admin/service/history/{id}
"""

from app.domains.shared.enums import AppointmentStatus
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

URL = "/api/v1/admin/service/history"
APPT_URL = "/api/v1/admin/service/appointments"


def _entry(vehicle, branch, **overrides) -> dict:
    body = {
        "ownedVehicleId": vehicle.id,
        "branchId": branch.id,
        "serviceType": "Periodic maintenance",
        "performedAt": "2026-01-15T10:00:00+00:00",
        "mileage": 20000,
        "description": "Oil change and inspection",
        "cost": 35000,
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# List                                                                         #
# --------------------------------------------------------------------------- #

def test_list_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_list_rejects_customer(client, customer_headers):
    assert client.get(URL, headers=customer_headers).status_code == 403


def test_list_empty(client, staff_headers):
    body = client.get(URL, headers=staff_headers).json()
    assert body == {"items": [], "total": 0, "page": 1, "size": 20, "pages": 1}


def test_list_after_create(client, staff_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    client.post(URL, json=_entry(vehicle, branch), headers=staff_headers)
    body = client.get(URL, headers=staff_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["serviceType"] == "Periodic maintenance"
    assert body["items"][0]["customerName"] == "Tunde Bello"


def test_list_filter_by_vehicle(client, staff_headers, owned_vehicle_factory, branch):
    v1 = owned_vehicle_factory(registration_number="AAA-111")
    v2 = owned_vehicle_factory(registration_number="BBB-222")
    client.post(URL, json=_entry(v1, branch), headers=staff_headers)
    client.post(URL, json=_entry(v2, branch), headers=staff_headers)
    body = client.get(URL, params={"vehicleId": v2.id}, headers=staff_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["ownedVehicleId"] == v2.id


def test_list_filter_by_customer(client, staff_headers, owned_vehicle_factory, branch, db_session):
    other = User(
        phone_normalized="8100000099",
        phone_display="08100000099",
        first_name="Bola",
        last_name="Ade",
        email="bola@elizade.test",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    mine = owned_vehicle_factory()
    theirs = owned_vehicle_factory(owner=other)
    client.post(URL, json=_entry(mine, branch), headers=staff_headers)
    client.post(URL, json=_entry(theirs, branch), headers=staff_headers)

    body = client.get(URL, params={"customerId": other.id}, headers=staff_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["customerId"] == other.id


# --------------------------------------------------------------------------- #
# Create (manual)                                                              #
# --------------------------------------------------------------------------- #

def test_create_ok(client, staff_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    resp = client.post(URL, json=_entry(vehicle, branch), headers=staff_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["ownedVehicleId"] == vehicle.id
    assert body["appointmentId"] is None
    assert body["cost"] == "35000.00"
    assert body["branchName"] == "Elizade Lekki"


def test_create_invalid_vehicle(client, staff_headers, branch):
    resp = client.post(
        URL,
        json=_entry(type("V", (), {"id": "00000000-0000-0000-0000-000000000000"}), branch),
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_create_invalid_branch(client, staff_headers, owned_vehicle_factory):
    vehicle = owned_vehicle_factory()
    resp = client.post(
        URL,
        json=_entry(vehicle, type("B", (), {"id": "00000000-0000-0000-0000-000000000000"})),
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_create_negative_cost_rejected(client, staff_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    resp = client.post(URL, json=_entry(vehicle, branch, cost=-5), headers=staff_headers)
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Delete (admin)                                                               #
# --------------------------------------------------------------------------- #

def test_delete_rejects_staff(client, staff_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    hist_id = client.post(URL, json=_entry(vehicle, branch), headers=staff_headers).json()["id"]
    assert client.delete(f"{URL}/{hist_id}", headers=staff_headers).status_code == 403


def test_delete_ok(client, staff_headers, admin_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    hist_id = client.post(URL, json=_entry(vehicle, branch), headers=staff_headers).json()["id"]
    assert client.delete(f"{URL}/{hist_id}", headers=admin_headers).status_code == 204
    assert client.get(URL, headers=staff_headers).json()["total"] == 0


def test_delete_not_found(client, admin_headers):
    resp = client.delete(f"{URL}/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Integration: completing a job writes history                                #
# --------------------------------------------------------------------------- #

def test_completing_appointment_appears_in_history(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    client.patch(f"{APPT_URL}/{appt.id}/status", json={"action": "start"}, headers=staff_headers)
    client.patch(f"{APPT_URL}/{appt.id}/status", json={"action": "complete"}, headers=staff_headers)

    body = client.get(URL, headers=staff_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["appointmentId"] == appt.id
