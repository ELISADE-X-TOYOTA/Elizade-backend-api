"""Warranty-eligibility and service-history behaviours the mobile app relies on.

Both endpoints already have happy-path coverage elsewhere. These pin the two
guarantees the client actually builds on:

* the eligibility check reports the INELIGIBLE case honestly, because the app
  now uses it to disable the claim button before the customer writes anything;
* `?vehicleId=` genuinely EXCLUDES other vehicles. The garage screen dropped its
  client-side filter in favour of this, so a filter that silently returned
  everything would put another car's service records on the wrong vehicle.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

WARRANTY = "/api/v1/warranty"
SERVICE = "/api/v1/service"


@pytest.fixture
def other_customer(db_session) -> User:
    user = User(
        phone_normalized="8100000033",
        phone_display="08100000033",
        first_name="Bola",
        last_name="Ade",
        email="ws.other@elizade.test",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# ── Warranty eligibility ─────────────────────────────────────────────────


def test_eligibility_returns_every_field_the_client_renders(
    client, customer_headers, owned_vehicle_factory
):
    owned = owned_vehicle_factory(purchase_date=datetime.now(timezone.utc), mileage=5_000)
    res = client.get(f"{WARRANTY}/eligibility", params={"ownedVehicleId": owned.id}, headers=customer_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    for key in (
        "eligible", "reason", "inServiceDate", "coverageEnd",
        "mileageLimitKm", "warrantyMonths", "currentMileage", "certificateNumber",
    ):
        assert key in body, f"{key} missing — the app's DTO declares it"
    assert body["eligible"] is True
    assert body["currentMileage"] == 5_000


def test_eligibility_reports_an_out_of_cover_vehicle(
    client, customer_headers, owned_vehicle_factory
):
    """The claim sheet disables submit on this, so it has to be truthful."""
    old = datetime.now(timezone.utc) - timedelta(days=365 * 5)
    owned = owned_vehicle_factory(vin="JTDB1234567890777", purchase_date=old, mileage=180_000)

    body = client.get(
        f"{WARRANTY}/eligibility", params={"ownedVehicleId": owned.id}, headers=customer_headers
    ).json()
    assert body["eligible"] is False
    # A reason is what the UI shows instead of a generic message.
    assert body["reason"]


def test_ineligible_vehicle_is_also_refused_at_submit(
    client, customer_headers, owned_vehicle_factory
):
    """The pre-check is a courtesy; the server stays the real gate."""
    old = datetime.now(timezone.utc) - timedelta(days=365 * 5)
    owned = owned_vehicle_factory(vin="JTDB1234567890778", purchase_date=old, mileage=180_000)

    res = client.post(
        f"{WARRANTY}/claims",
        headers=customer_headers,
        json={
            "ownedVehicleId": owned.id,
            "claimType": "Powertrain",
            "description": "Gearbox whine under load, started last week.",
        },
    )
    assert res.status_code == 422


def test_eligibility_404s_on_another_customers_vehicle(
    client, customer_headers, other_customer, owned_vehicle_factory
):
    theirs = owned_vehicle_factory(owner=other_customer, vin="JTDB1234567890779")
    res = client.get(
        f"{WARRANTY}/eligibility", params={"ownedVehicleId": theirs.id}, headers=customer_headers
    )
    # 404 not 403 — a 403 would confirm the id exists.
    assert res.status_code == 404


def test_eligibility_requires_the_vehicle_id(client, customer_headers):
    assert client.get(f"{WARRANTY}/eligibility", headers=customer_headers).status_code == 422


# ── Service history filtering ────────────────────────────────────────────


def _history(db_session, owned, branch, *, description: str, days_ago: int = 1):
    from app.domains.service.models import ServiceHistoryItem

    db_session.add(
        ServiceHistoryItem(
            owned_vehicle_id=owned.id,
            user_id=owned.user_id,
            branch_id=branch.id,
            service_type="periodic",
            performed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
            mileage=10_000,
            description=description,
            cost=45_000,
        )
    )
    db_session.commit()


def test_vehicle_filter_excludes_other_vehicles(
    client, customer_headers, owned_vehicle_factory, branch, db_session
):
    """The garage screen deleted its client-side filter relying on this."""
    car_a = owned_vehicle_factory(vin="JTDB1234567890AAA")
    car_b = owned_vehicle_factory(vin="JTDB1234567890BBB", model="Hilux")
    _history(db_session, car_a, branch, description="Car A oil change")
    _history(db_session, car_b, branch, description="Car B brake pads")

    body = client.get(f"{SERVICE}/history", params={"vehicleId": car_a.id}, headers=customer_headers).json()
    descriptions = [i["description"] for i in body["items"]]
    assert "Car A oil change" in descriptions
    assert "Car B brake pads" not in descriptions, "filter returned another vehicle's history"
    assert body["total"] == 1


def test_omitting_the_filter_returns_every_vehicle(
    client, customer_headers, owned_vehicle_factory, branch, db_session
):
    car_a = owned_vehicle_factory(vin="JTDB1234567890CCC")
    car_b = owned_vehicle_factory(vin="JTDB1234567890DDD", model="Hilux")
    _history(db_session, car_a, branch, description="A service")
    _history(db_session, car_b, branch, description="B service")

    body = client.get(f"{SERVICE}/history", headers=customer_headers).json()
    assert body["total"] == 2


def test_history_is_scoped_to_the_caller(
    client, customer_headers, other_customer, owned_vehicle_factory, branch, db_session
):
    theirs = owned_vehicle_factory(owner=other_customer, vin="JTDB1234567890EEE")
    _history(db_session, theirs, branch, description="Not yours")

    body = client.get(f"{SERVICE}/history", headers=customer_headers).json()
    assert all(i["description"] != "Not yours" for i in body["items"])


def test_filtering_by_another_customers_vehicle_leaks_nothing(
    client, customer_headers, other_customer, owned_vehicle_factory, branch, db_session
):
    theirs = owned_vehicle_factory(owner=other_customer, vin="JTDB1234567890FFF")
    _history(db_session, theirs, branch, description="Not yours either")

    res = client.get(f"{SERVICE}/history", params={"vehicleId": theirs.id}, headers=customer_headers)
    assert res.status_code in (200, 404)
    if res.status_code == 200:
        assert res.json()["items"] == []
