"""A fixed sign-in for App Store and Play Store reviewers.

WHY THIS IS NEEDED
==================
Apple and Google review teams cannot receive a one-time code. They test on
shared devices, often in an automated harness, with no access to a mailbox we
control. An app whose only door is an emailed OTP is an app they cannot get
into, and "we could not sign in" is a rejection.

So one nominated account — and only that account — may sign in with a fixed
code instead of an emailed one.

WHAT THIS IS, PLAINLY
=====================
A permanent credential. It does not expire, it does not rotate, and anyone who
learns both halves can sign in as that account for as long as it stays
configured. Every rule below exists to bound that:

  * OFF unless BOTH settings are present. A default build has no bypass, so
    forgetting to configure it fails closed rather than open.
  * Exactly one email, compared after normalisation. There is no pattern, no
    domain rule, no list.
  * The code is compared in constant time. A fixed secret checked with `==`
    leaks its length and prefix to a patient attacker.
  * A minimum code length is enforced at startup. `123456` is a six-digit
    space that falls to a script in seconds; if this account is going to be a
    standing credential it should at least not be brute-forceable.
  * THE ACCOUNT MUST BE A CUSTOMER. Checked at every sign-in, not just at
    configuration time, because roles change. A bypass into an admin account
    would hand the whole back office to whoever reads the submission notes —
    and those notes are pasted into two third-party consoles and shared with
    reviewers we never meet.

WHAT IT DELIBERATELY DOES NOT DO
================================
It does not create the account. If the reviewer account does not exist, sign-in
fails the same way any unknown email does. Auto-creating a privileged-by-
convention account from configuration alone is how a typo in an environment
variable becomes a live account nobody meant to make.
"""

from __future__ import annotations

import logging
import secrets

from app.core.config import get_settings
from app.core.security import normalize_email
from app.domains.users.models import User, UserRole

logger = logging.getLogger("elizade.auth.review")

#: Shorter than this is refused at startup.
#:
#: 8 is also the CEILING: `OtpVerifyIn.code` is `Field(min_length=4,
#: max_length=8)`, so a longer code is rejected as malformed before it ever
#: reaches this module — it would look like a broken bypass rather than a
#: configuration error. So the reviewer code is exactly 8 characters.
#:
#: That is not a compromise worth worrying about: 8 random alphanumerics is
#: about 2e14 combinations, against an endpoint that is rate limited. Six
#: DIGITS, the shape people reach for by default, is a million — which a
#: script exhausts, and which is why the floor exists at all.
MIN_CODE_LENGTH = 8


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.review_account_email.strip()) and bool(s.review_account_otp.strip())


def is_review_email(email: str) -> bool:
    """True when `email` is the nominated reviewer account."""
    if not is_enabled():
        return False
    return normalize_email(email) == normalize_email(get_settings().review_account_email)


def code_matches(code: str) -> bool:
    """Constant-time comparison against the configured static code."""
    if not is_enabled():
        return False
    return secrets.compare_digest(
        code.strip().encode("utf-8"),
        get_settings().review_account_otp.strip().encode("utf-8"),
    )


def may_bypass(user: User | None) -> bool:
    """Whether this user is allowed to use the fixed code.

    Re-checked on every sign-in rather than trusted from configuration: the
    account's role can be changed in the admin portal long after the variable
    was set, and a standing credential must not silently follow it upward.
    """
    if user is None:
        return False
    if not user.is_active:
        return False
    if user.role is not UserRole.customer:
        logger.error(
            "review bypass REFUSED for %s: role is %s, not customer. "
            "This credential is shared with third-party reviewers and must "
            "never reach a privileged account.",
            user.email, user.role.value,
        )
        return False
    return True


def validate_configuration() -> list[str]:
    """Problems worth refusing to start over. Empty list when fine or disabled."""
    s = get_settings()
    email = s.review_account_email.strip()
    code = s.review_account_otp.strip()

    if not email and not code:
        return []
    problems: list[str] = []
    if bool(email) != bool(code):
        problems.append(
            "REVIEW_ACCOUNT_EMAIL and REVIEW_ACCOUNT_OTP must be set together; "
            "one without the other does nothing."
        )
    if code and len(code) < MIN_CODE_LENGTH:
        problems.append(
            f"REVIEW_ACCOUNT_OTP must be at least {MIN_CODE_LENGTH} characters. "
            f"This code never expires and never rotates, so a short one is a "
            f"standing invitation — use a random string, not 123456."
        )
    return problems


def log_status() -> None:
    """Announce the bypass at boot. A backdoor that starts quietly is worse."""
    if not is_enabled():
        logger.info("[REVIEW] no store-reviewer account configured — OTP required for everyone")
        return
    logger.warning(
        "[REVIEW] store-reviewer bypass ACTIVE for %s — this account signs in "
        "with a fixed code that never expires. Unset REVIEW_ACCOUNT_EMAIL and "
        "REVIEW_ACCOUNT_OTP once review is complete.",
        normalize_email(get_settings().review_account_email),
    )
