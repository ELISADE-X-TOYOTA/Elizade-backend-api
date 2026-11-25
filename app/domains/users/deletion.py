"""A customer deleting their own account.

Required by Apple (guideline 5.1.1(v)) and Google Play, and promised on the
public page at elizade-web.vercel.app/delete-account.html. That page is the
contract this module implements, so the two must stay in step:

DELETED
    Profile (name, email, phone, photo), sign-in sessions and codes,
    notification settings and device tokens, in-app notifications, My Vehicles
    entries nothing else depends on, ownership documents, trade-in and warranty
    claim photos, support tickets with their messages and attachments, the
    watchlist and availability alerts, and client error reports.

KEPT, WITH THE IDENTITY REMOVED
    Sales and payment records (quotations, reservations, test drives, leads)
    and service and warranty history. These point at the user row, so the row
    survives as an anonymised, deactivated placeholder rather than being
    removed — deleting it would either fail on foreign keys or cascade away
    records Elizade is obliged to keep. A vehicle that warranty, service or
    recall records refer to stays for the same reason; it is the VIN record.

The email address is released (set to NULL), so the same person can register
again later and gets a fresh, empty account.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.audit.models import AuditLog
from app.domains.customers.models import CustomerNote, OwnedVehicle, WatchlistItem
from app.domains.inventory.models import VehicleAvailabilitySubscription
from app.domains.notifications.models import (
    DeviceToken,
    NotificationDelivery,
    NotificationPreference,
    ReminderDispatch,
    UserNotification,
)
from app.domains.ownership.models import VehicleOwnershipRequest
from app.domains.sales.models import TradeInRequest
from app.domains.service.models import ServiceAppointment, ServiceHistoryItem
from app.domains.shared.enums import AuditAction
from app.domains.support.models import SupportTicket, TicketMessage
from app.domains.telemetry.models import ClientErrorReport
from app.domains.users.models import OtpChallenge, RefreshToken, ReviewBypassAttempt, User
from app.domains.warranty.models import RecallVehicle, WarrantyCertificate, WarrantyClaim

logger = logging.getLogger("elizade.account_deletion")

#: What the anonymised row is called wherever staff still see it (a kept
#: quotation, a past service). Honest about what happened, and not a name.
DELETED_FIRST_NAME = "Deleted"
DELETED_LAST_NAME = "customer"

#: Every channel off, so nothing can be sent to a placeholder.
DELETED_PREFERENCES = {
    "push_enabled": False,
    "sms_enabled": False,
    "email_enabled": False,
    "marketing_opt_in": False,
}


def _urls(values: list | None) -> list[str]:
    return [v for v in (values or []) if isinstance(v, str) and v]


def _vehicle_is_referenced(db: Session, vehicle_id: str) -> bool:
    """True when kept records point at this vehicle, so it must stay."""
    for model in (
        WarrantyCertificate,
        WarrantyClaim,
        RecallVehicle,
        ServiceAppointment,
        ServiceHistoryItem,
    ):
        hit = db.execute(
            select(model.id).where(model.owned_vehicle_id == vehicle_id).limit(1)
        ).first()
        if hit:
            return True
    return False


def delete_customer_account(db: Session, user: User) -> dict[str, list[str]]:
    """Delete or anonymise everything the page promises. Commits.

    Returns the uploaded files to remove from storage, grouped by source. They
    are removed by the caller AFTER the commit: a storage failure must never
    leave personal data in the database, and a database failure must never
    leave records pointing at files that are already gone.
    """
    uid = user.id
    email = user.email
    files: dict[str, list[str]] = {
        "avatar": _urls([user.avatar_url]),
        "support": [],
        "warranty": [],
        "trade_in": [],
        "ownership": [],
    }

    # Support: tickets and their messages go entirely.
    ticket_ids = list(db.scalars(select(SupportTicket.id).where(SupportTicket.user_id == uid)))
    if ticket_ids:
        for msg in db.scalars(select(TicketMessage).where(TicketMessage.ticket_id.in_(ticket_ids))):
            files["support"].extend(_urls(msg.attachments))
        db.query(TicketMessage).filter(TicketMessage.ticket_id.in_(ticket_ids)).delete(synchronize_session=False)
        db.query(SupportTicket).filter(SupportTicket.id.in_(ticket_ids)).delete(synchronize_session=False)

    # Ownership requests and their documents.
    for req in db.scalars(select(VehicleOwnershipRequest).where(VehicleOwnershipRequest.user_id == uid)):
        files["ownership"].extend(_urls(req.document_urls))
    db.query(VehicleOwnershipRequest).filter(VehicleOwnershipRequest.user_id == uid).delete(synchronize_session=False)

    # Photos on records that are otherwise kept.
    for claim in db.scalars(select(WarrantyClaim).where(WarrantyClaim.user_id == uid)):
        files["warranty"].extend(_urls(claim.attachment_urls))
        claim.attachment_urls = []
    for trade in db.scalars(select(TradeInRequest).where(TradeInRequest.user_id == uid)):
        files["trade_in"].extend(_urls(trade.photo_urls))
        trade.photo_urls = []

    # Notifications: deliveries reference notifications, so they go first.
    db.query(NotificationDelivery).filter(NotificationDelivery.user_id == uid).delete(synchronize_session=False)
    db.query(UserNotification).filter(UserNotification.user_id == uid).delete(synchronize_session=False)
    db.query(DeviceToken).filter(DeviceToken.user_id == uid).delete(synchronize_session=False)
    db.query(NotificationPreference).filter(NotificationPreference.user_id == uid).delete(synchronize_session=False)
    db.query(ReminderDispatch).filter(ReminderDispatch.user_id == uid).delete(synchronize_session=False)

    # Saved items, alerts, staff notes about the person, error reports.
    db.query(WatchlistItem).filter(WatchlistItem.user_id == uid).delete(synchronize_session=False)
    db.query(VehicleAvailabilitySubscription).filter(
        VehicleAvailabilitySubscription.user_id == uid
    ).delete(synchronize_session=False)
    db.query(CustomerNote).filter(CustomerNote.customer_id == uid).delete(synchronize_session=False)
    db.query(ClientErrorReport).filter(ClientErrorReport.user_id == uid).delete(synchronize_session=False)

    # My Vehicles: removed unless kept records depend on it.
    db.flush()
    for vehicle in list(db.scalars(select(OwnedVehicle).where(OwnedVehicle.user_id == uid))):
        if not _vehicle_is_referenced(db, vehicle.id):
            db.delete(vehicle)
    db.flush()

    # Credentials: every session ends now, not when the access token expires.
    db.query(RefreshToken).filter(RefreshToken.user_id == uid).delete(synchronize_session=False)
    otp_filter = OtpChallenge.user_id == uid
    if email:
        otp_filter = or_(otp_filter, OtpChallenge.email == email)
        db.query(ReviewBypassAttempt).filter(ReviewBypassAttempt.email == email).delete(synchronize_session=False)
    db.query(OtpChallenge).filter(otp_filter).delete(synchronize_session=False)

    # The row itself: anonymised and deactivated, kept for the records above.
    user.email = None
    user.first_name = DELETED_FIRST_NAME
    user.last_name = DELETED_LAST_NAME
    user.other_name = None
    # Unique and NOT NULL; 20 characters fits the column exactly.
    user.phone_normalized = f"del{uuid.uuid4().hex[:17]}"
    user.phone_display = ""
    user.avatar_url = None
    user.preferences = dict(DELETED_PREFERENCES)
    user.is_active = False
    user.is_verified = False

    # No personal data in the audit entry: the point is that it is gone.
    db.add(
        AuditLog(
            actor_id=uid,
            action=AuditAction.delete,
            entity_type="user_account",
            entity_id=uid,
            changes={"reason": "customer_self_service_deletion"},
        )
    )
    db.commit()
    logger.info("[ACCOUNT] customer %s deleted their account", uid)
    return files


STAFF_DELETION_MESSAGE = (
    "Staff and admin accounts can't be deleted from the app. "
    "Please ask an administrator to remove your access."
)


def _require_customer(user: User) -> None:
    from fastapi import HTTPException, status  # noqa: PLC0415

    from app.domains.users.models import UserRole  # noqa: PLC0415

    if user.role is not UserRole.customer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=STAFF_DELETION_MESSAGE)
    if not user.email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account has no email address to confirm with.")


def request_deletion_code(db: Session, user: User) -> int:
    """Email a one-time code that confirms the deletion. Returns its lifetime.

    Deletion is irreversible, so holding a signed-in phone is not enough: the
    code proves the request comes from whoever controls the mailbox, exactly
    as signing in does. The store reviewer gets no email (nobody reads that
    inbox) and confirms with the fixed code instead.
    """
    from app.core.config import get_settings  # noqa: PLC0415
    from app.domains.auth import review_bypass  # noqa: PLC0415
    from app.domains.users.models import OtpPurpose  # noqa: PLC0415
    from app.services.otp import create_and_dispatch_otp  # noqa: PLC0415

    _require_customer(user)
    minutes = get_settings().otp_expire_minutes
    if review_bypass.is_review_email(user.email) and review_bypass.may_bypass(user):
        logger.warning("[REVIEW] deletion code requested for %s — fixed code applies", user.email)
        return minutes
    create_and_dispatch_otp(db, user.email, OtpPurpose.login, user_id=user.id)
    return minutes


def confirm_deletion(db: Session, user: User, code: str) -> dict[str, list[str]]:
    """Check the code, then delete. Returns files for `purge_files`."""
    from app.core.security import normalize_email  # noqa: PLC0415
    from app.domains.auth.service import accept_review_code, consume_otp_challenge  # noqa: PLC0415

    _require_customer(user)
    email_norm = normalize_email(user.email)
    code = code.strip()
    if not accept_review_code(db, email_norm, code, user):
        consume_otp_challenge(db, email_norm, code)
    return delete_customer_account(db, user)


def purge_files(files: dict[str, list[str]]) -> None:
    """Best-effort removal of uploaded files. Never raises."""
    from app.services import uploads  # noqa: PLC0415 — storage clients are built at import

    stores = {
        "avatar": uploads.avatar_storage,
        "support": uploads.support_storage,
        "warranty": uploads.warranty_storage,
        "trade_in": uploads.trade_in_storage,
        "ownership": uploads.ownership_storage,
    }
    for source, urls in files.items():
        store = stores.get(source)
        if store is None:
            continue
        for url in urls:
            try:
                store.delete(url)
            except Exception:  # noqa: BLE001 — a stuck file must not undo a deletion
                logger.warning("[ACCOUNT] could not remove %s file %s", source, url, exc_info=True)
