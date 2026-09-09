"""What a deactivated customer is told, and what they cannot do.

Registration answered "Account already exists." — true, unhelpful, and
indistinguishable from an ordinary duplicate. Sign-in said "Contact admin.",
naming somebody the customer has no way to reach. So a person whose account had
been disabled was sent round a loop: they could not sign in, could not register,
and neither message said why or where to go.

Worse, they could get back in anyway. `verify_otp` set `is_active = True`
unconditionally, so re-registering silently undid the deactivation.
"""

import pytest

from app.core.config import get_settings
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

AUTH = "/api/v1/auth"


@pytest.fixture
def deactivated(db_session):
    user = User(
        phone_normalized="8100000555",
        phone_display="08100000555",
        first_name="Disabled",
        last_name="Person",
        email="disabled.person@elizade.com",
        role=UserRole.customer,
        is_verified=True,
        is_active=False,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, email):
    return client.post(f"{AUTH}/otp/request", json={"email": email, "purpose": "login"})


def _register(client, email):
    return client.post(f"{AUTH}/otp/request", json={
        "email": email, "purpose": "register", "firstName": "Dis", "lastName": "Abled"})


def test_signing_in_explains_the_deactivation(client, deactivated):
    res = _login(client, deactivated.email)

    assert res.status_code == 403
    detail = res.json()["detail"]
    assert "deactivated" in detail.lower(), detail
    assert "admin" not in detail.lower(), "naming an 'admin' gives them nobody to contact"


def test_registering_says_the_same_thing(client, deactivated):
    """THE REPORTED DEFECT. It used to say "Account already exists."."""
    res = _register(client, deactivated.email)

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "deactivated" in detail.lower(), detail
    assert "already exists" not in detail.lower(), detail


def test_both_messages_name_the_support_address(client, deactivated):
    support = get_settings().support_email
    assert support in _login(client, deactivated.email).json()["detail"]
    assert support in _register(client, deactivated.email).json()["detail"]


def test_registering_cannot_silently_reactivate(client, db_session, deactivated):
    """Registration must not undo a moderation decision.

    `request_otp` refuses first, so this is the second gate — but a silent
    reactivation is exactly what survives when only one gate holds it.
    """
    _register(client, deactivated.email)
    db_session.refresh(deactivated)

    assert deactivated.is_active is False


def test_an_active_duplicate_still_says_duplicate(client, customer_user, db_session):
    """The clearer message must not swallow the ordinary case."""
    customer_user.email = "active.dupe@elizade.com"
    db_session.commit()

    res = _register(client, "active.dupe@elizade.com")

    assert res.status_code == 409
    assert "already exists" in res.json()["detail"].lower()


def test_an_unknown_email_can_still_register(client):
    assert _register(client, "brand.new.person@elizade.com").status_code == 200
