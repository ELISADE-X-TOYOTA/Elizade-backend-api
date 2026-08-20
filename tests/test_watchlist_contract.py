"""Watchlist behaviours the mobile client depends on.

`test_customer_apis_complete.py` already covers the happy-path CRUD. These pin
the edges the app builds real UI decisions on — chiefly the 409, which the
client turns into "you're already tracking the X" rather than a raw conflict.
"""

import pytest

from app.core.security import create_access_token
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

WATCHLIST = "/api/v1/watchlist"


@pytest.fixture
def other_customer_headers(db_session) -> dict[str, str]:
    user = User(
        phone_normalized="8100000022",
        phone_display="08100000022",
        first_name="Ada",
        last_name="Nwosu",
        email="watch.other@elizade.test",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _add(client, headers, **kw):
    return client.post(WATCHLIST, headers=headers, json={"model": "Land Cruiser", **kw})


# ── Uniqueness is on MODEL alone ─────────────────────────────────────────


def test_duplicate_model_conflicts_even_with_a_different_trim(client, customer_headers):
    """The app disables 'track' per model because of exactly this."""
    assert _add(client, customer_headers, trim="300 VX", color="Black").status_code == 201

    dupe = _add(client, customer_headers, trim="GR Sport", color="White")
    assert dupe.status_code == 409, "trim/colour must NOT create a second entry"


def test_a_removed_model_can_be_tracked_again(client, customer_headers):
    """Delete is a soft delete; re-adding must still work afterwards."""
    item_id = _add(client, customer_headers, trim="300 VX").json()["id"]
    assert client.delete(f"{WATCHLIST}/{item_id}", headers=customer_headers).status_code == 204
    assert _add(client, customer_headers, trim="GR Sport").status_code == 201


def test_two_customers_can_track_the_same_model(client, customer_headers, other_customer_headers):
    assert _add(client, customer_headers).status_code == 201
    assert _add(client, other_customer_headers).status_code == 201


# ── Optional fields ──────────────────────────────────────────────────────


def test_trim_and_colour_are_optional(client, customer_headers):
    res = _add(client, customer_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["trim"] is None and body["color"] is None


def test_blank_strings_are_stored_as_null(client, customer_headers):
    """The sheet sends '' for an emptied field; it must not persist as ''."""
    res = _add(client, customer_headers, trim="   ", color="")
    assert res.status_code == 201
    assert res.json()["trim"] is None
    assert res.json()["color"] is None


def test_model_is_required(client, customer_headers):
    assert client.post(WATCHLIST, headers=customer_headers, json={"trim": "VX"}).status_code == 422
    assert client.post(WATCHLIST, headers=customer_headers, json={"model": ""}).status_code == 422


# ── Ownership scoping ────────────────────────────────────────────────────


def test_cannot_patch_another_customers_item(client, customer_headers, other_customer_headers):
    item_id = _add(client, customer_headers).json()["id"]
    res = client.patch(
        f"{WATCHLIST}/{item_id}", headers=other_customer_headers, json={"trim": "hijacked"}
    )
    # 404 rather than 403 — a 403 would confirm the id exists.
    assert res.status_code == 404


def test_cannot_delete_another_customers_item(client, customer_headers, other_customer_headers):
    item_id = _add(client, customer_headers).json()["id"]
    assert client.delete(f"{WATCHLIST}/{item_id}", headers=other_customer_headers).status_code == 404
    # Still tracked by its real owner.
    assert any(i["id"] == item_id for i in client.get(WATCHLIST, headers=customer_headers).json())


def test_list_is_scoped_to_the_caller(client, customer_headers, other_customer_headers):
    _add(client, customer_headers, trim="Mine")
    assert client.get(WATCHLIST, headers=other_customer_headers).json() == []
