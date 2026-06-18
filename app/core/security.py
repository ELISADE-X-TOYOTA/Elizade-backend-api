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
