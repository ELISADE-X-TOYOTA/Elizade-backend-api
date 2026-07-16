from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.domains.branches.models import Branch
from app.domains.dashboard.schemas import (
    ActivityItemOut,
    BranchRowOut,
    DashboardOverviewOut,
    DashboardSummaryOut,
    HotLeadOut,
    InventoryModelRowOut,
    LeadSourceOut,
    MonthlyCountOut,
    PipelineStageOut,
    RevenueMonthOut,
    ServiceSlotOut,
    ServiceTypeRowOut,
    SlaTicketOut,
    StaffPerformanceOut,
    WeeklyLoadOut,
)
from app.domains.inventory.models import Vehicle
from app.domains.leads.models import Lead
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.service.models import ServiceAppointment, ServiceBay, ServiceHistoryItem
from app.domains.shared.enums import (
    AppointmentStatus,
    AvailabilityStatus,
    BroadcastCampaignStatus,
    ClaimStatus,
    LeadStatus,
    SlaStatus,
    TicketStatus,
)
from app.domains.support.models import SupportTicket
from app.domains.users.models import User, UserRole
from app.domains.warranty.models import WarrantyClaim

_PIPELINE_STAGES: list[tuple[LeadStatus, str]] = [
    (LeadStatus.new, "New"),
    (LeadStatus.contacted, "Contacted"),
    (LeadStatus.qualified, "Qualified"),
    (LeadStatus.proposal, "Proposal"),
    (LeadStatus.negotiation, "Negotiation"),
    (LeadStatus.won, "Won"),
    (LeadStatus.lost, "Lost"),
]

_HOT_LEAD_STATUSES = (
    LeadStatus.qualified,
    LeadStatus.proposal,
    LeadStatus.negotiation,
)

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _today_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _month_starts(count: int = 6) -> list[tuple[str, datetime, datetime]]:
    now = datetime.now(timezone.utc)
    months: list[tuple[str, datetime, datetime]] = []
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(count):
        label = cursor.strftime("%b")
        start = cursor
        if cursor.month == 12:
            end = cursor.replace(year=cursor.year + 1, month=1)
        else:
            end = cursor.replace(month=cursor.month + 1)
        months.insert(0, (label, start, end))
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    return months


def get_dashboard_summary(db: Session) -> DashboardSummaryOut:
    return get_dashboard_overview(db).summary


def get_dashboard_overview(db: Session) -> DashboardOverviewOut:
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    week_ago = now - timedelta(days=7)
    today_start, today_end = _today_bounds()

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
    vehicles_sold = (
        db.query(func.count(Vehicle.id))
        .filter(Vehicle.deleted_at.is_(None), Vehicle.availability == AvailabilityStatus.sold)
        .scalar()
        or 0
    )

    customers_total = db.query(func.count(User.id)).filter(User.role == UserRole.customer).scalar() or 0
    customers_new = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.customer, User.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )
    customers_with_vehicle = (
        db.query(func.count(User.id)).filter(User.role == UserRole.customer, User.owned_vehicles.any()).scalar() or 0
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

    branches_total = db.query(func.count(Branch.id)).scalar() or 0
    branches_active = db.query(func.count(Branch.id)).filter(Branch.is_active.is_(True)).scalar() or 0

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

    active_lead_statuses = (
        LeadStatus.new,
        LeadStatus.contacted,
        LeadStatus.qualified,
        LeadStatus.proposal,
        LeadStatus.negotiation,
    )
    leads_active = (
        db.query(func.count(Lead.id)).filter(Lead.status.in_(active_lead_statuses)).scalar() or 0
    )
    pipeline_value = float(
        db.query(func.coalesce(func.sum(Lead.value), 0))
        .filter(Lead.status.in_(active_lead_statuses))
        .scalar()
        or 0
    )
    leads_new_week = (
        db.query(func.count(Lead.id)).filter(Lead.created_at >= week_ago).scalar() or 0
    )
    won_count = db.query(func.count(Lead.id)).filter(Lead.status == LeadStatus.won).scalar() or 0
    lost_count = db.query(func.count(Lead.id)).filter(Lead.status == LeadStatus.lost).scalar() or 0
    conversion_rate = round((won_count / (won_count + lost_count)) * 100, 1) if (won_count + lost_count) else 0.0

    service_today = (
        db.query(func.count(ServiceAppointment.id))
        .filter(ServiceAppointment.scheduled_at >= today_start, ServiceAppointment.scheduled_at < today_end)
        .scalar()
        or 0
    )
    service_in_progress = (
        db.query(func.count(ServiceAppointment.id))
        .filter(
            ServiceAppointment.scheduled_at >= today_start,
            ServiceAppointment.scheduled_at < today_end,
            ServiceAppointment.status == AppointmentStatus.in_progress,
        )
        .scalar()
        or 0
    )
    service_awaiting = (
        db.query(func.count(ServiceAppointment.id))
        .filter(
            ServiceAppointment.scheduled_at >= today_start,
            ServiceAppointment.scheduled_at < today_end,
            ServiceAppointment.status == AppointmentStatus.awaiting_approval,
        )
        .scalar()
        or 0
    )
    service_completed_today = (
        db.query(func.count(ServiceAppointment.id))
        .filter(
            ServiceAppointment.scheduled_at >= today_start,
            ServiceAppointment.scheduled_at < today_end,
            ServiceAppointment.status == AppointmentStatus.completed,
        )
        .scalar()
        or 0
    )
    service_capacity = db.query(func.count(ServiceBay.id)).filter(ServiceBay.is_active.is_(True)).scalar() or 0

    summary = DashboardSummaryOut(
        vehiclesTotal=vehicles_total,
        vehiclesAvailable=vehicles_available,
        vehiclesReserved=vehicles_reserved,
        vehiclesSold=vehicles_sold,
        customersTotal=customers_total,
        customersNew30d=customers_new,
        customersWithVehicle=customers_with_vehicle,
        staffTotal=staff_total,
        staffActive=staff_active,
        branchesTotal=branches_total,
        branchesActive=branches_active,
        openSupportTickets=open_tickets,
        slaAtRiskTickets=sla_at_risk,
        pendingWarrantyClaims=pending_claims,
        activeNotificationRules=active_rules,
        campaignsSent=campaigns_sent,
        unreadNotificationsTotal=unread_notifications,
        leadsActive=leads_active,
        leadsPipelineValue=pipeline_value,
        leadsNewThisWeek=leads_new_week,
        leadsConversionRate=conversion_rate,
        serviceToday=service_today,
        serviceInProgress=service_in_progress,
        serviceAwaitingApproval=service_awaiting,
        serviceCapacity=service_capacity,
        serviceCompletedToday=service_completed_today,
    )

    lead_pipeline: list[PipelineStageOut] = []
    for status, label in _PIPELINE_STAGES:
        row = (
            db.query(func.count(Lead.id), func.coalesce(func.sum(Lead.value), 0))
            .filter(Lead.status == status)
            .one()
        )
        lead_pipeline.append(
            PipelineStageOut(
                stage=label,
                status=status.value,
                count=row[0] or 0,
                value=float(row[1] or 0),
            )
        )

    source_rows = (
        db.query(Lead.source, func.count(Lead.id))
        .group_by(Lead.source)
        .order_by(func.count(Lead.id).desc())
        .limit(6)
        .all()
    )
    lead_sources = [LeadSourceOut(source=src, count=cnt) for src, cnt in source_rows]

    hot_lead_rows = (
        db.query(Lead)
        .options(joinedload(Lead.assigned_agent))
        .filter(Lead.status.in_(_HOT_LEAD_STATUSES))
        .order_by(Lead.value.desc(), Lead.updated_at.desc())
        .limit(5)
        .all()
    )
    hot_leads = [
        HotLeadOut(
            id=lead.id,
            customerName=lead.customer_name,
            interestedModel=lead.interested_model,
            status=lead.status.value,
            value=float(lead.value),
            assignedAgent=(
                f"{lead.assigned_agent.first_name} {lead.assigned_agent.last_name}".strip()
                if lead.assigned_agent
                else None
            ),
        )
        for lead in hot_lead_rows
    ]

    appt_rows = (
        db.query(ServiceAppointment)
        .options(
            joinedload(ServiceAppointment.customer),
            joinedload(ServiceAppointment.owned_vehicle),
            joinedload(ServiceAppointment.branch),
            joinedload(ServiceAppointment.bay),
        )
        .filter(ServiceAppointment.scheduled_at >= today_start, ServiceAppointment.scheduled_at < today_end)
        .order_by(ServiceAppointment.scheduled_at.asc())
        .limit(8)
        .all()
    )
    today_service: list[ServiceSlotOut] = []
    for appt in appt_rows:
        vehicle = appt.owned_vehicle
        branch = appt.branch
        bay = appt.bay
        customer = appt.customer
        today_service.append(
            ServiceSlotOut(
                id=appt.id,
                time=appt.scheduled_at.strftime("%H:%M"),
                customerName=f"{customer.first_name} {customer.last_name}".strip() if customer else "Customer",
                vehicleLabel=f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "Vehicle",
                branchName=branch.name if branch else "",
                bayName=bay.name if bay else None,
                status=appt.status.value,
            )
        )

    sla_rows = (
        db.query(SupportTicket)
        .options(joinedload(SupportTicket.assigned_to))
        .filter(SupportTicket.status.in_(open_statuses), SupportTicket.sla_status == SlaStatus.at_risk)
        .order_by(SupportTicket.created_at.desc())
        .limit(5)
        .all()
    )
    sla_tickets = [
        SlaTicketOut(
            id=ticket.id,
            ticketNumber=ticket.ticket_number,
            subject=ticket.subject,
            assignedTo=(
                f"{ticket.assigned_to.first_name} {ticket.assigned_to.last_name}".strip()
                if ticket.assigned_to
                else None
            ),
        )
        for ticket in sla_rows
    ]

    model_rows = (
        db.query(
            Vehicle.model,
            func.count(Vehicle.id).filter(Vehicle.availability == AvailabilityStatus.sold).label("sold"),
            func.count(Vehicle.id).filter(Vehicle.availability == AvailabilityStatus.available).label("available"),
        )
        .filter(Vehicle.deleted_at.is_(None))
        .group_by(Vehicle.model)
        .order_by(func.count(Vehicle.id).desc())
        .limit(6)
        .all()
    )
    inventory_by_model = [
        InventoryModelRowOut(model=row.model, sold=row.sold or 0, available=row.available or 0) for row in model_rows
    ]

    quarter_start = now - timedelta(days=90)
    service_type_rows = (
        db.query(ServiceAppointment.service_type, func.count(ServiceAppointment.id))
        .filter(ServiceAppointment.scheduled_at >= quarter_start)
        .group_by(ServiceAppointment.service_type)
        .all()
    )
    service_by_type = [
        ServiceTypeRowOut(type=row[0].value.replace("_", " ").title(), count=row[1]) for row in service_type_rows
    ]

    branch_rows = db.query(Branch).filter(Branch.is_active.is_(True)).order_by(Branch.name.asc()).all()
    branch_stats: list[BranchRowOut] = []
    for branch in branch_rows:
        vehicles = (
            db.query(func.count(Vehicle.id))
            .filter(Vehicle.branch_id == branch.id, Vehicle.deleted_at.is_(None))
            .scalar()
            or 0
        )
        appts = (
            db.query(func.count(ServiceAppointment.id))
            .filter(
                ServiceAppointment.branch_id == branch.id,
                ServiceAppointment.scheduled_at >= today_start,
                ServiceAppointment.scheduled_at < today_end,
            )
            .scalar()
            or 0
        )
        branch_leads = (
            db.query(func.count(Lead.id))
            .join(Vehicle, Lead.vehicle_id == Vehicle.id)
            .filter(Vehicle.branch_id == branch.id, Lead.status.in_(active_lead_statuses))
            .scalar()
            or 0
        )
        branch_stats.append(
            BranchRowOut(
                id=branch.id,
                name=branch.name,
                vehicles=vehicles,
                appointmentsToday=appts,
                activeLeads=branch_leads,
            )
        )

    week_start = today_start - timedelta(days=today_start.weekday())
    weekly_service_load: list[WeeklyLoadOut] = []
    for i, label in enumerate(_WEEKDAY_LABELS):
        day_start = week_start + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        booked = (
            db.query(func.count(ServiceAppointment.id))
            .filter(ServiceAppointment.scheduled_at >= day_start, ServiceAppointment.scheduled_at < day_end)
            .scalar()
            or 0
        )
        completed = (
            db.query(func.count(ServiceAppointment.id))
            .filter(
                ServiceAppointment.scheduled_at >= day_start,
                ServiceAppointment.scheduled_at < day_end,
                ServiceAppointment.status == AppointmentStatus.completed,
            )
            .scalar()
            or 0
        )
        weekly_service_load.append(WeeklyLoadOut(day=label, booked=booked, completed=completed))

    customer_signups: list[MonthlyCountOut] = []
    for label, start, end in _month_starts(6):
        count = (
            db.query(func.count(User.id))
            .filter(User.role == UserRole.customer, User.created_at >= start, User.created_at < end)
            .scalar()
            or 0
        )
        customer_signups.append(MonthlyCountOut(month=label, customers=count))

    revenue_by_month: list[RevenueMonthOut] = []
    for label, start, end in _month_starts(6):
        sales_sum = (
            db.query(func.coalesce(func.sum(Lead.value), 0))
            .filter(Lead.status == LeadStatus.won, Lead.won_at >= start, Lead.won_at < end)
            .scalar()
            or 0
        )
        service_sum = (
            db.query(func.coalesce(func.sum(ServiceHistoryItem.cost), 0))
            .filter(ServiceHistoryItem.performed_at >= start, ServiceHistoryItem.performed_at < end)
            .scalar()
            or 0
        )
        revenue_by_month.append(
            RevenueMonthOut(
                month=label,
                sales=round(float(Decimal(str(sales_sum))) / 1_000_000, 1),
                service=round(float(Decimal(str(service_sum))) / 1_000_000, 1),
            )
        )

    recent_activity = _build_activity_feed(db)

    staff_rows = (
        db.query(User)
        .filter(User.role.in_([UserRole.staff, UserRole.admin]), User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .limit(6)
        .all()
    )
    staff_performance: list[StaffPerformanceOut] = []
    for member in staff_rows:
        won = (
            db.query(func.count(Lead.id))
            .filter(Lead.assigned_agent_id == member.id, Lead.status == LeadStatus.won)
            .scalar()
            or 0
        )
        tickets = (
            db.query(func.count(SupportTicket.id))
            .filter(SupportTicket.assigned_to_id == member.id, SupportTicket.status.in_(open_statuses))
            .scalar()
            or 0
        )
        staff_performance.append(
            StaffPerformanceOut(
                id=member.id,
                name=f"{member.first_name} {member.last_name}".strip(),
                department=member.department or "Operations",
                leadsWon=won,
                ticketsOpen=tickets,
            )
        )

    return DashboardOverviewOut(
        summary=summary,
        leadPipeline=lead_pipeline,
        leadSources=lead_sources,
        hotLeads=hot_leads,
        todayService=today_service,
        slaTickets=sla_tickets,
        inventoryByModel=inventory_by_model,
        serviceByType=service_by_type,
        branchStats=branch_stats,
        weeklyServiceLoad=weekly_service_load,
        customerSignupsByMonth=customer_signups,
        revenueByMonth=revenue_by_month,
        recentActivity=recent_activity,
        staffPerformance=staff_performance,
    )


def _build_activity_feed(db: Session) -> list[ActivityItemOut]:
    items: list[ActivityItemOut] = []

    for lead in db.query(Lead).order_by(Lead.created_at.desc()).limit(4).all():
        items.append(
            ActivityItemOut(
                id=f"lead-{lead.id}",
                text=f"New lead: {lead.customer_name} · {lead.interested_model}",
                meta=f"{lead.source} · {lead.status.value}",
                time=lead.created_at,
                color="violet",
            )
        )

    open_statuses = (
        TicketStatus.open,
        TicketStatus.assigned,
        TicketStatus.in_progress,
        TicketStatus.waiting_customer,
    )
    for ticket in (
        db.query(SupportTicket)
        .filter(SupportTicket.status.in_(open_statuses))
        .order_by(SupportTicket.created_at.desc())
        .limit(3)
        .all()
    ):
        items.append(
            ActivityItemOut(
                id=f"ticket-{ticket.id}",
                text=ticket.subject,
                meta=f"{ticket.ticket_number} · {ticket.category.value}",
                time=ticket.created_at,
                color="rose" if ticket.sla_status == SlaStatus.at_risk else "amber",
            )
        )

    today_start, today_end = _today_bounds()
    for appt in (
        db.query(ServiceAppointment)
        .filter(ServiceAppointment.scheduled_at >= today_start, ServiceAppointment.scheduled_at < today_end)
        .order_by(ServiceAppointment.updated_at.desc())
        .limit(3)
        .all()
    ):
        customer = appt.customer
        items.append(
            ActivityItemOut(
                id=f"appt-{appt.id}",
                text=f"Service {appt.status.value.replace('_', ' ')} — {customer.first_name if customer else 'Customer'}",
                meta=appt.service_type.value.replace("_", " "),
                time=appt.updated_at,
                color="sky",
            )
        )

    pending = (ClaimStatus.submitted, ClaimStatus.under_review, ClaimStatus.escalated)
    for claim in (
        db.query(WarrantyClaim)
        .filter(WarrantyClaim.status.in_(pending))
        .order_by(WarrantyClaim.created_at.desc())
        .limit(2)
        .all()
    ):
        items.append(
            ActivityItemOut(
                id=f"claim-{claim.id}",
                text=f"Warranty claim: {claim.claim_type}",
                meta=claim.status.value.replace("_", " "),
                time=claim.created_at,
                color="emerald",
            )
        )

    items.sort(key=lambda x: x.time, reverse=True)
    return items[:10]
