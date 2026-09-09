"""The two 500s the client-error telemetry caught, and their causes.

Nine HTTP 500s were captured within twenty-five minutes on 9 September, on
`/warranty/eligibility`, `/warranty/claims` and `/auth/otp/request`. The app
renders any 5xx as "Elizade services are temporarily unavailable", so all of
them were reported as an outage. Neither was an outage.

  1. A MALFORMED IDENTIFIER. Every id in this API is a UUID column, and the
     value comes straight from the client into a query. Anything that is not a
     UUID — "undefined", a blank, a demo id — makes psycopg2 raise `invalid
     input syntax for type uuid`, which nothing caught.

  2. A STALE PLACEHOLDER PHONE. Email-only accounts get a synthetic
     `phone_normalized` derived from the address, on a UNIQUE column. It was
     never updated when the email changed, so registering with an address
     somebody had moved away from collided and raised `UniqueViolation`.

Both produced an outage message for a bad request and a stale row.
"""

from app.core.security import is_placeholder_phone, normalize_email, placeholder_phone_for_email
from app.domains.users import service as users_service
from app.domains.users.models import User
from app.domains.users.schemas import UserProfileUpdateIn

AUTH = "/api/v1/auth"
WARRANTY = "/api/v1/warranty"
SALES = "/api/v1/sales"


# ── 1. Malformed identifiers ─────────────────────────────────────────────


def test_a_non_uuid_id_is_a_bad_request_not_a_server_error(client, customer_headers):
    res = client.get(
        f"{WARRANTY}/eligibility", headers=customer_headers,
        params={"ownedVehicleId": "not-a-uuid"},
    )
    assert res.status_code == 400, res.text
    assert res.status_code != 500


def test_a_blank_id_is_a_bad_request(client, customer_headers):
    res = client.get(
        f"{WARRANTY}/eligibility", headers=customer_headers, params={"ownedVehicleId": " "},
    )
    assert res.status_code == 400, res.text


def test_a_malformed_id_in_a_body_is_a_bad_request(client, customer_headers):
    res = client.post(f"{WARRANTY}/claims", headers=customer_headers, json={
        "ownedVehicleId": "undefined", "claimType": "Other",
        "description": "The identifier here is junk.", "attachmentUrls": []})
    assert res.status_code == 400, res.text


def test_the_guard_is_not_warranty_specific(client, customer_headers):
    """173 places take a client id into a query; the fix is at the edge."""
    res = client.post(f"{SALES}/test-drives", headers=customer_headers, json={
        "vehicleId": "not-a-uuid", "branchId": "also-not-a-uuid",
        "scheduledAt": "2027-01-01T10:00:00Z"})
    assert res.status_code == 400, res.text


def test_a_well_formed_but_unknown_id_still_reads_as_missing(client, customer_headers):
    """A real UUID that does not exist is a 404, not a 400 — the distinction
    between 'malformed' and 'not here' has to survive."""
    res = client.get(
        f"{WARRANTY}/eligibility", headers=customer_headers,
        params={"ownedVehicleId": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 404, res.text


# ── 2. The stale placeholder phone ───────────────────────────────────────


def _register(client, email, first="New", last="Person"):
    return client.post(f"{AUTH}/otp/request", json={
        "email": email, "purpose": "register", "firstName": first, "lastName": last})


def test_an_address_someone_moved_away_from_can_be_registered_again(client, db_session):
    """THE REPORTED 500. It is somebody else's registration that breaks."""
    original = "moves.away@elizade.com"
    assert _register(client, original).status_code == 200

    owner = db_session.query(User).filter(User.email == normalize_email(original)).one()
    # Via the sanctioned path: the customer-facing PATCH now refuses an email
    # change outright, because the address is the sign-in credential.
    users_service.change_email_verified(db_session, owner, "now.elsewhere@elizade.com")

    again = _register(client, original, first="Second", last="Person")
    assert again.status_code == 200, again.text


def test_the_placeholder_follows_the_email(client, db_session):
    email = "follows.along@elizade.com"
    _register(client, email)
    user = db_session.query(User).filter(User.email == normalize_email(email)).one()
    assert is_placeholder_phone(user.phone_normalized, email)

    moved = "somewhere.else@elizade.com"
    users_service.change_email_verified(db_session, user, moved)
    db_session.refresh(user)

    assert is_placeholder_phone(user.phone_normalized, moved), (
        "the synthetic phone still encodes the address the customer left"
    )


def test_a_real_phone_number_is_never_rewritten(db_session, customer_user):
    """Only a derived stand-in moves. A number the customer gave us is theirs."""
    customer_user.phone_normalized = "8109998877"
    customer_user.phone_display = "08109998877"
    db_session.commit()

    users_service.change_email_verified(db_session, customer_user, "brand.new@elizade.com")
    db_session.refresh(customer_user)

    assert customer_user.phone_normalized == "8109998877"


def test_a_legacy_stale_row_does_not_block_registration(client, db_session):
    """Rows written before the fix still hold placeholders for addresses they
    no longer own. A customer must not pay for that."""
    stranded = "legacy.holder@elizade.com"
    taken_norm, _ = placeholder_phone_for_email(stranded)
    db_session.add(User(
        phone_normalized=taken_norm, phone_display="legacy",
        first_name="Legacy", last_name="Row", email="different.address@elizade.com",
        is_active=True,
    ))
    db_session.commit()

    res = _register(client, stranded)

    assert res.status_code == 200, res.text
    created = db_session.query(User).filter(User.email == normalize_email(stranded)).one()
    assert created.phone_normalized != taken_norm
