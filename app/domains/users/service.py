from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole
from app.domains.users.schemas import (
    UserPreferencesOut,
    UserPreferencesUpdateIn,
    UserProfileOut,
    UserProfileUpdateIn,
)


def _require_non_empty(value: str | None, field_label: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_label} cannot be empty",
        )
    return stripped


def update_profile(db: Session, user: User, payload: UserProfileUpdateIn) -> UserProfileOut:
    if payload.email and payload.email != user.email:
        owner = db.query(User).filter(User.email == payload.email).one_or_none()
        if owner and owner.id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        user.email = payload.email

    if payload.first_name is not None:
        user.first_name = _require_non_empty(payload.first_name, "First name")
    if payload.last_name is not None:
        user.last_name = _require_non_empty(payload.last_name, "Last name")
    if payload.city is not None:
        user.city = _require_non_empty(payload.city, "City")
    if payload.state is not None:
        user.state = _require_non_empty(payload.state, "State")
    if payload.avatar is not None:
        user.avatar_url = payload.avatar.strip() or None
    if payload.department is not None:
        if user.role not in (UserRole.staff, UserRole.admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department can only be updated for staff accounts",
            )
        user.department = payload.department.strip() or None

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
