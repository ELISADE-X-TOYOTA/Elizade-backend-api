from datetime import datetime, timedelta, timezone

CUSTOMER = "/api/v1/service"
ADMIN = "/api/v1/admin/service"


def _future_slot(days: int = 2) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _book(client, headers, vehicle_id: str, branch_id: str, service_type: str = "recall"):
    return client.post(
        f"{CUSTOMER}/appointments",
        headers=headers,
        json={
            "ownedVehicleId": vehicle_id,
            "branchId": branch_id,
            "serviceType": service_type,
            "scheduledAt": _future_slot(),
            "mileageAtBooking": 12000,
            "issueDescription": "Recall inspection",
        },
    )


def test_recall_booking_is_on_until_an_admin_turns_it_off(client):
    response = client.get(f"{CUSTOMER}/offerings")
    assert response.status_code == 200, response.text
    assert response.json()["recallBookingEnabled"] is True


def test_admin_can_disable_recall_booking(client, admin_headers):
    response = client.patch(
        f"{ADMIN}/offerings",
        headers=admin_headers,
        json={"recallBookingEnabled": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["recallBookingEnabled"] is False
    assert client.get(f"{CUSTOMER}/offerings").json()["recallBookingEnabled"] is False


def test_staff_cannot_change_the_recall_switch(client, staff_headers):
    response = client.patch(
        f"{ADMIN}/offerings",
        headers=staff_headers,
        json={"recallBookingEnabled": False},
    )
    assert response.status_code == 403, response.text


def test_customer_cannot_book_recall_while_it_is_off(
    client, admin_headers, customer_headers, owned_vehicle_factory, branch
):
    client.patch(
        f"{ADMIN}/offerings",
        headers=admin_headers,
        json={"recallBookingEnabled": False},
    )
    response = _book(client, customer_headers, owned_vehicle_factory().id, branch.id)
    assert response.status_code == 400, response.text
    assert "not available" in response.json()["detail"].lower()


def test_other_service_types_still_book_while_recall_is_off(
    client, admin_headers, customer_headers, owned_vehicle_factory, branch
):
    client.patch(
        f"{ADMIN}/offerings",
        headers=admin_headers,
        json={"recallBookingEnabled": False},
    )
    response = _book(
        client, customer_headers, owned_vehicle_factory().id, branch.id, service_type="periodic"
    )
    assert response.status_code == 201, response.text


def test_customer_can_book_recall_while_it_is_on(
    client, customer_headers, owned_vehicle_factory, branch
):
    response = _book(client, customer_headers, owned_vehicle_factory().id, branch.id)
    assert response.status_code == 201, response.text
    assert response.json()["serviceType"] == "recall"
