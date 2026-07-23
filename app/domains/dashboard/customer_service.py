from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.domains.customers.models import OwnedVehicle, WatchlistItem
from app.domains.dashboard.customer_schemas import (
    CustomerDashboardSummaryOut,
    OwnedVehicleSnapshotOut,
    UpcomingAppointmentOut,
)
from app.domains.notifications.service import unread_count
from app.domains.ownership.models import VehicleOwnershipRequest
from app.domains.sales.models import Quotation, Reservation, TestDriveBooking, TradeInRequest
from app.domains.service.models import ServiceAppointment
from app.domains.shared.enums import (
    AdditionalWorkStatus,
    AppointmentStatus,
    ClaimStatus,
    OwnershipRequestStatus,
    QuotationStatus,
    ReservationStatus,
    TestDriveStatus,
    TicketStatus,
    TradeInStatus,
    WarrantyCertificateStatus,
)
from app.domains.support.models import SupportTicket
from app.domains.warranty.models import RecallVehicle, WarrantyCertificate, WarrantyClaim

OPEN_TICKET_STATUSES = (
    TicketStatus.open,
    TicketStatus.assigned,
    TicketStatus.in_progress,
    TicketStatus.waiting_customer,
)
PENDING_OWNERSHIP = (
    OwnershipRequestStatus.pending,
    OwnershipRequestStatus.pending_documents,
    OwnershipRequestStatus.under_review,
)
PENDING_CLAIMS = (ClaimStatus.submitted, ClaimStatus.under_review, ClaimStatus.escalated)
UPCOMING_APPT = (AppointmentStatus.requested, AppointmentStatus.confirmed, AppointmentStatus.in_progress)


def get_customer_summary(db: Session, user_id: str) -> CustomerDashboardSummaryOut:
    vehicles = (
        db.query(OwnedVehicle)
        .filter(OwnedVehicle.user_id == user_id)
        .order_by(OwnedVehicle.is_primary.desc(), OwnedVehicle.created_at.desc())
        .all()
    )
    primary = vehicles[0] if vehicles else None
    primary_out = None
    if primary:
        primary_out = OwnedVehicleSnapshotOut(
            id=primary.id,
            label=f"{primary.year} {primary.make} {primary.model}",
            registrationNumber=primary.registration_number,
            mileage=primary.mileage,
            nextServiceDue=primary.next_service_due.isoformat() if primary.next_service_due else None,
            nextServiceMileage=primary.next_service_mileage,
        )

    appts = (
        db.query(ServiceAppointment)
        .options(
            joinedload(ServiceAppointment.owned_vehicle),
            joinedload(ServiceAppointment.branch),
            joinedload(ServiceAppointment.job),
        )
        .filter(ServiceAppointment.user_id == user_id, ServiceAppointment.status.in_(UPCOMING_APPT))
        .order_by(ServiceAppointment.scheduled_at.asc())
        .all()
    )
    next_appt_out = None
    if appts:
        a = appts[0]
        vehicle = a.owned_vehicle
        next_appt_out = UpcomingAppointmentOut(
            id=a.id,
            vehicleLabel=f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "Vehicle",
            serviceType=a.service_type.value,
            scheduledAt=a.scheduled_at.isoformat(),
            status=a.status.value,
            branchName=a.branch.name if a.branch else "",
        )

    pending_work = 0
    for appt in appts:
        if appt.job and appt.job.additional_work:
            pending_work += sum(
                1 for w in appt.job.additional_work if w.status == AdditionalWorkStatus.pending_approval
            )

    open_tickets = (
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.user_id == user_id, SupportTicket.status.in_(OPEN_TICKET_STATUSES))
        .scalar()
        or 0
    )
    active_certs = (
        db.query(func.count(WarrantyCertificate.id))
        .filter(
            WarrantyCertificate.user_id == user_id,
            WarrantyCertificate.status == WarrantyCertificateStatus.active,
        )
        .scalar()
        or 0
    )
    pending_claims = (
        db.query(func.count(WarrantyClaim.id))
        .filter(WarrantyClaim.user_id == user_id, WarrantyClaim.status.in_(PENDING_CLAIMS))
        .scalar()
        or 0
    )
    active_recalls = (
        db.query(func.count(RecallVehicle.id))
        .filter(RecallVehicle.user_id == user_id, RecallVehicle.service_completed_at.is_(None))
        .scalar()
        or 0
    )
    watchlist = (
        db.query(func.count(WatchlistItem.id))
        .filter(WatchlistItem.user_id == user_id, WatchlistItem.is_active.is_(True))
        .scalar()
        or 0
    )
    pending_ownership = (
        db.query(func.count(VehicleOwnershipRequest.id))
        .filter(
            VehicleOwnershipRequest.user_id == user_id,
            VehicleOwnershipRequest.status.in_(PENDING_OWNERSHIP),
        )
        .scalar()
        or 0
    )
    pending_reservations = (
        db.query(func.count(Reservation.id))
        .filter(
            Reservation.user_id == user_id,
            Reservation.status.in_((ReservationStatus.pending, ReservationStatus.deposit_paid)),
        )
        .scalar()
        or 0
    )
    pending_quotations = (
        db.query(func.count(Quotation.id))
        .filter(
            Quotation.user_id == user_id,
            Quotation.status.in_((QuotationStatus.sent, QuotationStatus.draft)),
        )
        .scalar()
        or 0
    )
    pending_trade_ins = (
        db.query(func.count(TradeInRequest.id))
        .filter(
            TradeInRequest.user_id == user_id,
            TradeInRequest.status.in_((TradeInStatus.submitted, TradeInStatus.under_review, TradeInStatus.valued)),
        )
        .scalar()
        or 0
    )
    upcoming_test_drives = (
        db.query(func.count(TestDriveBooking.id))
        .filter(
            TestDriveBooking.user_id == user_id,
            TestDriveBooking.status.in_((TestDriveStatus.requested, TestDriveStatus.confirmed)),
            TestDriveBooking.scheduled_at >= datetime.now(timezone.utc),
        )
        .scalar()
        or 0
    )

    return CustomerDashboardSummaryOut(
        ownedVehiclesCount=len(vehicles),
        primaryVehicle=primary_out,
        upcomingAppointments=len(appts),
        nextAppointment=next_appt_out,
        pendingAdditionalWork=pending_work,
        openSupportTickets=open_tickets,
        unreadNotifications=unread_count(db, user_id),
        activeWarrantyCertificates=active_certs,
        pendingWarrantyClaims=pending_claims,
        activeRecalls=active_recalls,
        watchlistCount=watchlist,
        pendingOwnershipRequests=pending_ownership,
        pendingReservations=pending_reservations,
        pendingQuotations=pending_quotations,
        pendingTradeIns=pending_trade_ins,
        upcomingTestDrives=upcoming_test_drives,
    )
