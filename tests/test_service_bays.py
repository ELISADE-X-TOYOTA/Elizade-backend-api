"""
Phase 1 — service bays:
    GET   /api/v1/admin/service/bays
    POST  /api/v1/admin/service/bays
    PATCH /api/v1/admin/service/bays/{bay_id}
"""

BAYS_URL = "/api/v1/admin/service/bays"


# --------------------------------------------------------------------------- #
# List (staff)                                                                #
# --------------------------------------------------------------------------- #

def test_list_requires_auth(client):
    assert client.get(BAYS_URL).status_code == 401


def test_list_rejects_customer(client, customer_headers):
    assert client.get(BAYS_URL, headers=customer_headers).status_code == 403


def test_list_allows_staff(client, staff_headers, service_bay_factory):
    service_bay_factory(name="Bay 1")
    service_bay_factory(name="Bay 2")
    resp = client.get(BAYS_URL, headers=staff_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert {b["name"] for b in body} == {"Bay 1", "Bay 2"}
    assert body[0]["branchName"] == "Elizade Lekki"


def test_list_filter_by_branch(client, staff_headers, service_bay_factory, branch, db_session):
    from app.domains.branches.models import Branch
    from app.domains.shared.enums import BranchType

    other = Branch(name="Elizade Ikeja", type=BranchType.service_centre, city="Lagos", state="Lagos", address="Ikeja")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    service_bay_factory(name="Lekki Bay", branch_id=branch.id)
    service_bay_factory(name="Ikeja Bay", branch_id=other.id)
    body = client.get(BAYS_URL, params={"branchId": other.id}, headers=staff_headers).json()
    assert len(body) == 1
    assert body[0]["name"] == "Ikeja Bay"


# --------------------------------------------------------------------------- #
# Create (admin)                                                              #
# --------------------------------------------------------------------------- #

def test_create_rejects_staff(client, staff_headers, branch):
    resp = client.post(BAYS_URL, json={"branchId": branch.id, "name": "Bay 9"}, headers=staff_headers)
    assert resp.status_code == 403


def test_create_ok(client, admin_headers, branch):
    resp = client.post(BAYS_URL, json={"branchId": branch.id, "name": "Bay 9"}, headers=admin_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Bay 9"
    assert body["branchId"] == branch.id
    assert body["isActive"] is True


def test_create_invalid_branch(client, admin_headers):
    resp = client.post(
        BAYS_URL,
        json={"branchId": "00000000-0000-0000-0000-000000000000", "name": "Bay 9"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Update (admin)                                                              #
# --------------------------------------------------------------------------- #

def test_update_rejects_staff(client, staff_headers, service_bay_factory):
    bay = service_bay_factory()
    resp = client.patch(f"{BAYS_URL}/{bay.id}", json={"name": "Renamed"}, headers=staff_headers)
    assert resp.status_code == 403


def test_update_rename_and_deactivate(client, admin_headers, service_bay_factory):
    bay = service_bay_factory(name="Bay 1", is_active=True)
    resp = client.patch(f"{BAYS_URL}/{bay.id}", json={"name": "Bay 1A", "isActive": False}, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Bay 1A"
    assert body["isActive"] is False


def test_update_not_found(client, admin_headers):
    resp = client.patch(
        f"{BAYS_URL}/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 404
