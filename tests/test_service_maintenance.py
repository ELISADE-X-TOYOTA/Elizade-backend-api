"""Phase 3 — maintenance intervals, due/overdue lists, vehicle detail."""

INTERVALS = "/api/v1/admin/service/maintenance/intervals"
SETTINGS = "/api/v1/admin/service/maintenance/settings"
DUE_SOON = "/api/v1/admin/service/maintenance/due-soon"
OVERDUE = "/api/v1/admin/service/maintenance/overdue"
CALL_LIST = "/api/v1/admin/service/maintenance/call-list"
ITEMS = "/api/v1/admin/service/items"
HISTORY = "/api/v1/admin/service/history"


def _create_item(client, admin_headers, code="engine-oil-filter"):
    return client.post(
        ITEMS,
        json={"code": code, "name": "Engine oil and filter", "group": "periodic"},
        headers=admin_headers,
    ).json()


def _create_interval(client, admin_headers, item_id, **overrides):
    body = {
        "serviceItemId": item_id,
        "kind": "scheduled",
        "intervalKm": 10_000,
        "intervalMonths": 12,
        **overrides,
    }
    return client.post(INTERVALS, json=body, headers=admin_headers)


def test_settings_defaults_for_staff(client, staff_headers):
    body = client.get(SETTINGS, headers=staff_headers).json()
    assert body["dueSoonKm"] == 500
    assert body["dueSoonDays"] == 30


def test_staff_cannot_create_interval(client, staff_headers, admin_headers):
    item_id = _create_item(client, admin_headers)["id"]
    assert _create_interval(client, staff_headers, item_id).status_code == 403


def test_interval_crud_and_vehicle_detail(
    client,
    staff_headers,
    admin_headers,
    db_session,
    customer_user,
    branch,
):
    from datetime import datetime, timezone

    from app.domains.customers.models import OwnedVehicle

    item_id = _create_item(client, admin_headers)["id"]
    assert _create_interval(client, admin_headers, item_id).status_code == 201

    vehicle = OwnedVehicle(
        user_id=customer_user.id,
        vin="1HGBH41JXMN109186",
        make="Toyota",
        model="Corolla",
        trim="LE",
        year=2022,
        color="White",
        mileage=49_600,
        registration_number="ABC-123",
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(vehicle)
    db_session.commit()
    branch_id = branch.id

    detail = client.get(
        f"/api/v1/admin/service/maintenance/vehicles/{vehicle.id}",
        headers=staff_headers,
    ).json()
    assert detail["ownedVehicleId"] == vehicle.id
    oil = next(i for i in detail["items"] if i["serviceItemCode"] == "engine-oil-filter")
    assert oil["status"] == "not_on_record"

    client.post(
        HISTORY,
        json={
            "ownedVehicleId": vehicle.id,
            "branchId": branch_id,
            "serviceType": "periodic",
            "performedAt": "2026-01-01T10:00:00Z",
            "mileage": 40_000,
            "description": "Service visit",
            "cost": 0,
            "lines": [{"serviceItemId": item_id, "operation": "serviced"}],
        },
        headers=admin_headers,
    )

    detail = client.get(
        f"/api/v1/admin/service/maintenance/vehicles/{vehicle.id}",
        headers=staff_headers,
    ).json()
    oil = next(i for i in detail["items"] if i["serviceItemCode"] == "engine-oil-filter")
    assert oil["status"] == "due_soon"

    due = client.get(DUE_SOON, headers=staff_headers).json()
    assert due["total"] >= 1
    assert any(row["ownedVehicleId"] == vehicle.id for row in due["items"])

    call = client.get(CALL_LIST, headers=staff_headers).json()
    assert call["total"] >= 1


def test_overdue_when_past_km_interval(client, staff_headers, admin_headers, db_session, customer_user, branch):
    from datetime import datetime, timezone

    from app.domains.customers.models import OwnedVehicle

    item_id = _create_item(client, admin_headers, code="brake-pads")["id"]
    _create_interval(client, admin_headers, item_id, intervalKm=5_000, intervalMonths=None)

    vehicle = OwnedVehicle(
        user_id=customer_user.id,
        vin="2HGBH41JXMN109187",
        make="Toyota",
        model="Hilux",
        trim="SR",
        year=2021,
        color="Black",
        mileage=20_000,
        registration_number="XYZ-999",
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(vehicle)
    db_session.commit()
    branch_id = branch.id

    client.post(
        HISTORY,
        json={
            "ownedVehicleId": vehicle.id,
            "branchId": branch_id,
            "serviceType": "periodic",
            "performedAt": "2025-01-01T10:00:00Z",
            "mileage": 10_000,
            "description": "Brake service",
            "cost": 0,
            "lines": [{"serviceItemId": item_id, "operation": "replaced"}],
        },
        headers=admin_headers,
    )

    detail = client.get(
        f"/api/v1/admin/service/maintenance/vehicles/{vehicle.id}",
        headers=staff_headers,
    ).json()
    brake = next(i for i in detail["items"] if i["serviceItemCode"] == "brake-pads")
    assert brake["status"] == "overdue"

    overdue = client.get(OVERDUE, headers=staff_headers).json()
    assert any(row["ownedVehicleId"] == vehicle.id for row in overdue["items"])
