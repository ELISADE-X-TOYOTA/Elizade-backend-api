from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import normalize_phone
from app.domains.staff.schemas import StaffCreateIn, StaffOut, StaffUpdateIn
from app.domains.users.models import DEFAULT_PREFERENCES, OtpPurpose, User, UserRole
from app.services.otp import create_and_dispatch_otp


def _to_staff_out(user: User) -> StaffOut:
    email = user.email or ""
    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return StaffOut(
        id=user.id,
        firstName=user.first_name,
        lastName=user.last_name,
        email=email,
        phone=user.phone_display,
        department=user.department or "",
        city=user.city,
        state=user.state,
        isActive=user.is_active,
        isVerified=user.is_verified,
        createdAt=created.isoformat(),
    )


def list_staff(db: Session) -> list[StaffOut]:
    rows = (
        db.query(User)
        .filter(User.role == UserRole.staff)
        .order_by(User.created_at.desc())
        .all()
    )
    return [_to_staff_out(u) for u in rows]


def create_staff(db: Session, payload: StaffCreateIn) -> StaffOut:
    phone_norm = normalize_phone(payload.phone)
    if len(phone_norm) < 9:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")

    existing_phone = db.query(User).filter(User.phone_normalized == phone_norm).one_or_none()
    if existing_phone:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already registered.")

    existing_email = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use.")

    staff = User(
        phone_normalized=phone_norm,
        phone_display=payload.phone.strip(),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        email=payload.email,
        department=payload.department.strip(),
        city=payload.city.strip(),
        state=payload.state.strip(),
        role=UserRole.staff,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)

    if payload.send_welcome_otp:
        create_and_dispatch_otp(
            db,
            phone_norm,
            payload.phone.strip(),
            OtpPurpose.login,
            user_id=staff.id,
            email=staff.email,
        )

    return _to_staff_out(staff)


def update_staff(db: Session, staff_id: str, payload: StaffUpdateIn) -> StaffOut:
    staff = db.get(User, staff_id)
    if not staff or staff.role != UserRole.staff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    if payload.email and payload.email != staff.email:
        owner = db.query(User).filter(User.email == payload.email).one_or_none()
        if owner and owner.id != staff.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        staff.email = payload.email

    if payload.first_name is not None:
        staff.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        staff.last_name = payload.last_name.strip()
    if payload.department is not None:
        staff.department = payload.department.strip()
    if payload.city is not None:
        staff.city = payload.city.strip()
    if payload.state is not None:
        staff.state = payload.state.strip()
    if payload.is_active is not None:
        staff.is_active = payload.is_active

    db.commit()
    db.refresh(staff)
    return _to_staff_out(staff)
