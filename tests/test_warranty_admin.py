"""Warranty admin API tests."""

from app.domains.customers.models import OwnedVehicle
from app.domains.shared.enums import ClaimStatus
from app.domains.warranty.models import WarrantyClaim


def _make_claim(db_session, customer, *, description: str, status=ClaimStatus.submitted):
    owned = OwnedVehicle(
        user_id=customer.id,
        vin="WTYTEST0000000001",
        model="Camry",
        trim="XSE",
        year=2023,
        color="White",
        registration_number="WTY-001",
        mileage=5000,
    )
    db_session.add(owned)
    db_session.flush()
    claim = WarrantyClaim(
        user_id=customer.id,
        owned_vehicle_id=owned.id,
        claim_type="Mechanical",
        description=description,
        status=status,
    )
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)
    return claim, owned


def test_warranty_requires_auth(client):
    assert client.get("/api/v1/admin/warranty/claims").status_code == 401


def test_warranty_summary(client, staff_headers, db_session, customer_user):
    _make_claim(db_session, customer_user, description="Engine vibration")
    res = client.get("/api/v1/admin/warranty/summary", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["pendingClaims"] >= 1


def test_list_and_update_claim(client, staff_headers, db_session, customer_user):
    claim, _ = _make_claim(db_session, customer_user, description="Engine vibration")

    res = client.get("/api/v1/admin/warranty/claims?status=pending", headers=staff_headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1

    detail = client.get(f"/api/v1/admin/warranty/claims/{claim.id}", headers=staff_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == claim.id

    updated = client.patch(
        f"/api/v1/admin/warranty/claims/{claim.id}",
        headers=staff_headers,
        json={"status": "approved", "resolutionNotes": "Covered under warranty"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "approved"
    assert updated.json()["resolutionNotes"] == "Covered under warranty"


def test_list_certificates_and_recalls(client, staff_headers):
    certs = client.get("/api/v1/admin/warranty/certificates", headers=staff_headers)
    assert certs.status_code == 200
    assert isinstance(certs.json(), list)

    recalls = client.get("/api/v1/admin/warranty/recalls", headers=staff_headers)
    assert recalls.status_code == 200
    assert isinstance(recalls.json(), list)


def test_issue_certificate_and_owned_vehicles(client, staff_headers, db_session, customer_user):
    _, owned = _make_claim(db_session, customer_user, description="For cert test")

    options = client.get("/api/v1/admin/warranty/owned-vehicles", headers=staff_headers)
    assert options.status_code == 200
    assert any(o["id"] == owned.id for o in options.json())

    created = client.post(
        "/api/v1/admin/warranty/certificates",
        headers=staff_headers,
        json={"ownedVehicleId": owned.id, "type": "standard"},
    )
    assert created.status_code == 201
    assert created.json()["certificateNumber"].startswith("ELZ-WTY-")


def test_create_recall_and_notify(client, staff_headers, db_session, customer_user):
    _, owned = _make_claim(db_session, customer_user, description="For recall test")

    created = client.post(
        "/api/v1/admin/warranty/recalls",
        headers=staff_headers,
        json={
            "referenceCode": "REC-TEST-0001",
            "title": "Test recall",
            "description": "Inspect test component",
            "severity": "medium",
            "affectedModels": ["Camry"],
        },
    )
    assert created.status_code == 201
    recall_id = created.json()["id"]
    assert created.json()["affectedCount"] >= 1

    notified = client.post(f"/api/v1/admin/warranty/recalls/{recall_id}/notify", headers=staff_headers)
    assert notified.status_code == 200
    assert notified.json()["notifiedCount"] >= 0
