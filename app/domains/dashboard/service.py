from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.dashboard.schemas import DashboardSummaryOut
from app.domains.inventory.models import Vehicle
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.shared.enums import (
    AvailabilityStatus,
    BroadcastCampaignStatus,
    ClaimStatus,
    SlaStatus,
    TicketStatus,
)
from app.domains.support.models import SupportTicket
from app.domains.users.models import User, UserRole
from app.domains.warranty.models import WarrantyClaim


def get_dashboard_summary(db: Session) -> DashboardSummaryOut:
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    vehicles_total = db.query(func.count(Vehicle.id)).filter(Vehicle.deleted_at.is_(None)).scalar() or 0
    vehicles_available = (
        db.query(func.count(Vehicle.id))
        .filter(Vehicle.deleted_at.is_(None), Vehicle.availability == AvailabilityStatus.available)
        .scalar()
        or 0
    )
    vehicles_reserved = (
        db.query(func.count(Vehicle.id))
        .filter(Vehicle.deleted_at.is_(None), Vehicle.availability == AvailabilityStatus.reserved)
        .scalar()
        or 0
    )

    customers_total = (
        db.query(func.count(User.id)).filter(User.role == UserRole.customer).scalar() or 0
    )
    customers_new = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.customer, User.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )

    staff_total = (
        db.query(func.count(User.id)).filter(User.role.in_([UserRole.staff, UserRole.admin])).scalar() or 0
    )
    staff_active = (
        db.query(func.count(User.id))
        .filter(User.role.in_([UserRole.staff, UserRole.admin]), User.is_active.is_(True))
        .scalar()
        or 0
    )

    open_statuses = (
        TicketStatus.open,
        TicketStatus.assigned,
        TicketStatus.in_progress,
        TicketStatus.waiting_customer,
    )
    open_tickets = (
        db.query(func.count(SupportTicket.id)).filter(SupportTicket.status.in_(open_statuses)).scalar() or 0
    )
    sla_at_risk = (
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.status.in_(open_statuses), SupportTicket.sla_status == SlaStatus.at_risk)
        .scalar()
        or 0
    )

    pending_claim_statuses = (ClaimStatus.submitted, ClaimStatus.under_review, ClaimStatus.escalated)
    pending_claims = (
        db.query(func.count(WarrantyClaim.id))
        .filter(WarrantyClaim.status.in_(pending_claim_statuses))
        .scalar()
        or 0
    )

    active_rules = (
        db.query(func.count(NotificationRule.id)).filter(NotificationRule.is_active.is_(True)).scalar() or 0
    )
    campaigns_sent = (
        db.query(func.count(BroadcastCampaign.id))
        .filter(BroadcastCampaign.status == BroadcastCampaignStatus.sent)
        .scalar()
        or 0
    )
    unread_notifications = (
        db.query(func.count(UserNotification.id)).filter(UserNotification.is_read.is_(False)).scalar() or 0
    )

    leads_active = _safe_leads_active_count(db)
    service_today, service_capacity = _safe_service_today_counts(db)

    return DashboardSummaryOut(
        vehiclesTotal=vehicles_total,
        vehiclesAvailable=vehicles_available,
        vehiclesReserved=vehicles_reserved,
        customersTotal=customers_total,
        customersNew30d=customers_new,
        staffTotal=staff_total,
        staffActive=staff_active,
        openSupportTickets=open_tickets,
        slaAtRiskTickets=sla_at_risk,
        pendingWarrantyClaims=pending_claims,
        activeNotificationRules=active_rules,
        campaignsSent=campaigns_sent,
        unreadNotificationsTotal=unread_notifications,
        leadsActive=leads_active,
        serviceToday=service_today,
        serviceCapacity=service_capacity,
    )


def _safe_leads_active_count(db: Session) -> int | None:
    try:
        from app.domains.leads.models import Lead
        from app.domains.shared.enums import LeadStatus

        active_statuses = (
            LeadStatus.new,
            LeadStatus.contacted,
            LeadStatus.qualified,
            LeadStatus.proposal,
            LeadStatus.negotiation,
        )
        return db.query(func.count(Lead.id)).filter(Lead.status.in_(active_statuses)).scalar() or 0
    except Exception:
        return None


def _safe_service_today_counts(db: Session) -> tuple[int | None, int | None]:
    try:
        from app.domains.service.models import ServiceAppointment, ServiceBay
        from app.domains.shared.enums import AppointmentStatus

        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        active_statuses = (
            AppointmentStatus.requested,
            AppointmentStatus.confirmed,
            AppointmentStatus.in_progress,
            AppointmentStatus.awaiting_approval,
        )
        today_count = (
            db.query(func.count(ServiceAppointment.id))
            .filter(
                ServiceAppointment.scheduled_at >= start,
                ServiceAppointment.scheduled_at < end,
                ServiceAppointment.status.in_(active_statuses),
            )
            .scalar()
            or 0
        )
        capacity = db.query(func.count(ServiceBay.id)).filter(ServiceBay.is_active.is_(True)).scalar() or 0
        return today_count, capacity or None
    except Exception:
        return None, None
