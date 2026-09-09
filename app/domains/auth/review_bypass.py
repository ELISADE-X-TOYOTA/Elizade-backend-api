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
  * A short, explicit LIST of addresses, each compared after normalisation.
    There is still no pattern and no domain rule — a wildcard here would turn
    a reviewer workaround into a way past the front door for anyone with the
    code. The list is capped, because "just add one more" is how a bounded
    exception becomes an unbounded one.
  * ONE code for the whole list. Every listed address is therefore exposed if
    the code leaks, which is the argument for keeping the list at the two or
    three people who genuinely cannot receive email, and removing them the day
    they can.
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

#: The reviewer code is exactly SIX characters, and that is set by the app,
#: not by taste: the OTP screen renders six boxes. A longer code cannot be
#: entered at all, which is how the first version of this shipped — an
#: 8-character code that no reviewer could have typed, on the very screen this
#: feature exists to get them past.
#:
#: Six DIGITS would be a million combinations, and `/auth/otp/verify` has no
#: throttle on this branch. So the code must contain at least one letter:
#: six alphanumerics is ~57 billion, and it also guarantees the fixed code can
#: never be confused with a real six-digit OTP.
MIN_CODE_LENGTH = 6

#: How many addresses may share the fixed code.
#:
#: A cap rather than an unlimited list, because this is a standing credential
#: and the list is the blast radius. Store reviewers plus a couple of testers
#: who cannot receive email is the intended shape; a dozen is a sign the real
#: problem is mail deliverability and should be fixed there instead.
MAX_BYPASS_ACCOUNTS = 5


def configured_emails() -> list[str]:
    """The nominated addresses, normalised, in configuration order.

    `REVIEW_ACCOUNT_EMAIL` accepts one address or several separated by commas.
    A single address is still the common case and still works unchanged.
    """
    raw = get_settings().review_account_email or ""
    seen: list[str] = []
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        normalised = normalize_email(candidate)
        if normalised not in seen:
            seen.append(normalised)
    return seen


def is_enabled() -> bool:
    s = get_settings()
    return bool(configured_emails()) and bool(s.review_account_otp.strip())


def is_review_email(email: str) -> bool:
    """True when `email` is one of the nominated accounts."""
    if not is_enabled():
        return False
    return normalize_email(email) in configured_emails()


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

    emails = configured_emails()
    if email and not emails:
        problems.append("REVIEW_ACCOUNT_EMAIL contains no usable address.")
    if len(emails) > MAX_BYPASS_ACCOUNTS:
        problems.append(
            f"REVIEW_ACCOUNT_EMAIL lists {len(emails)} addresses; at most "
            f"{MAX_BYPASS_ACCOUNTS} may share a standing credential. If more "
            f"people cannot receive their code, fix mail delivery rather than "
            f"widening this."
        )
    for candidate in emails:
        if "@" not in candidate or candidate.startswith("@") or candidate.endswith("@"):
            problems.append(f"REVIEW_ACCOUNT_EMAIL entry {candidate!r} is not an email address.")
    if bool(email) != bool(code):
        problems.append(
            "REVIEW_ACCOUNT_EMAIL and REVIEW_ACCOUNT_OTP must be set together; "
            "one without the other does nothing."
        )
    if code and len(code) != MIN_CODE_LENGTH:
        problems.append(
            f"REVIEW_ACCOUNT_OTP must be exactly {MIN_CODE_LENGTH} characters — "
            f"the app's OTP screen has {MIN_CODE_LENGTH} boxes, so anything "
            f"longer cannot be entered."
        )
    if code and code.isdigit():
        problems.append(
            "REVIEW_ACCOUNT_OTP must contain at least one letter. Six digits is "
            "a million combinations for a code that never expires and never "
            "rotates — use something like 'Rv7Kqm', not '123456'."
        )
    return problems


def log_status() -> None:
    """Announce the bypass at boot. A backdoor that starts quietly is worse."""
    if not is_enabled():
        logger.info("[REVIEW] no store-reviewer account configured — OTP required for everyone")
        return
    emails = configured_emails()
    logger.warning(
        "[REVIEW] fixed-code bypass ACTIVE for %d account(s): %s — these sign "
        "in with a code that never expires and never rotates, and they all "
        "share it. Unset REVIEW_ACCOUNT_EMAIL and REVIEW_ACCOUNT_OTP once "
        "review and testing are complete.",
        len(emails),
        ", ".join(emails),
    )
