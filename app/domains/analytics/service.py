from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.analytics.schemas import AnalyticsOverviewOut, InventoryModelStatOut, NamedCountOut
from app.domains.dashboard.service import get_dashboard_summary
from app.domains.inventory.models import Vehicle
from app.domains.shared.enums import (
    AvailabilityStatus,
    ClaimStatus,
    TicketStatus,
    WarrantyCertificateStatus,
)
from app.domains.support.models import SupportTicket
from app.domains.users.models import User, UserRole
from app.domains.warranty.models import RecallCampaign, WarrantyCertificate, WarrantyClaim


def get_analytics_overview(db: Session) -> AnalyticsOverviewOut:
    summary = get_dashboard_summary(db)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    model_rows = (
        db.query(
            Vehicle.model,
            func.count(Vehicle.id).filter(Vehicle.availability == AvailabilityStatus.available).label("available"),
            func.count(Vehicle.id).filter(Vehicle.availability == AvailabilityStatus.reserved).label("reserved"),
            func.count(Vehicle.id).filter(Vehicle.availability == AvailabilityStatus.sold).label("sold"),
            func.count(Vehicle.id).label("total"),
        )
        .filter(Vehicle.deleted_at.is_(None))
        .group_by(Vehicle.model)
        .order_by(func.count(Vehicle.id).desc())
        .all()
    )

    customers_with_vehicle = (
        db.query(func.count(User.id)).filter(User.role == UserRole.customer, User.owned_vehicles.any()).scalar() or 0
    )

    open_statuses = (
        TicketStatus.open,
        TicketStatus.assigned,
        TicketStatus.in_progress,
        TicketStatus.waiting_customer,
    )
    support_by_category = (
        db.query(SupportTicket.category, func.count(SupportTicket.id))
        .filter(SupportTicket.status.in_(open_statuses))
        .group_by(SupportTicket.category)
        .all()
    )

    pending_statuses = (ClaimStatus.submitted, ClaimStatus.under_review, ClaimStatus.escalated)
    claims_by_status = (
        db.query(WarrantyClaim.status, func.count(WarrantyClaim.id))
        .group_by(WarrantyClaim.status)
        .all()
    )

    active_certs = (
        db.query(func.count(WarrantyCertificate.id))
        .filter(WarrantyCertificate.status == WarrantyCertificateStatus.active)
        .scalar()
        or 0
    )
    active_recalls = db.query(func.count(RecallCampaign.id)).filter(RecallCampaign.is_active.is_(True)).scalar() or 0

    return AnalyticsOverviewOut(
        inventoryByModel=[
            InventoryModelStatOut(
                model=row.model,
                available=row.available or 0,
                reserved=row.reserved or 0,
                sold=row.sold or 0,
                total=row.total or 0,
            )
            for row in model_rows
        ],
        inventoryAvailable=summary.vehiclesAvailable,
        inventoryReserved=summary.vehiclesReserved,
        inventorySold=(
            db.query(func.count(Vehicle.id))
            .filter(Vehicle.deleted_at.is_(None), Vehicle.availability == AvailabilityStatus.sold)
            .scalar()
            or 0
        ),
        customersTotal=summary.customersTotal,
        customersNew30d=summary.customersNew30d,
        customersWithVehicle=customers_with_vehicle,
        openSupportTickets=summary.openSupportTickets,
        slaAtRiskTickets=summary.slaAtRiskTickets,
        supportByCategory=[
            NamedCountOut(name=cat.value, count=count) for cat, count in support_by_category
        ],
        pendingWarrantyClaims=summary.pendingWarrantyClaims,
        warrantyClaimsByStatus=[
            NamedCountOut(name=status.value, count=count) for status, count in claims_by_status
        ],
        activeCertificates=active_certs,
        activeRecalls=active_recalls,
        campaignsSent=summary.campaignsSent,
        activeNotificationRules=summary.activeNotificationRules,
        unreadNotificationsTotal=summary.unreadNotificationsTotal,
        serviceToday=summary.serviceToday,
        serviceCapacity=summary.serviceCapacity,
        leadsActive=summary.leadsActive,
    )
