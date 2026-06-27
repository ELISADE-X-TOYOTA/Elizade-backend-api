from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.seed_demo_data import seed_demo_data
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

settings = get_settings()


def seed_admin_user(db: Session) -> None:
    phone = settings.admin_phone_normalized
    existing = db.query(User).filter(User.phone_normalized == phone).one_or_none()
    if existing:
        existing.role = UserRole.admin
        existing.department = existing.department or "Management"
        existing.first_name = existing.first_name or "Divine"
        existing.last_name = existing.last_name or "Obinali"
        existing.email = existing.email or "divine.obinali@elizade.com"
        existing.is_verified = True
        existing.is_active = True
        db.commit()
        return

    admin = User(
        phone_normalized=phone,
        phone_display="08107891549",
        first_name="Divine",
        last_name="Obinali",
        email="divine.obinali@elizade.com",
        city="Lagos",
        state="Lagos",
        role=UserRole.admin,
        department="Management",
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db.add(admin)
    db.commit()


def seed_all(db: Session) -> None:
    seed_admin_user(db)
    seed_demo_data(db)
