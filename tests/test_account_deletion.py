"""A customer deleting their own account.

Apple (5.1.1(v)) and Google Play require it, and the public page at
elizade-web.vercel.app/delete-account.html promises what goes and what stays.
These tests hold the endpoint to that page.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.core.security import create_access_token
from app.domains.audit.models import AuditLog
from app.domains.customers.models import OwnedVehicle, WatchlistItem
from app.domains.sales.models import TradeInRequest
from app.domains.shared.enums import (
    MessageSender,
    TicketCategory,
    WarrantyCertificateStatus,
    WarrantyCertificateType,
)
from app.domains.support.models import SupportTicket, TicketMessage
from app.domains.users import deletion
from app.domains.users.models import OtpChallenge, RefreshToken, User, UserRole
from app.domains.warranty.models import WarrantyCertificate

CODE = "482913"
REVIEW_EMAIL = "appreview@elizade.com"
REVIEW_CODE = "334567"


@pytest.fixture(autouse=True)
def fixed_code(monkeypatch):
    """Every emailed code is CODE, so a test can type it back."""
    monkeypatch.setattr("app.services.otp.generate_otp_code", lambda: CODE)


@pytest.fixture(autouse=True)
def no_storage(monkeypatch):
    """Record which files would be removed instead of touching storage."""
    removed: list = []
    monkeypatch.setattr(deletion, "purge_files", lambda files: removed.append(files))
    return removed


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _delete(client, user: User, code: str = CODE):
    sent = client.post("/api/v1/users/me/deletion-code", headers=_headers(user))
    assert sent.status_code == 200, sent.text
    return client.post("/api/v1/users/me/delete", json={"code": code}, headers=_headers(user))


@pytest.fixture
def full_customer(db_session, customer_user, owned_vehicle_factory):
    """A customer with something in every category the page names."""
    uid = customer_user.id
    customer_user.avatar_url = "https://cdn.example/customer-avatars/me.jpg"

    spare = owned_vehicle_factory(vin="JTDSPARE000000001", registration_number="LAG-1")
    covered = owned_vehicle_factory(vin="JTDCOVER000000002", registration_number="LAG-2")
    db_session.add(
        WarrantyCertificate(
            user_id=uid,
            owned_vehicle_id=covered.id,
            certificate_number="ELZ-WTY-DEL-1",
            type=list(WarrantyCertificateType)[0],
            status=WarrantyCertificateStatus.active,
            coverage_start=_now() - timedelta(days=30),
            coverage_end=_now() + timedelta(days=300),
        )
    )
    ticket = SupportTicket(
        ticket_number="SUP-DEL-1",
        user_id=uid,
        category=TicketCategory.service,
        subject="Noise from the brakes",
        first_response_due=_now() + timedelta(hours=4),
        resolution_due=_now() + timedelta(days=2),
    )
    db_session.add(ticket)
    db_session.flush()
    db_session.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_type=list(MessageSender)[0],
            body="Photo attached",
            attachments=["https://cdn.example/customer-support/brake.jpg"],
        )
    )
    db_session.add(WatchlistItem(user_id=uid, model="RAV4"))
    db_session.add(
        TradeInRequest(
            user_id=uid,
            make="Toyota",
            model="Corolla",
            year=2015,
            mileage=120000,
            condition_notes="Good",
            photo_urls=["https://cdn.example/customer-trade-ins/front.jpg"],
        )
    )
    db_session.add(
        RefreshToken(
            user_id=uid,
            token_hash="a" * 64,
            family_id="00000000-0000-0000-0000-000000000001",
            expires_at=_now() + timedelta(days=30),
        )
    )
    db_session.commit()
    return {"user": customer_user, "spare": spare.id, "covered": covered.id, "ticket": ticket.id}


# ── The flow ───────────────────────────────────────────────────────────────


def test_requesting_a_code_emails_one(client, db_session, customer_user):
    res = client.post("/api/v1/users/me/deletion-code", headers=_headers(customer_user))
    assert res.status_code == 200, res.text
    assert res.json()["expiresInMinutes"] > 0
    assert db_session.query(OtpChallenge).filter(OtpChallenge.email == customer_user.email).count() == 1


def test_deleting_removes_what_the_page_says(client, db_session, full_customer, no_storage):
    user = full_customer["user"]
    uid = user.id
    email = user.email

    res = _delete(client, user)
    assert res.status_code == 204, res.text

    db_session.expire_all()
    row = db_session.get(User, uid)
    # The row stays as an anonymised placeholder for the kept records.
    assert row.email is None
    assert (row.first_name, row.last_name) == ("Deleted", "customer")
    assert row.avatar_url is None and row.phone_display == ""
    assert row.is_active is False
    assert not any(row.preferences.values())

    assert db_session.query(SupportTicket).filter_by(user_id=uid).count() == 0
    assert db_session.query(TicketMessage).filter_by(ticket_id=full_customer["ticket"]).count() == 0
    assert db_session.query(WatchlistItem).filter_by(user_id=uid).count() == 0
    assert db_session.query(RefreshToken).filter_by(user_id=uid).count() == 0
    assert db_session.query(OtpChallenge).filter(OtpChallenge.email == email).count() == 0

    # Photos come off the kept trade-in record.
    trade = db_session.query(TradeInRequest).filter_by(user_id=uid).one()
    assert trade.photo_urls == []

    # A vehicle nothing depends on goes; one under warranty is the VIN record.
    assert db_session.get(OwnedVehicle, full_customer["spare"]) is None
    assert db_session.get(OwnedVehicle, full_customer["covered"]) is not None
    assert db_session.query(WarrantyCertificate).filter_by(user_id=uid).count() == 1

    # Uploaded files are handed over for removal from storage.
    (files,) = no_storage
    assert files["avatar"] == ["https://cdn.example/customer-avatars/me.jpg"]
    assert files["support"] == ["https://cdn.example/customer-support/brake.jpg"]
    assert files["trade_in"] == ["https://cdn.example/customer-trade-ins/front.jpg"]

    # Recorded, without personal data.
    audit = db_session.query(AuditLog).filter_by(entity_type="user_account", entity_id=uid).one()
    assert email not in str(audit.changes)


def test_the_old_session_stops_working(client, customer_user):
    headers = _headers(customer_user)
    assert _delete(client, customer_user).status_code == 204
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_the_email_can_register_again(client, db_session, customer_user):
    # The shared fixture uses a .test address, which registration's email
    # validation rightly rejects as reserved.
    customer_user.email = email = "ada.okafor@elizade.net"
    db_session.commit()
    assert _delete(client, customer_user).status_code == 204
    res = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email, "purpose": "register", "firstName": "New", "lastName": "Start"},
    )
    assert res.status_code == 200, res.text


# ── What it must refuse ────────────────────────────────────────────────────


def test_a_wrong_code_deletes_nothing(client, db_session, customer_user):
    res = _delete(client, customer_user, code="000000")
    assert res.status_code == 400
    db_session.expire_all()
    row = db_session.get(User, customer_user.id)
    assert row.is_active is True and row.email


def test_no_code_requested_deletes_nothing(client, db_session, customer_user):
    res = client.post("/api/v1/users/me/delete", json={"code": CODE}, headers=_headers(customer_user))
    assert res.status_code == 400
    db_session.expire_all()
    assert db_session.get(User, customer_user.id).is_active is True


def test_staff_cannot_delete_themselves_from_the_app(client, staff_user, admin_user):
    for user in (staff_user, admin_user):
        res = client.post("/api/v1/users/me/deletion-code", headers=_headers(user))
        assert res.status_code == 403
        res = client.post("/api/v1/users/me/delete", json={"code": CODE}, headers=_headers(user))
        assert res.status_code == 403


def test_signed_out_callers_are_refused(client):
    assert client.post("/api/v1/users/me/deletion-code").status_code == 401
    assert client.post("/api/v1/users/me/delete", json={"code": CODE}).status_code == 401


# ── The store reviewer ─────────────────────────────────────────────────────


@pytest.fixture
def reviewer(db_session, monkeypatch) -> User:
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", REVIEW_EMAIL, raising=False)
    monkeypatch.setattr(s, "review_account_otp", REVIEW_CODE, raising=False)
    user = User(
        phone_normalized="2348109999002",
        phone_display="+234 810 999 9002",
        first_name="App",
        last_name="Reviewer",
        email=REVIEW_EMAIL,
        role=UserRole.customer,
        is_active=True,
        is_verified=True,
        preferences={},
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_the_reviewer_deletes_with_the_fixed_code_and_no_email(client, db_session, reviewer):
    res = client.post("/api/v1/users/me/deletion-code", headers=_headers(reviewer))
    assert res.status_code == 200
    assert db_session.query(OtpChallenge).filter(OtpChallenge.email == REVIEW_EMAIL).count() == 0

    res = client.post("/api/v1/users/me/delete", json={"code": REVIEW_CODE}, headers=_headers(reviewer))
    assert res.status_code == 204, res.text
    db_session.expire_all()
    assert db_session.get(User, reviewer.id).is_active is False


def test_the_next_review_can_still_sign_in_after_a_deletion(client, db_session, reviewer):
    """Reviewers test deletion; the next reviewer uses the same address."""
    assert _delete(client, reviewer, code=REVIEW_CODE).status_code == 204

    res = client.post("/api/v1/auth/otp/request", json={"email": REVIEW_EMAIL, "purpose": "login"})
    assert res.status_code == 200, res.text
    res = client.post("/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE})
    assert res.status_code == 200, res.text
    fresh = db_session.query(User).filter(User.email == REVIEW_EMAIL).one()
    assert fresh.id != reviewer.id and fresh.role is UserRole.customer


def test_a_stranger_is_never_recreated(client):
    res = client.post("/api/v1/auth/otp/request", json={"email": "nobody@example.com", "purpose": "login"})
    assert res.status_code == 404
