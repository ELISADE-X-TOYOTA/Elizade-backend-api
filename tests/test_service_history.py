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
    assert body["items"][0]["lines"] == []


# --------------------------------------------------------------------------- #
# Structured lines                                                             #
# --------------------------------------------------------------------------- #

ITEMS = "/api/v1/admin/service/items"
CUSTOMER_HISTORY = "/api/v1/service/history"


def _create_item(client, admin_headers, **overrides) -> dict:
    body = {
        "code": "engine-oil-filter",
        "name": "Engine oil and filter",
        "group": "periodic",
    }
    body.update(overrides)
    resp = client.post(ITEMS, json=body, headers=admin_headers)
    assert resp.status_code == 201
    return resp.json()


def test_create_with_lines(client, staff_headers, admin_headers, owned_vehicle_factory, branch):
    item = _create_item(client, admin_headers)
    vehicle = owned_vehicle_factory(mileage=15000)
    resp = client.post(
        URL,
        json=_entry(
            vehicle,
            branch,
            lines=[
                {
                    "serviceItemId": item["id"],
                    "operation": "serviced",
                    "quantity": 1,
                    "amount": 25000,
                    "notes": "5W-30",
                }
            ],
        ),
        headers=staff_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert line["serviceItemCode"] == "engine-oil-filter"
    assert line["operation"] == "serviced"
    assert line["quantity"] == 1
    assert line["amount"] == "25000.00"
    assert line["notes"] == "5W-30"
    assert line["source"] == "manual_entry"
    assert line["isBackfilled"] is False


def test_create_duplicate_item_rejected(client, staff_headers, admin_headers, owned_vehicle_factory, branch):
    item = _create_item(client, admin_headers)
    vehicle = owned_vehicle_factory()
    line = {"serviceItemId": item["id"], "operation": "inspected"}
    resp = client.post(
        URL,
        json=_entry(vehicle, branch, lines=[line, {**line, "operation": "replaced"}]),
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_create_unknown_item_rejected(client, staff_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    resp = client.post(
        URL,
        json=_entry(
            vehicle,
            branch,
            lines=[{"serviceItemId": "00000000-0000-0000-0000-000000000000", "operation": "serviced"}],
        ),
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_create_inactive_item_rejected(client, staff_headers, admin_headers, owned_vehicle_factory, branch):
    item = _create_item(client, admin_headers)
    client.patch(f"{ITEMS}/{item['id']}", json={"isActive": False}, headers=admin_headers)
    vehicle = owned_vehicle_factory()
    resp = client.post(
        URL,
        json=_entry(vehicle, branch, lines=[{"serviceItemId": item["id"], "operation": "serviced"}]),
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_create_invalid_operation_rejected(client, staff_headers, admin_headers, owned_vehicle_factory, branch):
    item = _create_item(client, admin_headers)
    vehicle = owned_vehicle_factory()
    resp = client.post(
        URL,
        json=_entry(vehicle, branch, lines=[{"serviceItemId": item["id"], "operation": "checked"}]),
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_get_history_detail(client, staff_headers, owned_vehicle_factory, branch):
    vehicle = owned_vehicle_factory()
    created = client.post(URL, json=_entry(vehicle, branch), headers=staff_headers).json()
    resp = client.get(f"{URL}/{created['id']}", headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert resp.json()["lines"] == []


def test_unmapped_filter(client, staff_headers, admin_headers, owned_vehicle_factory, branch):
    item = _create_item(client, admin_headers)
    mapped_vehicle = owned_vehicle_factory(registration_number="MAP-001")
    unmapped_vehicle = owned_vehicle_factory(registration_number="UNM-002", vin="JTDB1234567890002")
    client.post(
        URL,
        json=_entry(mapped_vehicle, branch, lines=[{"serviceItemId": item["id"], "operation": "replaced"}]),
        headers=staff_headers,
    )
    unmapped = client.post(URL, json=_entry(unmapped_vehicle, branch), headers=staff_headers).json()

    body = client.get(URL, params={"unmappedOnly": True}, headers=staff_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == unmapped["id"]
    assert body["items"][0]["lines"] == []


def test_replace_lines_and_raise_mileage(
    client, staff_headers, admin_headers, owned_vehicle_factory, branch, db_session
):
    oil = _create_item(client, admin_headers)
    pads = _create_item(client, admin_headers, code="brake-pads", name="Brake pads", group="chassis")
    vehicle = owned_vehicle_factory(mileage=20000)
    history_id = client.post(URL, json=_entry(vehicle, branch, mileage=20000), headers=staff_headers).json()["id"]

    resp = client.put(
        f"{URL}/{history_id}/lines",
        json={
            "mileage": 21500,
            "lines": [
                {"serviceItemId": oil["id"], "operation": "serviced"},
                {"serviceItemId": pads["id"], "operation": "inspected"},
            ],
        },
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mileage"] == 21500
    assert {line["operation"] for line in body["lines"]} == {"serviced", "inspected"}
    assert {line["serviceItemCode"] for line in body["lines"]} == {"engine-oil-filter", "brake-pads"}

    db_session.refresh(vehicle)
    assert vehicle.mileage == 21500

    # Replacing with an empty set unmaps the record; odometer never decreases.
    cleared = client.put(f"{URL}/{history_id}/lines", json={"lines": [], "mileage": 10000}, headers=staff_headers)
    assert cleared.status_code == 200
    assert cleared.json()["lines"] == []
    assert cleared.json()["mileage"] == 10000
    db_session.refresh(vehicle)
    assert vehicle.mileage == 21500


def test_complete_with_lines_records_operation_and_mileage(
    client, staff_headers, admin_headers, appointment_factory, db_session
):
    item = _create_item(client, admin_headers)
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    client.patch(f"{APPT_URL}/{appt.id}/status", json={"action": "start"}, headers=staff_headers)
    resp = client.patch(
        f"{APPT_URL}/{appt.id}/status",
        json={
            "action": "complete",
            "mileage": 16000,
            "lines": [{"serviceItemId": item["id"], "operation": "replaced", "notes": "OEM filter"}],
        },
        headers=staff_headers,
    )
    assert resp.status_code == 200

    body = client.get(URL, headers=staff_headers).json()
    assert body["total"] == 1
    record = body["items"][0]
    assert record["appointmentId"] == appt.id
    assert record["mileage"] == 16000
    assert record["description"] == "Periodic maintenance"
    assert len(record["lines"]) == 1
    assert record["lines"][0]["operation"] == "replaced"
    assert record["lines"][0]["source"] == "job_completion"
    assert record["lines"][0]["notes"] == "OEM filter"

    db_session.refresh(appt.owned_vehicle)
    assert appt.owned_vehicle.mileage == 16000


def test_lines_rejected_on_confirm(client, staff_headers, admin_headers, appointment_factory):
    item = _create_item(client, admin_headers)
    appt = appointment_factory(status=AppointmentStatus.requested)
    resp = client.patch(
        f"{APPT_URL}/{appt.id}/status",
        json={"action": "confirm", "lines": [{"serviceItemId": item["id"], "operation": "serviced"}]},
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_customer_history_omits_line_notes(
    client, staff_headers, admin_headers, customer_headers, owned_vehicle_factory, branch
):
    item = _create_item(client, admin_headers)
    vehicle = owned_vehicle_factory()
    client.post(
        URL,
        json=_entry(
            vehicle,
            branch,
            lines=[{"serviceItemId": item["id"], "operation": "serviced", "notes": "internal tech note"}],
        ),
        headers=staff_headers,
    )
    body = client.get(CUSTOMER_HISTORY, headers=customer_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["description"] == "Oil change and inspection"
    assert body["items"][0]["lines"] == []
