from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.seed_demo_data import seed_demo_data
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

settings = get_settings()


def seed_admin_user(db: Session) -> None:
    email = settings.admin_email.lower()
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing:
        existing.role = UserRole.admin
        existing.department = existing.department or "Management"
        existing.first_name = existing.first_name or "Divine"
        existing.last_name = existing.last_name or "Obinali"
        existing.email = email
        existing.is_verified = True
        existing.is_active = True
        db.commit()
        return

    previous_admin = (
        db.query(User)
        .filter(User.role == UserRole.admin)
        .order_by(User.created_at.asc())
        .first()
    )
    if previous_admin:
        previous_admin.email = email
        previous_admin.role = UserRole.admin
        previous_admin.department = previous_admin.department or "Management"
        previous_admin.first_name = previous_admin.first_name or "Divine"
        previous_admin.last_name = previous_admin.last_name or "Obinali"
        previous_admin.is_verified = True
        previous_admin.is_active = True
        db.commit()
        return

    admin = User(
        phone_normalized="8107891549",
        phone_display="08107891549",
        first_name="Divine",
        last_name="Obinali",
        email=email,
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
