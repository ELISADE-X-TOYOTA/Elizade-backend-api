from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole


def test_get_profile_requires_auth(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_get_profile(client, customer_user, customer_headers):
    response = client.get("/api/v1/users/me", headers=customer_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == customer_user.id
    assert data["firstName"] == customer_user.first_name
    assert data["email"] == customer_user.email
    assert "preferences" in data


def test_patch_profile_city(client, customer_user, customer_headers, db_session):
    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"city": "Ibadan"},
    )
    assert response.status_code == 200
    assert response.json()["city"] == "Ibadan"

    db_session.refresh(customer_user)
    assert customer_user.city == "Ibadan"


def test_patch_profile_rejects_empty_first_name(client, customer_headers):
    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"firstName": "   "},
    )
    assert response.status_code == 400
    assert "First name cannot be empty" in response.json()["detail"]


def test_patch_profile_duplicate_email(client, db_session, customer_headers):
    conflict = User(
        phone_normalized="8100000099",
        phone_display="08100000099",
        email="other@elizade.com",
        first_name="Other",
        last_name="User",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(conflict)
    db_session.commit()

    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"email": "other@elizade.com"},
    )
    assert response.status_code == 409
    assert "Email already in use" in response.json()["detail"]


def test_customer_cannot_update_department(client, customer_headers):
    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"department": "Sales"},
    )
    assert response.status_code == 403


def test_staff_can_update_department(client, staff_user, staff_headers, db_session):
    response = client.patch(
        "/api/v1/users/me",
        headers=staff_headers,
        json={"department": "Aftersales"},
    )
    assert response.status_code == 200
    assert response.json()["department"] == "Aftersales"

    db_session.refresh(staff_user)
    assert staff_user.department == "Aftersales"


def test_patch_preferences(client, customer_user, customer_headers, db_session):
    response = client.patch(
        "/api/v1/users/me/preferences",
        headers=customer_headers,
        json={"pushEnabled": False, "marketingOptIn": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pushEnabled"] is False
    assert data["marketingOptIn"] is True
    assert data["smsEnabled"] is True

    db_session.refresh(customer_user)
    assert customer_user.preferences["push_enabled"] is False
    assert customer_user.preferences["marketing_opt_in"] is True


def test_get_preferences_defaults_public(client):
    response = client.get("/api/v1/users/preferences/defaults")
    assert response.status_code == 200
    data = response.json()
    assert data["pushEnabled"] is True
    assert data["marketingOptIn"] is False
