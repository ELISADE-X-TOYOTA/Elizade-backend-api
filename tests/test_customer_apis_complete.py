"""Comprehensive customer API tests — support, sales, watchlist, service, dashboard."""

from datetime import datetime, timedelta, timezone

SUPPORT = "/api/v1/support/tickets"
SALES = "/api/v1/sales"
SERVICE = "/api/v1/service"
WATCHLIST = "/api/v1/watchlist"
DASHBOARD = "/api/v1/dashboard/summary"


def test_customer_endpoints_require_auth(client):
    assert client.get(SUPPORT).status_code == 401
    assert client.get(f"{SALES}/quotations").status_code == 401
    assert client.get(WATCHLIST).status_code == 401
    assert client.get(f"{SERVICE}/history").status_code == 401
    assert client.get(DASHBOARD).status_code == 401


def test_customer_endpoints_reject_staff(client, staff_headers):
    assert client.get(SUPPORT, headers=staff_headers).status_code == 403
    assert client.get(f"{SALES}/quotations", headers=staff_headers).status_code == 403
    assert client.get(WATCHLIST, headers=staff_headers).status_code == 403
    assert client.get(DASHBOARD, headers=staff_headers).status_code == 403


# --- Support ---


def test_customer_support_ticket_flow(client, customer_headers, staff_headers, db_session, customer_user):
    created = client.post(
        SUPPORT,
        headers=customer_headers,
        json={
            "category": "service",
            "subject": "Delayed service appointment",
            "body": "My car has been waiting since Monday morning.",
            "priority": "medium",
        },
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]
    assert created.json()["status"] == "open"

    listed = client.get(SUPPORT, headers=customer_headers).json()
    assert any(t["id"] == ticket_id for t in listed)

    replied = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "Any update on this?"},
    )
    assert replied.status_code == 200
    assert len(replied.json()["ticket"]["messages"]) >= 2

    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/resolve",
        headers=staff_headers,
    )
    rated = client.post(
        f"{SUPPORT}/{ticket_id}/rate",
        headers=customer_headers,
        json={"rating": 5},
    )
    assert rated.status_code == 200
    assert rated.json()["satisfactionRating"] == 5


# --- Sales: quotations, reservations, trade-ins ---


def test_request_quotation(client, customer_headers, vehicle_factory):
    vehicle = vehicle_factory()
    resp = client.post(
        f"{SALES}/quotations",
        headers=customer_headers,
        json={"vehicleId": vehicle.id},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "sent"
    assert resp.json()["vehicleId"] == vehicle.id

    listed = client.get(f"{SALES}/quotations", headers=customer_headers).json()
    assert len(listed) >= 1


def test_create_reservation(client, customer_headers, vehicle_factory):
    vehicle = vehicle_factory()
    resp = client.post(
        f"{SALES}/reservations",
        headers=customer_headers,
        json={"vehicleId": vehicle.id, "depositAmount": 500000},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"

    listed = client.get(f"{SALES}/reservations", headers=customer_headers).json()
    assert len(listed) >= 1


def test_submit_trade_in(client, customer_headers):
    resp = client.post(
        f"{SALES}/trade-ins",
        headers=customer_headers,
        json={
            "make": "Toyota",
            "model": "Camry",
            "year": 2018,
            "mileage": 85000,
            "conditionNotes": "Good condition, minor scratch on rear bumper.",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "submitted"

    listed = client.get(f"{SALES}/trade-ins", headers=customer_headers).json()
    assert len(listed) >= 1


# --- Watchlist ---


def test_watchlist_crud(client, customer_headers):
    created = client.post(
        WATCHLIST,
        headers=customer_headers,
        json={"model": "RAV4", "trim": "XLE", "color": "White"},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    listed = client.get(WATCHLIST, headers=customer_headers).json()
    assert any(i["id"] == item_id for i in listed)

    updated = client.patch(
        f"{WATCHLIST}/{item_id}",
        headers=customer_headers,
        json={"color": "Black"},
    )
    assert updated.status_code == 200
    assert updated.json()["color"] == "Black"

    deleted = client.delete(f"{WATCHLIST}/{item_id}", headers=customer_headers)
    assert deleted.status_code == 204
    assert client.get(WATCHLIST, headers=customer_headers).json() == []


# --- Service: book appointment + history ---


def test_book_service_appointment(client, customer_headers, owned_vehicle_factory, branch):
    owned = owned_vehicle_factory()
    scheduled = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    resp = client.post(
        f"{SERVICE}/appointments",
        headers=customer_headers,
        json={
            "ownedVehicleId": owned.id,
            "branchId": branch.id,
            "serviceType": "periodic",
            "scheduledAt": scheduled.isoformat().replace("+00:00", "Z"),
            "mileageAtBooking": 12000,
            "issueDescription": "10,000 km periodic service due",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "requested"
    assert resp.json()["vehicleId"] == owned.id


def test_customer_service_history(client, customer_headers, staff_headers, owned_vehicle_factory, branch, db_session):
    from app.domains.service.models import ServiceHistoryItem

    owned = owned_vehicle_factory()
    db_session.add(
        ServiceHistoryItem(
            owned_vehicle_id=owned.id,
            user_id=owned.user_id,
            branch_id=branch.id,
            service_type="periodic",
            performed_at=datetime.now(timezone.utc),
            mileage=10000,
            description="Oil change and filter replacement",
            cost=45000,
        )
    )
    db_session.commit()

    resp = client.get(f"{SERVICE}/history?vehicleId={owned.id}", headers=customer_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert resp.json()["items"][0]["vehicleLabel"] == "2022 Toyota Corolla"


def test_customer_history_rejects_admin_route(client, customer_headers):
    assert client.get("/api/v1/admin/service/history", headers=customer_headers).status_code == 403


# --- Dashboard ---


def test_customer_dashboard_summary(client, customer_headers, owned_vehicle_factory, appointment_factory):
    owned_vehicle_factory(is_primary=True)
    appointment_factory()

    resp = client.get(DASHBOARD, headers=customer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ownedVehiclesCount"] >= 1
    assert body["primaryVehicle"] is not None
    assert body["upcomingAppointments"] >= 1
    assert "unreadNotifications" in body
    assert "watchlistCount" in body
