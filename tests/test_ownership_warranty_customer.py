"""Tests for vehicle ownership claim flow and customer warranty."""

from app.domains.customers.models import OwnedVehicle
from app.domains.shared.enums import AvailabilityStatus


def test_ownership_requires_auth(client):
    assert client.get("/api/v1/ownership/vehicles").status_code == 401


def test_vin_lookup_and_submit(client, customer_headers, vehicle_factory):
    vehicle = vehicle_factory(vin="JTDBT923000123456", availability=AvailabilityStatus.sold)

    lookup = client.get("/api/v1/ownership/lookup?vin=JTDBT923000123456", headers=customer_headers)
    assert lookup.status_code == 200
    data = lookup.json()
    assert data["found"] is True
    assert data["canSubmit"] is True
    assert data["vehiclePreview"]["model"] == vehicle.model

    created = client.post(
        "/api/v1/ownership/requests",
        headers=customer_headers,
        json={
            "vin": "JTDBT923000123456",
            "registrationNumber": "ABC-123",
            "documentUrls": ["/media/documents/test.pdf"],
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"


def test_admin_approve_creates_owned_vehicle(
    client, staff_headers, customer_headers, db_session, vehicle_factory, customer_user
):
    vehicle = vehicle_factory(vin="JTDBT923000999999", availability=AvailabilityStatus.sold)

    submit = client.post(
        "/api/v1/ownership/requests",
        headers=customer_headers,
        json={"vin": "JTDBT923000999999", "registrationNumber": "XYZ-999"},
    )
    request_id = submit.json()["id"]

    listed = client.get("/api/v1/admin/ownership/requests?status=pending", headers=staff_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    approved = client.patch(
        f"/api/v1/admin/ownership/requests/{request_id}",
        headers=staff_headers,
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["ownedVehicleId"]

    garage = client.get("/api/v1/ownership/vehicles", headers=customer_headers)
    assert garage.status_code == 200
    assert any(v["vin"] == "JTDBT923000999999" for v in garage.json())

    owned = db_session.query(OwnedVehicle).filter(OwnedVehicle.vin == "JTDBT923000999999").one()
    assert owned.user_id == customer_user.id
    assert owned.inventory_vehicle_id == vehicle.id


def test_warranty_customer_submit(client, customer_headers, owned_vehicle_factory, db_session):
    from datetime import datetime, timezone

    owned = owned_vehicle_factory(
        vin="WTYCLM0000000001",
        mileage=5000,
        purchase_date=datetime.now(timezone.utc),
    )

    elig = client.get(f"/api/v1/warranty/eligibility?ownedVehicleId={owned.id}", headers=customer_headers)
    assert elig.status_code == 200
    assert elig.json()["warrantyMonths"] == 36

    claim = client.post(
        "/api/v1/warranty/claims",
        headers=customer_headers,
        json={
            "ownedVehicleId": owned.id,
            "claimType": "Powertrain",
            "description": "Engine vibration under load at highway speeds",
            "currentMileage": 5200,
            "conditions": "Occurs above 80 km/h",
        },
    )
    assert claim.status_code == 201
    assert claim.json()["status"] == "submitted"

    db_session.refresh(owned)
    assert owned.mileage == 5200


def test_admin_approve_with_custom_in_service_date(
    client, staff_headers, customer_headers, db_session, vehicle_factory, customer_user
):
    from datetime import datetime, timezone

    from app.domains.customers.models import OwnedVehicle
    from app.domains.warranty.models import WarrantyCertificate

    vehicle = vehicle_factory(vin="JTDBT923000888888", availability=AvailabilityStatus.sold)
    delivery = datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)

    submit = client.post(
        "/api/v1/ownership/requests",
        headers=customer_headers,
        json={"vin": "JTDBT923000888888", "registrationNumber": "LAG-888"},
    )
    request_id = submit.json()["id"]

    approved = client.patch(
        f"/api/v1/admin/ownership/requests/{request_id}",
        headers=staff_headers,
        json={"status": "approved", "inServiceDate": delivery.isoformat()},
    )
    assert approved.status_code == 200

    owned = db_session.query(OwnedVehicle).filter(OwnedVehicle.vin == "JTDBT923000888888").one()
    assert owned.purchase_date.replace(tzinfo=timezone.utc) == delivery

    cert = (
        db_session.query(WarrantyCertificate)
        .filter(WarrantyCertificate.owned_vehicle_id == owned.id)
        .one()
    )
    assert cert.coverage_start.replace(tzinfo=timezone.utc) == delivery
