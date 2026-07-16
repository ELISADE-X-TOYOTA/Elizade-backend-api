import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_otp_code, hash_otp, normalize_email
from app.domains.users.models import OtpChallenge, OtpPurpose
from app.services.email import MockEmailService, email_service

settings = get_settings()
MAX_OTP_ATTEMPTS = 5


def _print_otp_dev_fallback(email: str, code: str, purpose: str) -> None:
    """Only log OTP to the terminal when SMTP is not configured (mock mode)."""
    if not isinstance(email_service, MockEmailService):
        return
    line = (
        f"\n{'=' * 48}\n"
        f"  ELIZADE CONNECT OTP ({purpose}) [mock — no SMTP]\n"
        f"  Email: {email}\n"
        f"  Code:  {code}\n"
        f"  Expires in {settings.otp_expire_minutes} min\n"
        f"{'=' * 48}\n"
    )
    print(line, file=sys.stdout, flush=True)


def invalidate_pending_challenges(db: Session, email: str) -> None:
    email_norm = normalize_email(email)
    db.query(OtpChallenge).filter(
        OtpChallenge.email == email_norm,
        OtpChallenge.verified_at.is_(None),
    ).delete(synchronize_session=False)


def create_and_dispatch_otp(
    db: Session,
    email: str,
    purpose: OtpPurpose,
    user_id: str | None = None,
) -> None:
    email_norm = normalize_email(email)
    invalidate_pending_challenges(db, email_norm)

    code = generate_otp_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)

    challenge = OtpChallenge(
        email=email_norm,
        user_id=user_id,
        code_hash=hash_otp(code),
        purpose=purpose,
        expires_at=expires,
    )
    db.add(challenge)
    db.commit()

    email_service.send_otp(email_norm, code, purpose.value)
    _print_otp_dev_fallback(email_norm, code, purpose.value)
