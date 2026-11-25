from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.users import deletion, service
from app.domains.users.schemas import (
    AccountDeletionIn,
    DeletionCodeOut,
    UserPreferencesOut,
    UserPreferencesUpdateIn,
    UserProfileOut,
    UserProfileUpdateIn,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfileOut)
def get_my_profile(current_user: CurrentUser) -> UserProfileOut:
    return UserProfileOut.from_user(current_user)


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


@router.post("/me/deletion-code", response_model=DeletionCodeOut)
def request_account_deletion_code(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> DeletionCodeOut:
    """Step 1 of deleting the account: email a confirmation code."""
    return DeletionCodeOut(expiresInMinutes=deletion.request_deletion_code(db, current_user))


@router.post("/me/delete", status_code=204)
def delete_my_account(
    payload: AccountDeletionIn,
    background: BackgroundTasks,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    """Step 2: confirm with the code and delete. Irreversible.

    POST rather than DELETE because it carries a body, and some HTTP clients
    and proxies drop DELETE bodies. Uploaded files are removed after the
    response, once the database change is committed.
    """
    files = deletion.confirm_deletion(db, current_user, payload.code)
    background.add_task(deletion.purge_files, files)
