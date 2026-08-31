"""Service-item catalogue (Phase 1 — Service Board)."""

ITEMS = "/api/v1/admin/service/items"


def _payload(**overrides) -> dict:
    body = {
        "code": "engine-oil-filter",
        "name": "Engine oil and filter",
        "group": "periodic",
        "description": "Scheduled oil and filter change",
        "sortOrder": 10,
    }
    body.update(overrides)
    return body


def test_list_requires_auth(client):
    assert client.get(ITEMS).status_code == 401


def test_list_rejects_customer(client, customer_headers):
    assert client.get(ITEMS, headers=customer_headers).status_code == 403


def test_list_empty(client, staff_headers):
    assert client.get(ITEMS, headers=staff_headers).json() == []


def test_staff_cannot_create(client, staff_headers):
    assert client.post(ITEMS, json=_payload(), headers=staff_headers).status_code == 403


def test_create_ok(client, admin_headers, staff_headers):
    resp = client.post(ITEMS, json=_payload(), headers=admin_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "engine-oil-filter"
    assert body["group"] == "periodic"
    assert body["isActive"] is True

    listed = client.get(ITEMS, headers=staff_headers).json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_create_normalizes_code(client, admin_headers):
    resp = client.post(ITEMS, json=_payload(code="Brake-Pads"), headers=admin_headers)
    assert resp.status_code == 201
    assert resp.json()["code"] == "brake-pads"


def test_create_rejects_bad_code(client, admin_headers):
    resp = client.post(ITEMS, json=_payload(code="Oil Filter!"), headers=admin_headers)
    assert resp.status_code == 422


def test_create_rejects_unknown_group(client, admin_headers):
    resp = client.post(ITEMS, json=_payload(group="bodywork"), headers=admin_headers)
    assert resp.status_code == 400


def test_create_duplicate_code_conflict(client, admin_headers):
    client.post(ITEMS, json=_payload(), headers=admin_headers)
    resp = client.post(ITEMS, json=_payload(name="Other"), headers=admin_headers)
    assert resp.status_code == 409


def test_update_deactivate_and_filter(client, admin_headers, staff_headers):
    item_id = client.post(ITEMS, json=_payload(), headers=admin_headers).json()["id"]
    client.post(
        ITEMS,
        json=_payload(code="brake-pads", name="Brake pads", group="chassis"),
        headers=admin_headers,
    )

    resp = client.patch(f"{ITEMS}/{item_id}", json={"isActive": False}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["isActive"] is False

    active = client.get(ITEMS, params={"isActive": True}, headers=staff_headers).json()
    assert len(active) == 1
    assert active[0]["code"] == "brake-pads"

    chassis = client.get(ITEMS, params={"group": "chassis"}, headers=staff_headers).json()
    assert len(chassis) == 1
    assert chassis[0]["code"] == "brake-pads"


def test_update_not_found(client, admin_headers):
    resp = client.patch(
        f"{ITEMS}/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 404
