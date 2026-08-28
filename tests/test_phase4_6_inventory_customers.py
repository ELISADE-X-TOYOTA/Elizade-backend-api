from datetime import datetime, timedelta, timezone

from app.domains.audit.models import AuditLog
from app.domains.customers.models import CustomerDuplicateReview, OwnedVehicle
from app.domains.inventory.models import VehicleAvailabilitySubscription
from app.domains.notifications.models import UserNotification
from app.domains.shared.enums import AvailabilityStatus, AuditAction
from app.domains.users.models import User, UserRole


def test_notify_me_subscription_notifies_once_on_availability_transition(
    client, customer_headers, admin_headers, customer_user, vehicle_factory, db_session
):
    vehicle = vehicle_factory(availability=AvailabilityStatus.sold)

    status_response = client.get(f"/api/v1/vehicles/{vehicle.id}/notify-me", headers=customer_headers)
    assert status_response.status_code == 200
    assert status_response.json()["subscribed"] is False

    response = client.post(f"/api/v1/vehicles/{vehicle.id}/notify-me", headers=customer_headers)
    assert response.status_code == 201
    assert response.json()["subscribed"] is True
    subscription_id = response.json()["subscriptionId"]

    status_response = client.get(f"/api/v1/vehicles/{vehicle.id}/notify-me", headers=customer_headers)
    assert status_response.status_code == 200
    assert status_response.json()["subscribed"] is True

    response = client.patch(
        f"/api/v1/admin/vehicles/{vehicle.id}/status",
        json={"availability": "available"},
        headers=admin_headers,
    )
    assert response.status_code == 200

    notification = (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == customer_user.id)
        .one()
    )
    assert "availability update" in notification.title
    subscription = db_session.get(VehicleAvailabilitySubscription, subscription_id)
    assert subscription.is_active is False
    assert subscription.notified_at is not None


def test_future_publication_is_hidden_until_utc_instant(client, admin_headers, branch):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = client.post(
        "/api/v1/admin/vehicles",
        json={
            "model": "Scheduled",
            "trim": "LE",
            "year": 2025,
            "color": "White",
            "colorHex": "#FFFFFF",
            "price": 25000000,
            "fuelType": "Petrol",
            "transmission": "Automatic",
            "engine": "1.8L",
            "branchId": branch.id,
            "publishedAt": future,
            "isPublished": True,
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    vehicle_id = response.json()["id"]
    assert client.get(f"/api/v1/vehicles/{vehicle_id}").status_code == 404


def test_publication_schedule_requires_timezone_offset(client, admin_headers, branch):
    response = client.post(
        "/api/v1/admin/vehicles",
        json={
            "model": "Ambiguous",
            "trim": "LE",
            "year": 2025,
            "color": "White",
            "price": 25000000,
            "fuelType": "Petrol",
            "transmission": "Automatic",
            "engine": "1.8L",
            "branchId": branch.id,
            "publishedAt": "2030-01-01T10:00:00",
        },
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "timezone" in response.json()["detail"]


def test_duplicate_review_merge_reassigns_records_and_audits(
    client, customer_user, admin_headers, db_session, owned_vehicle_factory
):
    source = User(
        phone_normalized="8100000999",
        phone_display="08100000999",
        email="duplicate@elizade.test",
        first_name=customer_user.first_name,
        last_name=customer_user.last_name,
        city=customer_user.city,
        state=customer_user.state,
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    owned_vehicle_factory(owner=source, vin="DUPMERGE000000001")

    candidates = client.get("/api/v1/admin/customers/duplicates", headers=admin_headers)
    assert candidates.status_code == 200
    candidate = next(
        item
        for item in candidates.json()
        if {item["customerId"], item["duplicateCustomerId"]}
        == {source.id, customer_user.id}
    )

    reviewed = client.patch(
        f"/api/v1/admin/customers/duplicates/{candidate['id']}",
        json={"status": "confirmed"},
        headers=admin_headers,
    )
    assert reviewed.status_code == 200

    merged = client.post(
        "/api/v1/admin/customers/merge",
        json={"sourceCustomerId": source.id, "targetCustomerId": customer_user.id},
        headers=admin_headers,
    )
    assert merged.status_code == 200
    assert merged.json()["mergedCustomerId"] == source.id
    assert merged.json()["survivingCustomerId"] == customer_user.id
    assert db_session.query(OwnedVehicle).filter(OwnedVehicle.user_id == source.id).count() == 0
    assert db_session.get(User, source.id).is_active is False
    review = db_session.get(CustomerDuplicateReview, candidate["id"])
    assert review.status.value == "merged"
    audit = db_session.get(AuditLog, merged.json()["auditId"])
    assert audit.action == AuditAction.merge
