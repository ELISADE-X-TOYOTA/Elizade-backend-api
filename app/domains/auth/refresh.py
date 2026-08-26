"""Refresh-token issuance, rotation, and reuse detection.

WHY THIS EXISTS: the app previously held one 7-day JWT and nothing else. When
it expired — or when any endpoint returned 401 for any reason — the client
wiped the credential and the customer landed back on the login screen mid-task.
There was no way to renew a session without making the user sign in again.

THE ROTATION RULE: presenting a refresh token revokes it and returns a
replacement. A token is therefore valid exactly once. If the same token is
presented twice, either the network retried or the token was stolen — and we
cannot tell which, so we assume theft and revoke the entire family. The
legitimate user signs in again; the thief gets nothing.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.domains.users.models import RefreshToken

logger = logging.getLogger("elizade.auth")
settings = get_settings()


class RefreshError(Exception):
    """The presented refresh token cannot mint a new session."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(moment: datetime) -> datetime:
    """Postgres can hand back a naive datetime depending on the driver."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def issue(db: Session, user_id: str, *, family_id: str | None = None) -> str:
    """Mint a refresh token. Returns the PLAINTEXT — the only time it exists."""
    import uuid

    token = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(token),
        family_id=family_id or str(uuid.uuid4()),
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(row)
    db.flush()
    return token


def _revoke_family(db: Session, family_id: str) -> None:
    """Kill every token descended from one sign-in."""
    now = _now()
    (
        db.query(RefreshToken)
        .filter(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .update({RefreshToken.revoked_at: now}, synchronize_session=False)
    )


def rotate(db: Session, presented: str) -> tuple[str, str, str]:
    """Exchange a refresh token for a new (access, refresh) pair.

    Returns (access_token, refresh_token, user_id).
    Raises RefreshError for anything that should send the user to sign-in.
    """
    row = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(presented))
        .one_or_none()
    )

    if row is None:
        # Never existed, or the family was already purged.
        raise RefreshError("Unknown refresh token")

    if row.revoked_at is not None:
        # REUSE. A rotated token came back — treat the family as compromised.
        # This is the one branch that must be aggressive: the alternative is
        # leaving a thief with a working session.
        logger.warning("refresh token reuse detected; revoking family %s", row.family_id)
        _revoke_family(db, row.family_id)
        db.commit()
        raise RefreshError("Refresh token already used")

    if _now() > _as_utc(row.expires_at):
        raise RefreshError("Refresh token expired")

    replacement = issue(db, row.user_id, family_id=row.family_id)
    new_row = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(replacement))
        .one()
    )
    row.revoked_at = _now()
    row.replaced_by_id = new_row.id
    db.commit()

    return create_access_token(row.user_id), replacement, row.user_id


def revoke(db: Session, presented: str) -> None:
    """Sign-out. Best effort — an unknown token is already not a session."""
    row = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(presented))
        .one_or_none()
    )
    if row is not None and row.revoked_at is None:
        _revoke_family(db, row.family_id)
        db.commit()


def revoke_all_for_user(db: Session, user_id: str) -> None:
    """Sign out everywhere — used when an account is disabled."""
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .update({RefreshToken.revoked_at: _now()}, synchronize_session=False)
    )
    db.commit()
