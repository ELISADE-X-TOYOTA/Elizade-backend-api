"""
Phase 2 — admin inventory endpoints:
    GET    /api/v1/admin/vehicles
    GET    /api/v1/admin/vehicles/{id}
    POST   /api/v1/admin/vehicles
    PATCH  /api/v1/admin/vehicles/{id}
    PATCH  /api/v1/admin/vehicles/{id}/status
    DELETE /api/v1/admin/vehicles/{id}
"""

from datetime import datetime, timezone

from app.domains.shared.enums import AvailabilityStatus

ADMIN_URL = "/api/v1/admin/vehicles"


def _payload(branch, **overrides) -> dict:
    body = {
        "model": "Corolla",
        "trim": "LE",
        "year": 2024,
        "color": "White",
        "colorHex": "#FFFFFF",
        "price": 25000000,
        "fuelType": "Petrol",
        "transmission": "Automatic",
        "engine": "1.8L 4-cylinder",
        "branchId": branch.id,
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# Auth enforcement                                                            #
# --------------------------------------------------------------------------- #

def test_list_requires_auth(client):
    assert client.get(ADMIN_URL).status_code == 401


def test_list_rejects_customer(client, customer_headers):
    assert client.get(ADMIN_URL, headers=customer_headers).status_code == 403


def test_list_allows_staff(client, staff_headers):
    assert client.get(ADMIN_URL, headers=staff_headers).status_code == 200


def test_create_rejects_staff(client, staff_headers, branch):
    resp = client.post(ADMIN_URL, json=_payload(branch), headers=staff_headers)
    assert resp.status_code == 403


def test_create_rejects_customer(client, customer_headers, branch):
    resp = client.post(ADMIN_URL, json=_payload(branch), headers=customer_headers)
    assert resp.status_code == 403


def test_update_rejects_staff(client, staff_headers, vehicle_factory):
    v = vehicle_factory()
    resp = client.patch(f"{ADMIN_URL}/{v.id}", json={"price": 1}, headers=staff_headers)
    assert resp.status_code == 403


def test_status_allows_staff(client, staff_headers, vehicle_factory):
    v = vehicle_factory()
    resp = client.patch(f"{ADMIN_URL}/{v.id}/status", json={"availability": "reserved"}, headers=staff_headers)
    assert resp.status_code == 200


def test_delete_rejects_staff(client, staff_headers, vehicle_factory):
    v = vehicle_factory()
    assert client.delete(f"{ADMIN_URL}/{v.id}", headers=staff_headers).status_code == 403


# --------------------------------------------------------------------------- #
# Create                                                                      #
# --------------------------------------------------------------------------- #

def test_create_ok(client, admin_headers, admin_user, branch):
    resp = client.post(ADMIN_URL, json=_payload(branch, vin="JT123456789012345"), headers=admin_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["model"] == "Corolla"
    assert body["vin"] == "JT123456789012345"
    assert body["createdById"] == admin_user.id
    assert body["isPublished"] is True
    assert body["publishedAt"] is not None  # stamped on publish


def test_create_unpublished_has_no_publish_time(client, admin_headers, branch):
    resp = client.post(ADMIN_URL, json=_payload(branch, isPublished=False), headers=admin_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["isPublished"] is False
    assert body["publishedAt"] is None


def test_create_invalid_branch(client, admin_headers, branch):
    resp = client.post(
        ADMIN_URL,
        json=_payload(branch, branchId="00000000-0000-0000-0000-000000000000"),
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_create_duplicate_vin(client, admin_headers, branch, vehicle_factory):
    vehicle_factory(vin="DUPVIN00000000001")
    resp = client.post(ADMIN_URL, json=_payload(branch, vin="DUPVIN00000000001"), headers=admin_headers)
    assert resp.status_code == 409


def test_create_duplicate_stock_number(client, admin_headers, branch, vehicle_factory):
    vehicle_factory(stock_number="STK-001")
    resp = client.post(ADMIN_URL, json=_payload(branch, stockNumber="STK-001"), headers=admin_headers)
    assert resp.status_code == 409


def test_create_invalid_availability(client, admin_headers, branch):
    resp = client.post(ADMIN_URL, json=_payload(branch, availability="banana"), headers=admin_headers)
    assert resp.status_code == 400


def test_create_invalid_price_rejected_by_schema(client, admin_headers, branch):
    resp = client.post(ADMIN_URL, json=_payload(branch, price=0), headers=admin_headers)
    assert resp.status_code == 422  # Field(gt=0)


# --------------------------------------------------------------------------- #
# List                                                                        #
# --------------------------------------------------------------------------- #

def test_list_includes_all_statuses(client, admin_headers, vehicle_factory):
    vehicle_factory(availability=AvailabilityStatus.available)
    vehicle_factory(availability=AvailabilityStatus.sold)
    vehicle_factory(availability=AvailabilityStatus.transferred)
    body = client.get(ADMIN_URL, headers=admin_headers).json()
    assert body["total"] == 3


def test_list_excludes_deleted_by_default(client, admin_headers, vehicle_factory):
    vehicle_factory(model="Alive")
    vehicle_factory(model="Dead", deleted_at=datetime.now(timezone.utc))
    body = client.get(ADMIN_URL, headers=admin_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["model"] == "Alive"


def test_list_include_deleted_flag(client, admin_headers, vehicle_factory):
    vehicle_factory(model="Alive")
    vehicle_factory(model="Dead", deleted_at=datetime.now(timezone.utc))
    body = client.get(ADMIN_URL, params={"includeDeleted": "true"}, headers=admin_headers).json()
    assert body["total"] == 2


def test_list_filter_sold(client, admin_headers, vehicle_factory):
    vehicle_factory(availability=AvailabilityStatus.available)
    vehicle_factory(availability=AvailabilityStatus.sold)
    body = client.get(ADMIN_URL, params={"availability": "sold"}, headers=admin_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["availability"] == "sold"


def test_list_filter_unpublished(client, admin_headers, vehicle_factory):
    vehicle_factory(is_published=True)
    vehicle_factory(is_published=False)
    body = client.get(ADMIN_URL, params={"isPublished": "false"}, headers=admin_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["isPublished"] is False


def test_list_invalid_availability(client, admin_headers):
    resp = client.get(ADMIN_URL, params={"availability": "banana"}, headers=admin_headers)
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Detail                                                                      #
# --------------------------------------------------------------------------- #

def test_detail_ok(client, admin_headers, vehicle_factory):
    v = vehicle_factory(vin="VIN00000000000001", stock_number="STK-9")
    resp = client.get(f"{ADMIN_URL}/{v.id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["vin"] == "VIN00000000000001"
    assert body["stockNumber"] == "STK-9"
    assert body["isPublished"] is True


def test_detail_not_found(client, admin_headers):
    assert client.get(f"{ADMIN_URL}/00000000-0000-0000-0000-000000000000", headers=admin_headers).status_code == 404


def test_detail_deleted_404(client, admin_headers, vehicle_factory):
    v = vehicle_factory(deleted_at=datetime.now(timezone.utc))
    assert client.get(f"{ADMIN_URL}/{v.id}", headers=admin_headers).status_code == 404


# --------------------------------------------------------------------------- #
# Update                                                                      #
# --------------------------------------------------------------------------- #

def test_update_price_promo_specs(client, admin_headers, vehicle_factory):
    v = vehicle_factory(price="25000000.00")
    resp = client.patch(
        f"{ADMIN_URL}/{v.id}",
        json={
            "price": 23000000,
            "isPromotional": True,
            "promotionLabel": "Eid Sale",
            "promotionalPrice": 21000000,
            "specs": {"airbags": 7},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == "23000000.00"
    assert body["isPromotional"] is True
    assert body["promotionLabel"] == "Eid Sale"
    assert body["specs"] == {"airbags": 7}


def test_update_branch(client, admin_headers, vehicle_factory, db_session):
    from app.domains.branches.models import Branch
    from app.domains.shared.enums import BranchType

    other = Branch(name="Elizade Ibadan", type=BranchType.showroom, city="Ibadan", state="Oyo", address="Ring Rd")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    v = vehicle_factory()
    resp = client.patch(f"{ADMIN_URL}/{v.id}", json={"branchId": other.id}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["branchId"] == other.id
    assert resp.json()["branchName"] == "Elizade Ibadan"


def test_update_invalid_branch(client, admin_headers, vehicle_factory):
    v = vehicle_factory()
    resp = client.patch(
        f"{ADMIN_URL}/{v.id}",
        json={"branchId": "00000000-0000-0000-0000-000000000000"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_update_vin_conflict(client, admin_headers, vehicle_factory):
    vehicle_factory(vin="EXISTING000000001")
    target = vehicle_factory(vin="OWNVIN00000000001")
    resp = client.patch(f"{ADMIN_URL}/{target.id}", json={"vin": "EXISTING000000001"}, headers=admin_headers)
    assert resp.status_code == 409


def test_update_not_found(client, admin_headers):
    resp = client.patch(
        f"{ADMIN_URL}/00000000-0000-0000-0000-000000000000",
        json={"price": 1000},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Status                                                                      #
# --------------------------------------------------------------------------- #

def test_status_update_ok(client, admin_headers, vehicle_factory):
    v = vehicle_factory(availability=AvailabilityStatus.available)
    resp = client.patch(f"{ADMIN_URL}/{v.id}/status", json={"availability": "sold"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["availability"] == "sold"


def test_status_update_invalid(client, admin_headers, vehicle_factory):
    v = vehicle_factory()
    resp = client.patch(f"{ADMIN_URL}/{v.id}/status", json={"availability": "banana"}, headers=admin_headers)
    assert resp.status_code == 400


def test_status_update_not_found(client, admin_headers):
    resp = client.patch(
        f"{ADMIN_URL}/00000000-0000-0000-0000-000000000000/status",
        json={"availability": "sold"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Delete (soft)                                                               #
# --------------------------------------------------------------------------- #

def test_delete_soft_removes_from_views(client, admin_headers, vehicle_factory):
    v = vehicle_factory()
    assert client.delete(f"{ADMIN_URL}/{v.id}", headers=admin_headers).status_code == 204
    # Gone from admin detail and default list...
    assert client.get(f"{ADMIN_URL}/{v.id}", headers=admin_headers).status_code == 404
    assert client.get(ADMIN_URL, headers=admin_headers).json()["total"] == 0
    # ...but still visible with includeDeleted.
    body = client.get(ADMIN_URL, params={"includeDeleted": "true"}, headers=admin_headers).json()
    assert body["total"] == 1


def test_delete_hidden_from_public(client, admin_headers, vehicle_factory):
    v = vehicle_factory()
    client.delete(f"{ADMIN_URL}/{v.id}", headers=admin_headers)
    assert client.get(f"/api/v1/vehicles/{v.id}").status_code == 404


def test_delete_twice_404(client, admin_headers, vehicle_factory):
    v = vehicle_factory()
    assert client.delete(f"{ADMIN_URL}/{v.id}", headers=admin_headers).status_code == 204
    assert client.delete(f"{ADMIN_URL}/{v.id}", headers=admin_headers).status_code == 404
