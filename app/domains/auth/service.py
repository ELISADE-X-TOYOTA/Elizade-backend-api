from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, normalize_phone, verify_otp_hash
from app.domains.auth.schemas import AuthTokenOut, OtpRequestIn, OtpRequestOut, OtpVerifyIn
from app.domains.users.models import DEFAULT_PREFERENCES, OtpChallenge, OtpPurpose, User, UserRole
from app.domains.users.schemas import UserProfileOut
from app.services.otp import MAX_OTP_ATTEMPTS, create_and_dispatch_otp

settings = get_settings()


def _apply_admin_role(user: User) -> None:
    if user.phone_normalized == settings.admin_phone_normalized:
        user.role = UserRole.admin
        user.department = user.department or "Management"


def request_otp(db: Session, payload: OtpRequestIn) -> OtpRequestOut:
    phone_norm = normalize_phone(payload.phone)
    if len(phone_norm) < 9:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")

    purpose = OtpPurpose(payload.purpose)
    user = db.query(User).filter(User.phone_normalized == phone_norm).one_or_none()

    if purpose == OtpPurpose.login:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found for this number. Please register.",
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
                detail="Account already exists. Please sign in.",
            )
        if payload.email:
            email_owner = db.query(User).filter(User.email == payload.email).one_or_none()
            if email_owner and email_owner.phone_normalized != phone_norm:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use.")
        if not user:
            user = User(
                phone_normalized=phone_norm,
                phone_display=payload.phone.strip(),
                first_name=payload.first_name.strip(),
                last_name=payload.last_name.strip(),
                email=payload.email,
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
            user.phone_display = payload.phone.strip()
            if payload.email:
                user.email = payload.email
            if user.role == UserRole.customer or not user.is_verified:
                user.role = UserRole.customer
            _apply_admin_role(user)

    create_and_dispatch_otp(
        db,
        phone_norm,
        payload.phone.strip(),
        purpose,
        user_id=user.id if user else None,
        email=user.email if user else payload.email,
    )

    return OtpRequestOut(
        message="Verification code sent.",
        expires_in_minutes=settings.otp_expire_minutes,
    )


def verify_otp(db: Session, payload: OtpVerifyIn) -> AuthTokenOut:
    phone_norm = normalize_phone(payload.phone)
    code = payload.code.strip()

    challenge = (
        db.query(OtpChallenge)
        .filter(
            OtpChallenge.phone_normalized == phone_norm,
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

    user = db.query(User).filter(User.phone_normalized == phone_norm).one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found. Complete registration first.")

    user.is_verified = True
    user.is_active = True
    user.phone_display = payload.phone.strip() or user.phone_display
    _apply_admin_role(user)

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return AuthTokenOut(access_token=token, user=UserProfileOut.from_user(user))


def get_me(user: User) -> UserProfileOut:
    return UserProfileOut.from_user(user)
