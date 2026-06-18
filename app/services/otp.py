import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_otp_code, hash_otp
from app.domains.users.models import OtpChallenge, OtpPurpose
from app.services.email import email_service

settings = get_settings()
MAX_OTP_ATTEMPTS = 5


def _print_otp(phone: str, code: str, purpose: str) -> None:
    line = f"\n{'=' * 48}\n  ELIZADE CONNECT OTP ({purpose})\n  Phone: {phone}\n  Code:  {code}\n  Expires in {settings.otp_expire_minutes} min\n{'=' * 48}\n"
    print(line, file=sys.stdout, flush=True)


def invalidate_pending_challenges(db: Session, phone_normalized: str) -> None:
    db.query(OtpChallenge).filter(
        OtpChallenge.phone_normalized == phone_normalized,
        OtpChallenge.verified_at.is_(None),
    ).delete(synchronize_session=False)


def create_and_dispatch_otp(
    db: Session,
    phone_normalized: str,
    phone_display: str,
    purpose: OtpPurpose,
    user_id: str | None = None,
    email: str | None = None,
) -> None:
    invalidate_pending_challenges(db, phone_normalized)

    code = generate_otp_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)

    challenge = OtpChallenge(
        phone_normalized=phone_normalized,
        user_id=user_id,
        code_hash=hash_otp(code),
        purpose=purpose,
        expires_at=expires,
    )
    db.add(challenge)
    db.commit()

    _print_otp(phone_display, code, purpose.value)

    if email:
        email_service.send_otp(email, code, purpose.value)
