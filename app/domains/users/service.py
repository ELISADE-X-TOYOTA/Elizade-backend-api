from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import normalize_phone
from app.domains.users.models import DEFAULT_PREFERENCES, User
from app.domains.users.schemas import (
    UserPreferencesOut,
    UserPreferencesUpdateIn,
    UserProfileOut,
    UserProfileUpdateIn,
)


def update_profile(db: Session, user: User, payload: UserProfileUpdateIn) -> UserProfileOut:
    if payload.email and payload.email != user.email:
        owner = db.query(User).filter(User.email == payload.email).one_or_none()
        if owner and owner.id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        user.email = payload.email

    if payload.phone:
        phone_norm = normalize_phone(payload.phone)
        if len(phone_norm) < 9:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")

        phone_owner = db.query(User).filter(User.phone_normalized == phone_norm).one_or_none()
        if phone_owner and phone_owner.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number already registered by another user",
            )

        user.phone_normalized = phone_norm
        user.phone_display = payload.phone.strip()

    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        user.last_name = payload.last_name.strip()
    if payload.city is not None:
        user.city = payload.city.strip()
    if payload.state is not None:
        user.state = payload.state.strip()
    if payload.department is not None:
        user.department = payload.department.strip() or None
    if payload.avatar is not None:
        user.avatar_url = payload.avatar.strip() or None

    db.commit()
    db.refresh(user)
    return UserProfileOut.from_user(user)


def update_preferences(db: Session, user: User, payload: UserPreferencesUpdateIn) -> UserPreferencesOut:
    current_prefs = dict(user.preferences or DEFAULT_PREFERENCES)

    if payload.push_enabled is not None:
        current_prefs["push_enabled"] = payload.push_enabled
    if payload.sms_enabled is not None:
        current_prefs["sms_enabled"] = payload.sms_enabled
    if payload.email_enabled is not None:
        current_prefs["email_enabled"] = payload.email_enabled
    if payload.marketing_opt_in is not None:
        current_prefs["marketing_opt_in"] = payload.marketing_opt_in

    user.preferences = current_prefs
    db.commit()
    db.refresh(user)
    return UserPreferencesOut.from_db(user.preferences)


def get_default_preferences() -> UserPreferencesOut:
    return UserPreferencesOut.from_db(DEFAULT_PREFERENCES)
