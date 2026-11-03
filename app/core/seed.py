import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.seed_demo_data import seed_demo_data
from app.core.security import placeholder_phone_for_email
from app.domains.users.models import DEFAULT_PREFERENCES, OtpChallenge, RefreshToken, User, UserRole

logger = logging.getLogger("elizade.seed")

#: The first production boot created this address. It is removed once the
#: configured admin exists, so the old inbox can no longer sign in.
RETIRED_ADMIN_EMAIL = "divinewilson766@gmail.com"


def _admin_email() -> str:
    configured = get_settings().admin_email.strip().lower()
    if configured == RETIRED_ADMIN_EMAIL:
        return "allieric28@gmail.com"
    return configured


def _delete_user(db: Session, user: User) -> None:
    db.query(OtpChallenge).filter(OtpChallenge.user_id == user.id).delete(synchronize_session=False)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)


def seed_admin_user(db: Session) -> None:
    email = _admin_email()
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing is None:
        phone_normalized, phone_display = placeholder_phone_for_email(email)
        existing = User(
            phone_normalized=phone_normalized,
            phone_display=phone_display,
            first_name="Eric",
            last_name="Alli-balogun",
            email=email,
            city="Lagos",
            state="Lagos",
            role=UserRole.admin,
            department="Management",
            is_verified=True,
            is_active=True,
            preferences=dict(DEFAULT_PREFERENCES),
        )
        db.add(existing)
    else:
        existing.role = UserRole.admin
        existing.department = existing.department or "Management"
        existing.is_verified = True
        existing.is_active = True

    retired = db.query(User).filter(User.email == RETIRED_ADMIN_EMAIL).one_or_none()
    if retired is not None and retired.id != existing.id:
        _delete_user(db, retired)
        logger.info("Removed retired admin %s", RETIRED_ADMIN_EMAIL)

    db.commit()


def seed_all(db: Session) -> None:
    """Boot-time seeding.

    The admin account is ESSENTIAL and always runs — it is the only way into
    the admin portal, and `seed_admin_user` repairs an existing one rather than
    duplicating it. Gating that behind a flag would lock a fresh deployment out
    of its own back office.

    The demo content is not essential and is gated on `SEED_DEMO_DATA`. It adds
    ~75s to startup against a remote database and would otherwise fill a live
    database with sample Toyotas on first deploy.
    """
    seed_admin_user(db)

    # Read at call time, not import time, so a test (or a restart with a
    # changed .env) sees the current value.
    if not get_settings().seed_demo_data:
        logger.info("SEED_DEMO_DATA is off — skipping demo content.")
        return

    logger.info("SEED_DEMO_DATA is on — seeding demo content.")
    seed_demo_data(db)
