"""Rate limiting the fixed-code sign-in.

THE HOLE THIS CLOSES existed under every configuration, not just digit ones.
`/auth/otp/verify` applied no limit on the bypass branch: a wrong code fell
through to the normal path, and the normal path counts attempts on an
`OtpChallenge` row that a bypass sign-in never creates. So nothing counted,
and a permanent secret sat behind an endpoint that answers as fast as it is
asked.

That absence was the only reason the code had to contain a letter — six digits
is a million combinations, which is minutes of scripted guessing. Five
attempts per address per fifteen minutes turns the same space into years, so
an all-digit code becomes a reasonable choice rather than a tolerated one.

The tests that matter most are the last two: an unlisted stranger must not be
able to lock the reviewer out, and a correct sign-in must clear the count.
"""

from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.domains.auth import bypass_throttle
from app.domains.auth import review_bypass
from app.domains.users.models import DEFAULT_PREFERENCES, ReviewBypassAttempt, User, UserRole

AUTH = "/api/v1/auth"
CODE = "334567"


@pytest.fixture
def tester(db_session):
    """A customer with a REAL email domain.

    The shared `customer_user` fixture uses `@elizade.test`, and `.test` is a
    reserved TLD that `EmailStr` rejects — every request with it is refused at
    validation with a 422, long before reaching the code under test.
    """
    user = User(
        phone_normalized="8100000777",
        phone_display="08100000777",
        first_name="Faith",
        last_name="Ibitoye",
        email="bypass.tester@elizade.com",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def bypass_on(monkeypatch, tester):
    """The tester's own account, signing in with an all-digit code."""
    monkeypatch.setenv("REVIEW_ACCOUNT_EMAIL", tester.email)
    monkeypatch.setenv("REVIEW_ACCOUNT_OTP", CODE)
    get_settings.cache_clear()
    yield tester
    get_settings.cache_clear()


def _verify(client, email, code):
    return client.post(f"{AUTH}/otp/verify", json={"email": email, "code": code})


# ── An all-digit code is now allowed, and boots ──────────────────────────


def test_an_all_digit_code_is_accepted_by_the_validator(bypass_on):
    assert review_bypass.validate_configuration() == []


def test_the_code_still_has_to_be_six_characters(monkeypatch, tester):
    monkeypatch.setenv("REVIEW_ACCOUNT_EMAIL", tester.email)
    monkeypatch.setenv("REVIEW_ACCOUNT_OTP", "3345678")
    get_settings.cache_clear()
    assert any("6 characters" in p for p in review_bypass.validate_configuration())
    get_settings.cache_clear()


def test_the_right_code_signs_in(client, bypass_on):
    res = _verify(client, bypass_on.email, CODE)
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


# ── The limit ────────────────────────────────────────────────────────────


def test_wrong_codes_are_counted(client, bypass_on, db_session):
    for _ in range(3):
        _verify(client, bypass_on.email, "000000")

    row = db_session.query(ReviewBypassAttempt).filter(
        ReviewBypassAttempt.email == bypass_on.email
    ).one()
    assert row.failed_count == 3
    assert row.locked_until is None


def test_the_address_locks_out_after_the_limit(client, bypass_on, db_session):
    """THE POINT OF ALL THIS. Guessing must stop being free."""
    for _ in range(bypass_throttle.MAX_ATTEMPTS):
        _verify(client, bypass_on.email, "000000")

    res = _verify(client, bypass_on.email, "000000")
    assert res.status_code == 429, res.text


def test_a_locked_address_is_refused_even_with_the_RIGHT_code(client, bypass_on):
    """Checked before the comparison, so a lockout costs an attacker a request
    and tells them nothing about the code."""
    for _ in range(bypass_throttle.MAX_ATTEMPTS):
        _verify(client, bypass_on.email, "000000")

    res = _verify(client, bypass_on.email, CODE)
    assert res.status_code == 429, res.text


def test_the_lockout_expires(client, bypass_on, db_session):
    for _ in range(bypass_throttle.MAX_ATTEMPTS):
        _verify(client, bypass_on.email, "000000")
    assert _verify(client, bypass_on.email, CODE).status_code == 429

    row = db_session.query(ReviewBypassAttempt).filter(
        ReviewBypassAttempt.email == bypass_on.email
    ).one()
    row.locked_until = row.locked_until - timedelta(hours=1)
    db_session.commit()

    assert _verify(client, bypass_on.email, CODE).status_code == 200


def test_a_stale_window_does_not_accumulate(client, bypass_on, db_session):
    """A mistake made an hour ago must not count towards today's total."""
    _verify(client, bypass_on.email, "000000")
    row = db_session.query(ReviewBypassAttempt).filter(
        ReviewBypassAttempt.email == bypass_on.email
    ).one()
    row.first_failed_at = row.first_failed_at - timedelta(hours=2)
    db_session.commit()

    _verify(client, bypass_on.email, "000000")

    db_session.expire_all()
    row = db_session.query(ReviewBypassAttempt).filter(
        ReviewBypassAttempt.email == bypass_on.email
    ).one()
    assert row.failed_count == 1, "the elapsed window should have reset the count"


# ── The two that matter most ─────────────────────────────────────────────


def test_a_stranger_cannot_lock_out_the_reviewer(client, bypass_on, db_session):
    """Failures are counted ONLY for configured addresses.

    Otherwise anyone could disable the store reviewer's sign-in on demand,
    which turns a security control into a denial-of-service handle.
    """
    for _ in range(bypass_throttle.MAX_ATTEMPTS + 2):
        _verify(client, "someone.else@elizade.com", "000000")

    assert db_session.query(ReviewBypassAttempt).count() == 0
    assert _verify(client, bypass_on.email, CODE).status_code == 200


def test_a_correct_sign_in_clears_the_count(client, bypass_on, db_session):
    """Ordinary fat-fingering must not accumulate across sessions."""
    for _ in range(bypass_throttle.MAX_ATTEMPTS - 1):
        _verify(client, bypass_on.email, "000000")

    assert _verify(client, bypass_on.email, CODE).status_code == 200
    assert db_session.query(ReviewBypassAttempt).count() == 0

    # And the next mistake starts from zero, not from the brink.
    _verify(client, bypass_on.email, "000000")
    row = db_session.query(ReviewBypassAttempt).filter(
        ReviewBypassAttempt.email == bypass_on.email
    ).one()
    assert row.failed_count == 1


def test_the_normal_otp_path_is_untouched(client, db_session, tester, monkeypatch):
    """With no bypass configured, nothing here should change behaviour."""
    monkeypatch.setenv("REVIEW_ACCOUNT_EMAIL", "")
    monkeypatch.setenv("REVIEW_ACCOUNT_OTP", "")
    get_settings.cache_clear()

    res = _verify(client, tester.email, "000000")

    assert res.status_code == 400
    assert "verification code" in res.json()["detail"].lower()
    assert db_session.query(ReviewBypassAttempt).count() == 0
    get_settings.cache_clear()
