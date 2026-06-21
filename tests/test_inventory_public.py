"""
Phase 1 — public inventory read endpoints:
    GET /api/v1/vehicles
    GET /api/v1/vehicles/{id}
    GET /api/v1/vehicles/compare?ids=...
"""

from decimal import Decimal

from app.domains.shared.enums import AvailabilityStatus

LIST_URL = "/api/v1/vehicles"


# --------------------------------------------------------------------------- #
# GET /vehicles — list                                                         #
# --------------------------------------------------------------------------- #

def test_list_empty(client):
    resp = client.get(LIST_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "page": 1, "limit": 20, "total": 0, "totalPages": 0}


def test_list_returns_published_available(client, vehicle_factory):
    vehicle_factory(model="Corolla")
    vehicle_factory(model="Camry")
    resp = client.get(LIST_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {item["model"] for item in body["items"]} == {"Corolla", "Camry"}


def test_list_excludes_unpublished(client, vehicle_factory):
    vehicle_factory(model="Visible", is_published=True)
    vehicle_factory(model="Hidden", is_published=False)
    body = client.get(LIST_URL).json()
    assert body["total"] == 1
    assert body["items"][0]["model"] == "Visible"


def test_list_excludes_soft_deleted(client, vehicle_factory, db_session):
    from datetime import datetime, timezone

    keep = vehicle_factory(model="Keep")
    gone = vehicle_factory(model="Gone")
    gone.deleted_at = datetime.now(timezone.utc)
    db_session.commit()
    body = client.get(LIST_URL).json()
    assert body["total"] == 1
    assert body["items"][0]["model"] == "Keep"


def test_list_excludes_sold_and_transferred_by_default(client, vehicle_factory):
    vehicle_factory(model="Available", availability=AvailabilityStatus.available)
    vehicle_factory(model="Reserved", availability=AvailabilityStatus.reserved)
    vehicle_factory(model="Sold", availability=AvailabilityStatus.sold)
    vehicle_factory(model="Transferred", availability=AvailabilityStatus.transferred)
    body = client.get(LIST_URL).json()
    assert body["total"] == 2
    assert {i["model"] for i in body["items"]} == {"Available", "Reserved"}


def test_list_filter_by_make_partial_ci(client, vehicle_factory):
    vehicle_factory(make="Toyota", model="Corolla")
    vehicle_factory(make="Jetour", model="X70")
    body = client.get(LIST_URL, params={"make": "toy"}).json()
    assert body["total"] == 1
    assert body["items"][0]["make"] == "Toyota"


def test_list_filter_by_branch(client, vehicle_factory, branch, db_session):
    from app.domains.branches.models import Branch
    from app.domains.shared.enums import BranchType

    other = Branch(name="Elizade Abuja", type=BranchType.showroom, city="Abuja", state="FCT", address="Wuse")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    vehicle_factory(model="Lekki", branch_id=branch.id)
    vehicle_factory(model="Abuja", branch_id=other.id)
    body = client.get(LIST_URL, params={"branchId": other.id}).json()
    assert body["total"] == 1
    assert body["items"][0]["model"] == "Abuja"


def test_list_filter_price_range(client, vehicle_factory):
    vehicle_factory(model="Cheap", price=Decimal("10000000.00"))
    vehicle_factory(model="Mid", price=Decimal("25000000.00"))
    vehicle_factory(model="Pricey", price=Decimal("50000000.00"))
    body = client.get(LIST_URL, params={"minPrice": 20000000, "maxPrice": 40000000}).json()
    assert body["total"] == 1
    assert body["items"][0]["model"] == "Mid"


def test_list_availability_filter_valid(client, vehicle_factory):
    vehicle_factory(model="Available", availability=AvailabilityStatus.available)
    vehicle_factory(model="Reserved", availability=AvailabilityStatus.reserved)
    body = client.get(LIST_URL, params={"availability": "reserved"}).json()
    assert body["total"] == 1
    assert body["items"][0]["model"] == "Reserved"


def test_list_availability_filter_forbidden_value(client, vehicle_factory):
    vehicle_factory()
    resp = client.get(LIST_URL, params={"availability": "sold"})
    assert resp.status_code == 400


def test_list_availability_filter_invalid_value(client):
    resp = client.get(LIST_URL, params={"availability": "banana"})
    assert resp.status_code == 400


def test_list_pagination(client, vehicle_factory):
    for i in range(5):
        vehicle_factory(model=f"Car{i}")
    body = client.get(LIST_URL, params={"page": 2, "limit": 2}).json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["limit"] == 2
    assert body["totalPages"] == 3
    assert len(body["items"]) == 2


def test_list_sort_price_ascending(client, vehicle_factory):
    vehicle_factory(model="B", price=Decimal("30000000.00"))
    vehicle_factory(model="A", price=Decimal("10000000.00"))
    body = client.get(LIST_URL, params={"sort": "price"}).json()
    assert [i["model"] for i in body["items"]] == ["A", "B"]


def test_list_invalid_sort(client):
    resp = client.get(LIST_URL, params={"sort": "color"})
    assert resp.status_code == 400


def test_list_primary_image_url(client, vehicle_factory, image_factory):
    vehicle = vehicle_factory()
    image_factory(vehicle, url="https://cdn.elizade.test/secondary.jpg", sort_order=1, is_primary=False)
    image_factory(vehicle, url="https://cdn.elizade.test/primary.jpg", sort_order=0, is_primary=True)
    body = client.get(LIST_URL).json()
    assert body["items"][0]["primaryImageUrl"] == "https://cdn.elizade.test/primary.jpg"


# --------------------------------------------------------------------------- #
# GET /vehicles/{id} — detail                                                  #
# --------------------------------------------------------------------------- #

def test_detail_ok(client, vehicle_factory, image_factory):
    vehicle = vehicle_factory(model="Camry", engine="2.5L", specs={"airbags": 7})
    image_factory(vehicle, url="https://cdn.elizade.test/a.jpg", is_primary=True)
    resp = client.get(f"{LIST_URL}/{vehicle.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == vehicle.id
    assert body["model"] == "Camry"
    assert body["engine"] == "2.5L"
    assert body["specs"] == {"airbags": 7}
    assert body["branchName"] == "Elizade Lekki"
    assert body["branchCity"] == "Lagos"
    assert len(body["images"]) == 1


def test_detail_unpublished_404(client, vehicle_factory):
    vehicle = vehicle_factory(is_published=False)
    assert client.get(f"{LIST_URL}/{vehicle.id}").status_code == 404


def test_detail_soft_deleted_404(client, vehicle_factory, db_session):
    from datetime import datetime, timezone

    vehicle = vehicle_factory()
    vehicle.deleted_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.get(f"{LIST_URL}/{vehicle.id}").status_code == 404


def test_detail_not_found_404(client):
    assert client.get(f"{LIST_URL}/00000000-0000-0000-0000-000000000000").status_code == 404


# --------------------------------------------------------------------------- #
# GET /vehicles/compare                                                        #
# --------------------------------------------------------------------------- #

def test_compare_two_vehicles(client, vehicle_factory):
    a = vehicle_factory(model="Corolla")
    b = vehicle_factory(model="Camry")
    resp = client.get(f"{LIST_URL}/compare", params={"ids": f"{a.id},{b.id}"})
    assert resp.status_code == 200
    body = resp.json()
    assert [v["id"] for v in body] == [a.id, b.id]  # caller order preserved


def test_compare_requires_exactly_two(client, vehicle_factory):
    a = vehicle_factory()
    resp = client.get(f"{LIST_URL}/compare", params={"ids": a.id})
    assert resp.status_code == 400


def test_compare_rejects_duplicate_ids(client, vehicle_factory):
    a = vehicle_factory()
    resp = client.get(f"{LIST_URL}/compare", params={"ids": f"{a.id},{a.id}"})
    assert resp.status_code == 400


def test_compare_missing_vehicle_404(client, vehicle_factory):
    a = vehicle_factory()
    resp = client.get(
        f"{LIST_URL}/compare",
        params={"ids": f"{a.id},00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_compare_excludes_unpublished(client, vehicle_factory):
    a = vehicle_factory(is_published=True)
    b = vehicle_factory(is_published=False)
    resp = client.get(f"{LIST_URL}/compare", params={"ids": f"{a.id},{b.id}"})
    assert resp.status_code == 404
