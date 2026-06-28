"""Analytics overview API tests."""


def test_analytics_requires_auth(client):
    assert client.get("/api/v1/admin/analytics/overview").status_code == 401


def test_analytics_overview(client, staff_headers):
    res = client.get("/api/v1/admin/analytics/overview", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert "inventoryByModel" in data
    assert "customersTotal" in data
    assert "openSupportTickets" in data
    assert "pendingWarrantyClaims" in data
    assert isinstance(data["supportByCategory"], list)
    assert isinstance(data["warrantyClaimsByStatus"], list)
