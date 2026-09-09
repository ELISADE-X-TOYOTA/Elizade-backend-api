import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import is_placeholder_phone, placeholder_phone_for_email
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

    if payload.email and payload.email != user.email:
        owner = db.query(User).filter(User.email == payload.email).one_or_none()
        if owner and owner.id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

        """
        THE PLACEHOLDER PHONE HAS TO MOVE WITH THE EMAIL.

        Email-only accounts get a synthetic `phone_normalized` derived from the
        address, because the column is NOT NULL. It was derived once at
        registration and never revisited, so changing your email left it
        encoding the OLD address — and the column is UNIQUE.

        The consequence was a 500 on somebody else's registration. Anyone
        signing up with the address you moved away from produced the same
        placeholder, hit `duplicate key value violates unique constraint
        ix_users_phone_normalized`, and got "Elizade services are temporarily
        unavailable" — an outage message for a stale row. Telemetry caught it
        twice on /auth/otp/request.

        Only a PLACEHOLDER is rewritten. A customer who has given a real phone
        number keeps it; that is their number, not a derived artefact.
        """
        if is_placeholder_phone(user.phone_normalized, user.email):
            new_norm, new_display = placeholder_phone_for_email(payload.email)
            # If the new address somehow already has a placeholder in use, leave
            # the old one rather than trading one collision for another; the
            # address itself is already proven free by the check above.
            taken = (
                db.query(User)
                .filter(User.phone_normalized == new_norm, User.id != user.id)
                .first()
            )
            if taken is None:
                user.phone_normalized = new_norm
                user.phone_display = new_display

        user.email = payload.email
        email_changed = True

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
