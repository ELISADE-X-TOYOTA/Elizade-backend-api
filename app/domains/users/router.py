from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.users import service
from app.domains.users.schemas import (
    UserPreferencesOut,
    UserPreferencesUpdateIn,
    UserProfileOut,
    UserProfileUpdateIn,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserProfileOut)
def patch_my_profile(
    payload: UserProfileUpdateIn,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> UserProfileOut:
    return service.update_profile(db, current_user, payload)


@router.get("/me/preferences", response_model=UserPreferencesOut)
def get_my_preferences(current_user: CurrentUser) -> UserPreferencesOut:
    return UserPreferencesOut.from_db(current_user.preferences)


@router.patch("/me/preferences", response_model=UserPreferencesOut)
def patch_my_preferences(
    payload: UserPreferencesUpdateIn,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> UserPreferencesOut:
    return service.update_preferences(db, current_user, payload)


@router.get("/preferences/defaults", response_model=UserPreferencesOut)
def get_system_default_preferences() -> UserPreferencesOut:
    return service.get_default_preferences()
