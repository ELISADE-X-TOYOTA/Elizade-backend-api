import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
ALGORITHM = "HS256"


def normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("234"):
        return digits[3:]
    if digits.startswith("0"):
        return digits[1:]
    return digits


def normalize_email(email: str) -> str:
    return email.strip().lower()


def placeholder_phone_for_email(email: str) -> tuple[str, str]:
    """Synthetic phone fields for email-only accounts (users.phone is still required).

    DERIVED FROM THE EMAIL, which makes it stale the moment the email changes —
    see `is_placeholder_phone`. The value stays derived rather than random so
    an account created twice from the same address is caught by the uniqueness
    constraint instead of silently duplicating.
    """
    norm = normalize_email(email)
    digest = hashlib.sha256(norm.encode()).hexdigest()[:15]
    phone_norm = f"e{digest}"
    return phone_norm, norm


def is_placeholder_phone(phone_normalized: str | None, email: str) -> bool:
    """Is this stored phone the synthetic one derived from `email`?

    Used to tell a REAL phone number, which must never be rewritten, from a
    stand-in that is only there because the column is NOT NULL.
    """
    if not phone_normalized:
        return False
    return phone_normalized == placeholder_phone_for_email(email)[0]


def _otp_digest(code: str) -> str:
    payload = f"{settings.jwt_secret}:otp:{code}"
    return hashlib.sha256(payload.encode()).hexdigest()


def hash_otp(code: str) -> str:
    return _otp_digest(code)


def verify_otp_hash(code: str, hashed: str) -> bool:
    return _otp_digest(code) == hashed


def generate_otp_code(length: int | None = None) -> str:
    n = length or settings.otp_length
    return "".join(str(secrets.randbelow(10)) for _ in range(n))


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None


# ── Refresh tokens ───────────────────────────────────────────────────────
#
# A refresh token is opaque random bytes, NOT a JWT. There is nothing to read
# from it and nothing to verify offline: it is a lookup key into a table we
# control, which is what makes instant revocation possible. A self-contained
# JWT cannot be revoked before it expires without exactly this table anyway.

def generate_refresh_token() -> str:
    """A 256-bit URL-safe secret. Returned to the client once, never stored."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256, hex. Plain digest rather than a password KDF on purpose.

    A KDF defends a LOW-entropy secret against offline guessing. This secret
    has 256 bits of entropy, so guessing is not the threat — and a slow KDF on
    every API refresh would be a self-inflicted denial of service.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
