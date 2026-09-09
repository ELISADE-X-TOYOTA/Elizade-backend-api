"""Rate limiting for the fixed-code sign-in.

WHY THIS HAD TO EXIST BEFORE THE CODE COULD BE DIGITS.

The bypass accepts a permanent secret that never expires and never rotates,
and `/auth/otp/verify` applied no limit at all on that branch — a wrong code
simply fell through to the normal path. The normal path is protected: an
`OtpChallenge` row counts attempts and stops at five. The bypass has no
challenge row, so it had nothing counting.

That is why the code was required to contain a letter. Six digits is a million
combinations; against an endpoint that will answer as fast as it can be asked,
that is minutes of scripted guessing, and the reward is a live session on a
real customer account. The letter raised it to roughly 887 million, which was
a workaround for the missing limit rather than a fix for it.

With a limit in place the arithmetic changes completely. Five attempts per
address per fifteen minutes puts a million-code space at roughly six years of
continuous guessing, so a six-digit code becomes a reasonable choice rather
than a tolerated one. The limit is worth having whatever the code looks like —
it was a real hole under every configuration, including the letter ones.

KEYED BY EMAIL, NOT BY IP. The credential is per-account and the attacker
picks the address; rotating IPs is trivial and rotating the target address is
not, since only the configured ones can be attacked at all. Locking the
address is what actually bounds the search.

STORED IN THE DATABASE, not in memory. An in-process counter resets on every
deploy and is not shared between replicas — either alone hands an attacker a
clean slate for free.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.domains.users.models import ReviewBypassAttempt

logger = logging.getLogger("elizade.auth.review")

#: Failed attempts allowed before the address is locked out.
MAX_ATTEMPTS = 5

#: How long a lockout lasts, and the window failures are counted over.
LOCKOUT = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _row(db: Session, email: str) -> ReviewBypassAttempt | None:
    return (
        db.query(ReviewBypassAttempt)
        .filter(ReviewBypassAttempt.email == email)
        .one_or_none()
    )


def seconds_locked(db: Session, email: str) -> int:
    """Seconds remaining on a lockout, or 0 when this address may try.

    An expired lockout is treated as no lockout — the row is reset on the next
    failure rather than swept, so a stale row cannot lock somebody out forever.
    """
    row = _row(db, email)
    if row is None:
        return 0
    locked_until = _as_utc(row.locked_until)
    if locked_until is None:
        return 0
    remaining = (locked_until - _now()).total_seconds()
    return max(0, int(remaining))


def record_failure(db: Session, email: str) -> int:
    """Count a wrong code. Returns attempts remaining before lockout.

    Committed immediately: a failed attempt that is not durably recorded is not
    a limit, and the caller raises straight after this.
    """
    row = _row(db, email)
    now = _now()

    if row is None:
        row = ReviewBypassAttempt(email=email, failed_count=0, first_failed_at=now)
        db.add(row)

    # A window that has fully elapsed starts a fresh count, so an honest
    # mistake made an hour ago does not add to today's.
    first = _as_utc(row.first_failed_at)
    if first is None or now - first > LOCKOUT:
        row.failed_count = 0
        row.first_failed_at = now
        row.locked_until = None

    row.failed_count += 1
    if row.failed_count >= MAX_ATTEMPTS:
        row.locked_until = now + LOCKOUT
        logger.warning(
            "[REVIEW] fixed-code sign-in LOCKED for %s after %d failed attempts — "
            "locked for %d minutes",
            email,
            row.failed_count,
            int(LOCKOUT.total_seconds() // 60),
        )

    db.commit()
    return max(0, MAX_ATTEMPTS - row.failed_count)


def clear(db: Session, email: str) -> None:
    """Forget the failures for an address that has just signed in correctly."""
    row = _row(db, email)
    if row is None:
        return
    db.delete(row)
    db.commit()
