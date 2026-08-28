"""Refresh-token rotation, revocation, and theft detection.

These guard the mechanism that keeps a customer signed in. The failure mode
they exist to prevent is the one that was reported: a session ending mid-task
and dumping the user back on the login screen.

The security-critical case is REUSE. A rotated token must never work twice,
and presenting a spent one must take down the whole family — otherwise a
stolen token keeps minting sessions forever behind the real user's back.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import decode_access_token, hash_refresh_token
from app.domains.auth import refresh as refresh_service
from app.domains.users.models import RefreshToken


def _rows(db, user_id):
    return db.query(RefreshToken).filter(RefreshToken.user_id == user_id).all()


# ── Issuance ─────────────────────────────────────────────────────────────


def test_issued_token_is_never_stored_in_plaintext(db_session, customer_user):
    """The database must not hold anything usable as a credential."""
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    stored = _rows(db_session, customer_user.id)
    assert len(stored) == 1
    assert stored[0].token_hash != token, "the raw token was written to the DB"
    assert stored[0].token_hash == hash_refresh_token(token)


def test_issue_starts_a_new_family(db_session, customer_user):
    a = refresh_service.issue(db_session, customer_user.id)
    b = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    families = {r.family_id for r in _rows(db_session, customer_user.id)}
    assert len(families) == 2, "two sign-ins must not share a family"
    assert a != b


# ── Rotation ─────────────────────────────────────────────────────────────


def test_rotate_returns_a_working_access_token(db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    access, new_refresh, user_id = refresh_service.rotate(db_session, token)

    assert user_id == customer_user.id
    assert decode_access_token(access) == customer_user.id
    assert new_refresh != token, "rotation must issue a different token"


def test_rotation_stays_in_the_same_family(db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()
    original_family = _rows(db_session, customer_user.id)[0].family_id

    _, new_refresh, _ = refresh_service.rotate(db_session, token)

    new_row = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(new_refresh))
        .one()
    )
    assert new_row.family_id == original_family


def test_rotation_links_the_chain(db_session, customer_user):
    """`replaced_by_id` is what makes a lineage auditable after the fact."""
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    _, new_refresh, _ = refresh_service.rotate(db_session, token)

    old = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(token))
        .one()
    )
    new = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(new_refresh))
        .one()
    )
    assert old.revoked_at is not None, "the spent token must be revoked"
    assert old.replaced_by_id == new.id


def test_a_long_chain_keeps_working(db_session, customer_user):
    """Rotating repeatedly is the normal case, not an edge case."""
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    for _ in range(10):
        access, token, _ = refresh_service.rotate(db_session, token)
        assert decode_access_token(access) == customer_user.id


# ── Theft detection: the case that matters ───────────────────────────────


def test_reusing_a_spent_token_is_refused(db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()
    refresh_service.rotate(db_session, token)

    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, token)


def test_reuse_revokes_the_whole_family(db_session, customer_user):
    """A stolen token must not leave a working session behind.

    Scenario: an attacker copies the refresh token and uses it. The real
    client then rotates normally and presents what is now a spent token. We
    cannot tell victim from thief, so both are cut off and the user signs in
    again — the only outcome that does not leave the attacker with access.
    """
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    # The thief rotates first, and now holds a live token.
    _, thief_token, _ = refresh_service.rotate(db_session, token)

    # The real client presents the token it still holds — already spent.
    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, token)

    # The thief's token must be dead too.
    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, thief_token)

    assert all(r.revoked_at is not None for r in _rows(db_session, customer_user.id))


def test_reuse_does_not_touch_other_sessions(db_session, customer_user):
    """Signing out a compromised phone must not sign out the tablet."""
    phone = refresh_service.issue(db_session, customer_user.id)
    tablet = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    refresh_service.rotate(db_session, phone)
    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, phone)  # triggers family revocation

    # The other device is a different family and must survive.
    access, _, _ = refresh_service.rotate(db_session, tablet)
    assert decode_access_token(access) == customer_user.id


# ── Expiry and unknown tokens ────────────────────────────────────────────


def test_expired_token_is_refused(db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    row = _rows(db_session, customer_user.id)[0]
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, token)


def test_unknown_token_is_refused(db_session):
    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, "not-a-real-token-value-at-all")


# ── Sign-out ─────────────────────────────────────────────────────────────


def test_revoke_ends_the_session(db_session, customer_user):
    token = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    refresh_service.revoke(db_session, token)

    with pytest.raises(refresh_service.RefreshError):
        refresh_service.rotate(db_session, token)


def test_revoke_is_silent_on_an_unknown_token(db_session):
    """Sign-out must not report whether a token was real."""
    refresh_service.revoke(db_session, "never-existed")  # must not raise


def test_revoke_all_for_user_clears_every_device(db_session, customer_user):
    a = refresh_service.issue(db_session, customer_user.id)
    b = refresh_service.issue(db_session, customer_user.id)
    db_session.commit()

    refresh_service.revoke_all_for_user(db_session, customer_user.id)

    for token in (a, b):
        with pytest.raises(refresh_service.RefreshError):
            refresh_service.rotate(db_session, token)
