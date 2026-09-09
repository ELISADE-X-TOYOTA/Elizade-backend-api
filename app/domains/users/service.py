import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import is_placeholder_phone, normalize_email, placeholder_phone_for_email
from app.domains.notifications import catalog
from app.domains.notifications.notify import safe_notify
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole
from app.domains.users.schemas import (
    UserPreferencesOut,
    UserPreferencesUpdateIn,
    UserProfileOut,
    UserProfileUpdateIn,
)
from app.services.email import email_service

logger = logging.getLogger("elizade.users")


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
    # Captured before the write so the alert can go to the address that is
    # being replaced — telling only the NEW address is useless to somebody
    # whose account has just been taken over.
    previous_email = user.email
    email_changed = False

    if payload.email and normalize_email(payload.email) != normalize_email(user.email or ""):
        """
        THE REGISTERED EMAIL IS LOCKED, and the lock is here rather than only
        in the app.

        This address IS the credential: the sign-in code goes to it, so whoever
        controls it controls the account. Allowing it to change from an
        ordinary authenticated session means a borrowed or hijacked session can
        transfer the account outright, and the real owner finds out from an
        alert sent to a mailbox they no longer read.

        A read-only field in the UI is not a control — anything can call the
        API. Support can still do it, deliberately and with identity checked,
        through `change_email_verified` below.
        """
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your registered email cannot be changed here. "
                f"Contact {get_settings().support_email} and we will verify it with you."
            ),
        )

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

    # A security notification, and it had never been wired: someone could
    # change the email on an account and the owner would never hear.
    # `force=True` on this event means it ignores notification preferences —
    # you do not get to opt out of being told your login address moved.
    if email_changed:
        safe_notify(db, user=user, event=catalog.CONTACT_DETAILS_CHANGED,
                    context={"field": "email address"})
        # Also to the OLD address, which is the one an attacker has just cut
        # off. `notify` addresses a User, so this goes direct.
        _alert_previous_email(previous_email, user)

    return UserProfileOut.from_user(user)


def change_email_verified(db: Session, user: User, new_email: str) -> UserProfileOut:
    """Move an account to a new address AFTER identity has been established.

    The customer-facing `update_profile` refuses this outright, because the
    email is the sign-in credential. This is the path for support to use once
    they have verified the person — and it is a real function rather than a
    manual database edit, so the checks and the alerts cannot be skipped by
    whoever is in a hurry.

    Everything the old inline path did still happens here: the address must be
    free, the synthetic placeholder phone moves with the email (leaving it
    behind is what made somebody else's registration fail with a 500), the
    account is told, and the address being REPLACED is warned — that one is the
    point, because it is the mailbox an attacker has just cut off.
    """
    previous_email = user.email
    normalised = normalize_email(new_email)

    if normalised == normalize_email(previous_email or ""):
        return UserProfileOut.from_user(user)

    owner = db.query(User).filter(User.email == normalised).one_or_none()
    if owner and owner.id != user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    if is_placeholder_phone(user.phone_normalized, user.email or ""):
        new_norm, new_display = placeholder_phone_for_email(normalised)
        taken = (
            db.query(User)
            .filter(User.phone_normalized == new_norm, User.id != user.id)
            .first()
        )
        if taken is None:
            user.phone_normalized = new_norm
            user.phone_display = new_display

    user.email = normalised
    db.commit()
    db.refresh(user)

    safe_notify(db, user=user, event=catalog.CONTACT_DETAILS_CHANGED,
                context={"field": "email address"})
    _alert_previous_email(previous_email, user)
    return UserProfileOut.from_user(user)


def _alert_previous_email(previous_email: str | None, user: User) -> None:
    """Tell the address that was replaced, not just the one that replaced it."""
    if not previous_email or previous_email == user.email:
        return
    try:
        email_service.send_notification(
            to_email=previous_email,
            subject="Your Elizade Connect email address was changed",
            body=(
                f"The email address on your Elizade Connect account was changed to "
                f"{user.email}. If this wasn't you, contact us immediately.\n\n"
                "This is the last message this address will receive about the account."
            ),
            category="system",
        )
    except Exception:  # noqa: BLE001
        logger.exception("could not warn the previous address on an email change")


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
