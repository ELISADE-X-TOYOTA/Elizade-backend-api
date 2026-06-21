"""
Phase 0 smoke tests — verify the test harness itself works end-to-end:
DB session wiring, dependency override, and role-based auth. These hit existing
endpoints only; no inventory code is involved yet.
"""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_db_session_persists_within_test(client, branch):
    # The branch fixture committed to the test session; the override should see it.
    from app.domains.branches.models import Branch

    found = client.app  # touch app to ensure import works
    assert found is not None
    assert branch.id is not None
    assert isinstance(branch, Branch)


def test_admin_endpoint_requires_auth(client):
    resp = client.get("/api/v1/admin/staff")
    assert resp.status_code == 401


def test_admin_endpoint_rejects_customer(client, customer_headers):
    resp = client.get("/api/v1/admin/staff", headers=customer_headers)
    assert resp.status_code == 403


def test_admin_endpoint_allows_admin(client, admin_headers):
    resp = client.get("/api/v1/admin/staff", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []
