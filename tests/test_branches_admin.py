"""Admin branch management — CRUD and summary."""

ADMIN_URL = "/api/v1/admin/branches"


def test_summary_requires_admin(client):
    assert client.get(f"{ADMIN_URL}/summary").status_code == 401


def test_summary_rejects_staff(client, staff_headers):
    assert client.get(f"{ADMIN_URL}/summary", headers=staff_headers).status_code == 403


def test_summary_and_list(client, admin_headers, branch):
    summary = client.get(f"{ADMIN_URL}/summary", headers=admin_headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] >= 1
    assert body["active"] >= 1

    listed = client.get(ADMIN_URL, headers=admin_headers)
    assert listed.status_code == 200
    assert any(row["id"] == branch.id for row in listed.json())


def test_create_branch(client, admin_headers):
    resp = client.post(
        ADMIN_URL,
        headers=admin_headers,
        json={
            "name": "Elizade Port Harcourt",
            "type": "both",
            "city": "Port Harcourt",
            "state": "Rivers",
            "address": "12 Aba Road, PH",
            "phone": "08030001111",
            "isActive": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Elizade Port Harcourt"
    assert body["type"] == "both"
    assert body["isActive"] is True


def test_create_duplicate_name_same_city(client, admin_headers, branch):
    resp = client.post(
        ADMIN_URL,
        headers=admin_headers,
        json={
            "name": branch.name,
            "type": "showroom",
            "city": branch.city,
            "state": branch.state,
            "address": "Different address",
        },
    )
    assert resp.status_code == 409


def test_update_and_deactivate(client, admin_headers, branch):
    patch = client.patch(
        f"{ADMIN_URL}/{branch.id}",
        headers=admin_headers,
        json={"phone": "08099998888", "isActive": False},
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["phone"] == "08099998888"
    assert body["isActive"] is False

    public = client.get("/api/v1/branches")
    assert public.status_code == 200
    assert branch.id not in {row["id"] for row in public.json()}


def test_get_branch_detail(client, admin_headers, branch):
    resp = client.get(f"{ADMIN_URL}/{branch.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == branch.id
