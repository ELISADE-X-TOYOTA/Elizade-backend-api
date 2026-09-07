"""The App Store / Play Store reviewer sign-in.

This is a permanent credential that gets pasted into two third-party consoles
and read by people we never meet. The happy path is the least interesting
thing here — what matters is everything it must REFUSE, because each of those
is a way the back door widens without anybody noticing.
"""

import pytest

from app.core.config import get_settings
from app.domains.auth import review_bypass
from app.domains.users.models import User, UserRole

REVIEW_EMAIL = "appreview@elizade.com"
REVIEW_CODE = "Rv7Kqm"  # 6 chars: the app renders six OTP boxes, so this is the ceiling


@pytest.fixture
def reviewer(db_session) -> User:
    user = User(
        phone_normalized="2348109999001",
        phone_display="+234 810 999 9001",
        first_name="Store",
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


@pytest.fixture
def bypass_on(monkeypatch):
    """Configure the bypass, clearing the settings cache around it."""
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", REVIEW_EMAIL, raising=False)
    monkeypatch.setattr(s, "review_account_otp", REVIEW_CODE, raising=False)
    yield


@pytest.fixture
def bypass_off(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", "", raising=False)
    monkeypatch.setattr(s, "review_account_otp", "", raising=False)
    yield


# ── The reason it exists ─────────────────────────────────────────────────


def test_the_reviewer_signs_in_with_the_fixed_code(client, reviewer, bypass_on):
    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == REVIEW_EMAIL


def test_requesting_a_code_succeeds_without_sending_mail(client, reviewer, bypass_on):
    """The app must show its ordinary "code sent" screen.

    An error here would strand the reviewer on the very screen this feature
    exists to get them past.
    """
    res = client.post(
        "/api/v1/auth/otp/request",
        json={"email": REVIEW_EMAIL, "purpose": "login"},
    )
    assert res.status_code == 200, res.text


def test_the_fixed_code_works_repeatedly_and_does_not_expire(client, reviewer, bypass_on):
    """Review can take days and involves several sign-ins."""
    for _ in range(3):
        res = client.post(
            "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
        )
        assert res.status_code == 200


# ── Everything it must refuse ────────────────────────────────────────────


def test_disabled_by_default(client, reviewer, bypass_off):
    """An unconfigured build has no back door at all."""
    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
    )
    assert res.status_code == 400


def test_the_fixed_code_does_not_work_for_any_other_account(
    client, db_session, reviewer, bypass_on
):
    """The bypass is one email, not a master key.

    A second REAL account, so this exercises the bypass check rather than
    bouncing off email-format validation.
    """
    other = User(
        phone_normalized="2348109999002",
        phone_display="+234 810 999 9002",
        first_name="Someone",
        last_name="Else",
        email="someone.else@elizade.com",
        role=UserRole.customer,
        is_active=True,
        is_verified=True,
        preferences={},
    )
    db_session.add(other)
    db_session.commit()

    res = client.post(
        "/api/v1/auth/otp/verify",
        json={"email": "someone.else@elizade.com", "code": REVIEW_CODE},
    )
    assert res.status_code == 400


def test_a_wrong_code_on_the_review_account_is_still_rejected(client, reviewer, bypass_on):
    """The account is not exempt from verification — only from the mailbox."""
    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": "000000"}
    )
    assert res.status_code == 400


def test_the_bypass_is_refused_for_a_staff_account(client, db_session, reviewer, bypass_on):
    """THE ONE THAT MATTERS MOST.

    The code is shared with third-party reviewers. If the nominated account is
    ever promoted — in the admin portal, months later, by someone who has no
    idea this exists — that credential must stop working rather than quietly
    become a key to the back office.
    """
    reviewer.role = UserRole.staff
    db_session.commit()

    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
    )
    assert res.status_code == 400, "a privileged account must not accept the fixed code"


def test_the_bypass_is_refused_for_an_admin_account(client, db_session, reviewer, bypass_on):
    reviewer.role = UserRole.admin
    db_session.commit()
    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
    )
    assert res.status_code == 400


def test_a_deactivated_review_account_cannot_sign_in(client, db_session, reviewer, bypass_on):
    """Deactivating the account is how you revoke this without a deploy."""
    reviewer.is_active = False
    db_session.commit()
    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
    )
    assert res.status_code == 400


def test_a_missing_review_account_is_not_created(client, db_session, bypass_on):
    """Configuration alone must never conjure an account.

    A typo in an environment variable would otherwise create a live, working
    login for an address nobody chose.
    """
    res = client.post(
        "/api/v1/auth/otp/verify", json={"email": REVIEW_EMAIL, "code": REVIEW_CODE}
    )
    assert res.status_code == 400
    assert db_session.query(User).filter(User.email == REVIEW_EMAIL).one_or_none() is None


# ── Configuration guard ──────────────────────────────────────────────────


def test_an_all_digit_code_is_refused_at_startup(monkeypatch):
    """`123456` is a million combinations and this code never rotates."""
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", REVIEW_EMAIL, raising=False)
    monkeypatch.setattr(s, "review_account_otp", "123456", raising=False)
    problems = review_bypass.validate_configuration()
    assert problems and "letter" in problems[0]


def test_half_configured_is_refused_at_startup(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", REVIEW_EMAIL, raising=False)
    monkeypatch.setattr(s, "review_account_otp", "", raising=False)
    assert review_bypass.validate_configuration()


def test_unconfigured_is_valid(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", "", raising=False)
    monkeypatch.setattr(s, "review_account_otp", "", raising=False)
    assert review_bypass.validate_configuration() == []


def test_a_code_longer_than_the_app_can_accept_is_refused(monkeypatch):
    """THE BUG THIS CAUGHT LATE.

    The first version shipped an 8-character code. The app's OTP screen has six
    boxes and stripped letters, so it could not be typed OR pasted — a reviewer
    would have been stranded on the exact screen this feature exists to skip.
    Backend tests POST straight to the API and never saw it.
    """
    s = get_settings()
    monkeypatch.setattr(s, "review_account_email", REVIEW_EMAIL, raising=False)
    monkeypatch.setattr(s, "review_account_otp", "Rv7Kq2Xm", raising=False)
    problems = review_bypass.validate_configuration()
    assert problems and "6 characters" in problems[0]
