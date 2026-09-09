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
    # 403, NOT 409. The registered email is now locked on this endpoint
    # regardless of whether the target address is free, because the address is
    # the sign-in credential — a session that can move it can transfer the
    # account. The duplicate check still exists, on `change_email_verified`,
    # which support uses once identity is established.
    assert response.status_code == 403
    assert "cannot be changed here" in response.json()["detail"]


def test_the_lock_names_somewhere_to_go(client, customer_headers):
    """A refusal that does not say what to do next just moves the dead end."""
    response = client.patch(
        "/api/v1/users/me", headers=customer_headers, json={"email": "new.address@elizade.com"}
    )
    assert response.status_code == 403
    assert "@" in response.json()["detail"], "the message must name the support address"


def test_the_other_fields_are_still_editable(client, customer_headers):
    """Locking the email must not lock the form."""
    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"firstName": "Renamed", "lastName": "Person", "city": "Abuja"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["firstName"] == "Renamed"
    assert body["city"] == "Abuja"


def test_sending_the_unchanged_email_is_not_an_error(
    client, customer_headers, customer_user, db_session
):
    """The app posts the whole form; an untouched email field must not 403.

    The fixture's address is on `.test`, a reserved TLD that `EmailStr`
    refuses, so it is moved to a real domain first — otherwise this 422s at
    validation and proves nothing about the lock.
    """
    customer_user.email = "unchanged.probe@elizade.com"
    db_session.commit()

    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"email": "unchanged.probe@elizade.com", "city": "Ibadan"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["city"] == "Ibadan"


def test_the_comparison_ignores_case_and_padding(client, customer_headers, customer_user, db_session):
    """`Faith@X.com` and `faith@x.com` are the same address, not a change."""
    customer_user.email = "casing.probe@elizade.com"
    db_session.commit()

    response = client.patch(
        "/api/v1/users/me",
        headers=customer_headers,
        json={"email": "  Casing.Probe@Elizade.com  "},
    )
    assert response.status_code == 200, response.text


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
