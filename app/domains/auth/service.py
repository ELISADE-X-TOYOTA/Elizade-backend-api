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
from app.domains.users.models import DEFAULT_PREFERENCES, OtpChallenge, OtpPurpose, User, UserRole
from app.domains.users.schemas import UserProfileOut
from app.services.otp import MAX_OTP_ATTEMPTS, create_and_dispatch_otp

settings = get_settings()


def _apply_admin_role(user: User) -> None:
    if user.email and normalize_email(user.email) == normalize_email(settings.admin_email):
        user.role = UserRole.admin
        user.department = user.department or "Management"


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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated. Contact admin.")
    else:
        if not payload.first_name or not payload.last_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="First name and last name are required for registration.",
            )
        if user and user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already exists.",
            )
        phone_norm, phone_display = placeholder_phone_for_email(email_norm)
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
    user.is_active = True
    user.email = email_norm
    _apply_admin_role(user)

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    # A refresh token is minted here and ONLY here (plus rotation). This is the
    # single point where a new session family begins.
    refresh = refresh_service.issue(db, user.id)
    db.commit()
    return AuthTokenOut(
        access_token=token,
        refresh_token=refresh,
        user=UserProfileOut.from_user(user),
    )


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
