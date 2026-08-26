"""The /auth/refresh and /auth/logout endpoints, over HTTP.

`test_refresh_tokens.py` covers the rotation logic directly. These cover the
wire contract the mobile client depends on: the field names it reads, the
status codes it branches on, and the fact that refresh works WITHOUT a bearer
token — which is the whole point, since it is called precisely when the access
token is no longer accepted.
"""

from app.core.security import create_access_token
from app.domains.auth import refresh as refresh_service


def test_refresh_returns_a_new_pair(client, db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    res = client.post("/api/v1/auth/refresh", json={"refreshToken": token})

    assert res.status_code == 200
    body = res.json()
    # The client reads these exact snake_case keys.
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["refresh_token"] != token, "the token must rotate"


def test_refresh_needs_no_bearer_token(client, db_session, customer_user):
    """It must work when the access token is dead — no Authorization header."""
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    res = client.post("/api/v1/auth/refresh", json={"refreshToken": token})
    assert res.status_code == 200


def test_the_new_access_token_actually_works(client, db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    access = client.post("/api/v1/auth/refresh", json={"refreshToken": token}).json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == customer_user.email


def test_reused_token_gives_401(client, db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()
    client.post("/api/v1/auth/refresh", json={"refreshToken": token})

    res = client.post("/api/v1/auth/refresh", json={"refreshToken": token})
    assert res.status_code == 401


def test_unknown_token_gives_401_not_500(client):
    res = client.post("/api/v1/auth/refresh", json={"refreshToken": "totally-made-up-value"})
    assert res.status_code == 401


def test_failures_do_not_say_why(client, db_session, customer_user):
    """Distinguishing expired / revoked / unknown would help someone probing.

    Both probes are well-formed tokens. A malformed one (under the schema's
    minimum length) is a different case — that is a bad REQUEST and correctly
    gets a 422, and no token we ever issued could be that short.
    """
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()
    client.post("/api/v1/auth/refresh", json={"refreshToken": token})

    reused = client.post("/api/v1/auth/refresh", json={"refreshToken": token}).json()
    # Same shape as a real token (43 url-safe chars), just never issued.
    unknown = client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": "x" * 43},
    ).json()
    assert reused["detail"] == unknown["detail"]


def test_logout_revokes_the_session(client, db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    assert client.post("/api/v1/auth/logout", json={"refreshToken": token}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": token}).status_code == 401


def test_logout_is_204_even_for_an_unknown_token(client):
    """Sign-out must not report whether the token was real."""
    res = client.post("/api/v1/auth/logout", json={"refreshToken": "never-existed-at-all"})
    assert res.status_code == 204


def test_a_valid_access_token_is_unaffected_by_refresh(client, db_session, customer_user):
    """Rotating must not invalidate an access token already in flight."""
    existing = create_access_token(customer_user.id)
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    client.post("/api/v1/auth/refresh", json={"refreshToken": token})

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {existing}"})
    assert me.status_code == 200, "in-flight requests must not be broken by a refresh"
