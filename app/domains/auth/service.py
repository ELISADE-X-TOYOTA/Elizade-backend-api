import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    normalize_email,
    placeholder_phone_for_email,
    verify_otp_hash,
)
from app.domains.auth.schemas import AuthTokenOut, OtpRequestIn, OtpRequestOut, OtpVerifyIn
from app.domains.auth import refresh as refresh_service
from app.domains.auth import bypass_throttle, review_bypass
from app.domains.users.models import DEFAULT_PREFERENCES, OtpChallenge, OtpPurpose, User, UserRole
from app.domains.users.schemas import UserProfileOut
from app.services.otp import MAX_OTP_ATTEMPTS, create_and_dispatch_otp

logger = logging.getLogger("elizade.auth")

#: Said to anyone whose account has been deactivated, on sign-in OR sign-up.
#:
#: Registration used to answer "Account already exists." — true, unhelpful, and
#: indistinguishable from a plain duplicate. Sign-in said "Contact admin.",
#: naming a person the customer has no way to reach. Neither told them what had
#: actually happened or where to go, and a deactivated account is usually the
#: one case where somebody genuinely needs a human.
DEACTIVATED_ACCOUNT_MESSAGE = (
    "This email address is associated with a previously deactivated account. "
    "Please contact support at {support} to restore it."
)


def _deactivated_message() -> str:
    return DEACTIVATED_ACCOUNT_MESSAGE.format(support=get_settings().support_email)

settings = get_settings()


def _apply_admin_role(user: User) -> None:
    if user.email and normalize_email(user.email) == normalize_email(settings.admin_email):
        user.role = UserRole.admin
        user.department = user.department or "Management"


def _issue_session(db: Session, user: User) -> AuthTokenOut:
    """Mint an access/refresh pair for an already-authenticated user.

    Extracted so the reviewer path and the ordinary OTP path cannot drift —
    a second hand-rolled token mint is how one of them ends up missing
    refresh-token rotation.

    Deliberately does NOT touch `is_verified`, `is_active` or the role. The
    OTP path sets those because verifying a code is what proves the address;
    the reviewer path has proved nothing about a mailbox and must not
    silently upgrade an account.
    """
    token = create_access_token(user.id)
    refresh = refresh_service.issue(db, user.id)
    db.commit()
    return AuthTokenOut(
        access_token=token,
        refresh_token=refresh,
        user=UserProfileOut.from_user(user),
    )


def request_otp(db: Session, payload: OtpRequestIn) -> OtpRequestOut:
    email_norm = normalize_email(str(payload.email))
    purpose = OtpPurpose(payload.purpose)
    user = db.query(User).filter(User.email == email_norm).one_or_none()

    if purpose == OtpPurpose.login:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found for this email. Please register.",
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_deactivated_message())

        # The store reviewer's fixed code is already valid, so no challenge is
        # created and no mail is sent. Returning success rather than an error
        # matters: the app shows its normal "code sent" screen, and the
        # reviewer follows the ordinary flow with the code from our notes.
        # Sending a real email here would also be pointless — nobody is
        # reading that mailbox.
        if review_bypass.is_review_email(email_norm) and review_bypass.may_bypass(user):
            logger.warning("[REVIEW] fixed-code sign-in requested for %s", email_norm)
            return OtpRequestOut(
                message="Verification code sent.",
                expires_in_minutes=settings.otp_expire_minutes,
            )
    else:
        if not payload.first_name or not payload.last_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="First name and last name are required for registration.",
            )
        # A DEACTIVATED ACCOUNT IS NOT A DUPLICATE, and saying "Account
        # already exists" to someone whose account was disabled sends them
        # round a loop: they cannot register, and signing in tells them
        # something different. Checked before the duplicate case so the more
        # specific answer wins.
        if user and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_deactivated_message(),
            )
        if user and user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already exists.",
            )
        phone_norm, phone_display = placeholder_phone_for_email(email_norm)
        """
        A COLLIDING PLACEHOLDER MUST NOT BE A 500.

        `phone_normalized` is unique and, for email-only accounts, derived from
        the address. `update_profile` now moves it when an email changes, so
        the common cause is gone — but rows created before that fix still carry
        placeholders for addresses they no longer own, and any registration
        with one of those addresses would raise `UniqueViolation` and surface
        as "Elizade services are temporarily unavailable".

        A stale row is not a reason to refuse a customer. If the derived value
        is taken by somebody else, a unique one is used instead: the placeholder
        exists only to satisfy a NOT NULL column, and nothing reads meaning
        back out of it.
        """
        clash = (
            db.query(User)
            .filter(User.phone_normalized == phone_norm)
            .filter(User.email != email_norm)
            .first()
        )
        if clash is not None:
            logger.warning(
                "[AUTH] placeholder phone for %s is held by a stale row (%s); "
                "issuing a unique one instead",
                email_norm, clash.email,
            )
            phone_norm = f"e{uuid.uuid4().hex[:15]}"
            phone_display = email_norm

        if not user:
            user = User(
                phone_normalized=phone_norm,
                phone_display=phone_display,
                first_name=payload.first_name.strip(),
                last_name=payload.last_name.strip(),
                other_name=(payload.other_name or "").strip() or None,
                email=email_norm,
                role=UserRole.customer,
                is_verified=False,
                is_active=True,
                preferences=dict(DEFAULT_PREFERENCES),
            )
            _apply_admin_role(user)
            db.add(user)
            db.flush()
        else:
            user.first_name = payload.first_name.strip()
            user.last_name = payload.last_name.strip()
            if payload.other_name is not None:
                user.other_name = payload.other_name.strip() or None
            user.email = email_norm
            if user.role == UserRole.customer or not user.is_verified:
                user.role = UserRole.customer
            _apply_admin_role(user)

    create_and_dispatch_otp(
        db,
        email_norm,
        purpose,
        user_id=user.id if user else None,
    )

    return OtpRequestOut(
        message="Verification code sent to your email.",
        expires_in_minutes=settings.otp_expire_minutes,
    )


def verify_otp(db: Session, payload: OtpVerifyIn) -> AuthTokenOut:
    email_norm = normalize_email(str(payload.email))
    code = payload.code.strip()

    # ── Store-reviewer fixed code ────────────────────────────────────────
    # Checked BEFORE the challenge lookup, because `request_otp` deliberately
    # created no challenge for this account — looking one up would fail with
    # "No active verification code" and the reviewer would be stuck on exactly
    # the screen this exists to get them past.
    #
    # `may_bypass` re-checks the account is an active customer on every
    # attempt. A wrong code here falls through to the normal path and is
    # rejected like any other, so the fixed code is not a way to skip
    # verification — only a way to satisfy it without a mailbox.
    if review_bypass.is_review_email(email_norm):
        """
        THROTTLED, which it never used to be.

        A wrong code here simply fell through to the normal path, and the
        normal path counts attempts on an `OtpChallenge` row that a bypass
        sign-in never creates — so nothing was counting. A permanent secret
        against an endpoint answering as fast as it is asked is a search, not a
        wall, and that absence is the only reason the code had to contain a
        letter.

        Checked BEFORE the code comparison, so a locked-out address costs an
        attacker a request and tells them nothing.
        """
        locked = bypass_throttle.seconds_locked(db, email_norm)
        if locked:
            logger.warning("[REVIEW] fixed-code sign-in REFUSED for %s — locked for %ds", email_norm, locked)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many incorrect codes. Please try again in a few minutes.",
            )

        if review_bypass.code_matches(code):
            reviewer = db.query(User).filter(User.email == email_norm).one_or_none()
            if review_bypass.may_bypass(reviewer):
                logger.warning("[REVIEW] fixed-code sign-in accepted for %s", email_norm)
                # A correct sign-in clears the count, so ordinary fat-fingering
                # never accumulates towards a lockout across sessions.
                bypass_throttle.clear(db, email_norm)
                return _issue_session(db, reviewer)
        else:
            # Counted only for a configured address. An unlisted email cannot
            # reach this branch at all, so no stranger can lock the reviewer out.
            remaining = bypass_throttle.record_failure(db, email_norm)
            logger.warning(
                "[REVIEW] fixed-code sign-in FAILED for %s — %d attempt(s) left",
                email_norm, remaining,
            )

    challenge = (
        db.query(OtpChallenge)
        .filter(
            OtpChallenge.email == email_norm,
            OtpChallenge.verified_at.is_(None),
        )
        .order_by(OtpChallenge.created_at.desc())
        .first()
    )

    if not challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active verification code. Request a new one.")

    now = datetime.now(timezone.utc)
    expires = challenge.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired. Request a new one.")

    if challenge.attempts >= MAX_OTP_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attempts. Request a new code.")

    challenge.attempts += 1

    if not verify_otp_hash(code, challenge.code_hash):
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    challenge.verified_at = now

    user = db.query(User).filter(User.email == email_norm).one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found. Complete registration first.")

    user.is_verified = True
    """
    DELIBERATELY NOT `user.is_active = True`.

    This used to reactivate unconditionally, so anyone disabled in the admin
    portal could simply register again and be back — whatever the deactivation
    was for. Registration must not be a way to undo a moderation decision.

    `request_otp` now refuses a deactivated account before it gets here, so
    this is the second line rather than the first; a silent reactivation is
    exactly the kind of thing that survives if only one gate holds it.
    """
    user.email = email_norm
    _apply_admin_role(user)

    db.commit()
    db.refresh(user)

    # A refresh token is minted in `_issue_session` and ONLY there (plus
    # rotation). One place where a session family begins, shared with the
    # reviewer path so neither can lose rotation independently.
    return _issue_session(db, user)


def get_me(user: User) -> UserProfileOut:
    return UserProfileOut.from_user(user)


def check_email_available(db: Session, email: str) -> tuple[bool, str | None]:
    """Can this email start a registration?

    Mirrors the 409 rule in `request_otp` exactly: only a *verified* account
    blocks re-registration, so an abandoned unverified signup can be resumed.
    Kept read-only and side-effect free so the client can call it while the
    user types, without dispatching an OTP.
    """
    email_norm = normalize_email(email)
    user = db.query(User).filter(User.email == email_norm).one_or_none()
    if user and user.is_verified:
        return False, "Account already exists."
    return True, None
