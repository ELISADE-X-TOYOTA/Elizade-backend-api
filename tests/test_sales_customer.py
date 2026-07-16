"""Customer sales API — test drive bookings."""

from datetime import datetime, timedelta, timezone

SALES = "/api/v1/sales/test-drives"


def test_list_test_drives_requires_auth(client):
    assert client.get(SALES).status_code == 401


def test_book_test_drive(client, customer_headers, branch, vehicle_factory):
    vehicle = vehicle_factory()
    scheduled = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    resp = client.post(
        SALES,
        json={
            "vehicleId": vehicle.id,
            "branchId": branch.id,
            "scheduledAt": scheduled.isoformat().replace("+00:00", "Z"),
            "notes": "Prefer morning slot",
        },
        headers=customer_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "requested"
    assert body["vehicleId"] == vehicle.id
    assert body["leadId"] is not None
    assert "Prefer morning" in (body["notes"] or "")

    listed = client.get(SALES, headers=customer_headers).json()
    assert len(listed) >= 1
    assert listed[0]["id"] == body["id"]


def test_book_test_drive_past_time_rejected(client, customer_headers, branch, vehicle_factory):
    vehicle = vehicle_factory()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    resp = client.post(
        SALES,
        json={"vehicleId": vehicle.id, "branchId": branch.id, "scheduledAt": past},
        headers=customer_headers,
    )
    assert resp.status_code == 400
