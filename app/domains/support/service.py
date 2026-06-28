import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.domains.shared.enums import MessageSender, SlaStatus, TicketCategory, TicketPriority, TicketStatus
from app.domains.support.models import SlaConfig, SupportTicket, TicketMessage
from app.domains.support.schemas import (
    PaginatedTicketsOut,
    SlaConfigOut,
    SlaConfigUpdateIn,
    SupportSummaryOut,
    SupportTicketDetailOut,
    SupportTicketListItemOut,
    TicketCreateIn,
    TicketMessageCreateOut,
    TicketMessageOut,
    TicketUpdateIn,
)
from app.domains.users.models import User, UserRole

OPEN_STATUSES = (
    TicketStatus.open,
    TicketStatus.assigned,
    TicketStatus.in_progress,
    TicketStatus.waiting_customer,
)


def get_summary(db: Session) -> SupportSummaryOut:
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    open_count = db.query(SupportTicket).filter(SupportTicket.status.in_(OPEN_STATUSES)).count()
    at_risk = db.query(SupportTicket).filter(SupportTicket.sla_status == SlaStatus.at_risk).count()
    unassigned = (
        db.query(SupportTicket)
        .filter(SupportTicket.status.in_(OPEN_STATUSES), SupportTicket.assigned_to_id.is_(None))
        .count()
    )
    resolved_today = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.status.in_((TicketStatus.resolved, TicketStatus.closed)),
            SupportTicket.resolved_at.isnot(None),
            SupportTicket.resolved_at >= start_of_day,
        )
        .count()
    )
    return SupportSummaryOut(
        openTickets=open_count,
        atRiskTickets=at_risk,
        unassignedTickets=unassigned,
        resolvedToday=resolved_today,
    )


def list_assignees(db: Session) -> list[dict[str, str]]:
    rows = (
        db.query(User)
        .filter(User.role.in_((UserRole.staff, UserRole.admin)), User.is_active.is_(True))
        .order_by(User.first_name.asc())
        .all()
    )
    return [{"id": u.id, "name": f"{u.first_name} {u.last_name}".strip()} for u in rows]


def list_sla_configs(db: Session) -> list[SlaConfigOut]:
    rows = db.query(SlaConfig).order_by(SlaConfig.category.asc()).all()
    return [SlaConfigOut.from_model(r) for r in rows]


def update_sla_config(db: Session, config_id: str, payload: SlaConfigUpdateIn) -> SlaConfigOut:
    row = db.get(SlaConfig, config_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA config not found")

    if payload.response_hours is not None:
        row.response_hours = payload.response_hours
    if payload.resolution_hours is not None:
        row.resolution_hours = payload.resolution_hours
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.commit()
    db.refresh(row)
    return SlaConfigOut.from_model(row)


def _next_ticket_number(db: Session) -> str:
    count = db.query(func.count(SupportTicket.id)).scalar() or 0
    return f"TKT-{count + 1001:04d}"


def create_ticket(db: Session, payload: TicketCreateIn) -> SupportTicketDetailOut:
    customer = db.get(User, payload.customer_id)
    if not customer or customer.role != UserRole.customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer")

    try:
        category = TicketCategory(payload.category.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category") from exc

    try:
        priority = TicketPriority(payload.priority.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid priority") from exc

    sla = db.query(SlaConfig).filter(SlaConfig.category == category, SlaConfig.is_active.is_(True)).one_or_none()
    response_hours = sla.response_hours if sla else 8
    resolution_hours = sla.resolution_hours if sla else 72

    now = datetime.now(timezone.utc)
    ticket = SupportTicket(
        ticket_number=_next_ticket_number(db),
        user_id=customer.id,
        category=category,
        subject=payload.subject.strip(),
        status=TicketStatus.open,
        priority=priority,
        first_response_due=now + timedelta(hours=response_hours),
        resolution_due=now + timedelta(hours=resolution_hours),
        sla_status=SlaStatus.ok,
    )
    db.add(ticket)
    db.flush()

    if payload.body and payload.body.strip():
        db.add(
            TicketMessage(
                ticket_id=ticket.id,
                sender_type=MessageSender.staff,
                sender_id=None,
                body=payload.body.strip(),
            )
        )

    db.commit()
    return get_ticket(db, ticket.id)


def list_tickets(
    db: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    sla_status: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedTicketsOut:
    query = (
        db.query(SupportTicket)
        .options(
            joinedload(SupportTicket.customer),
            joinedload(SupportTicket.assigned_to),
        )
        .order_by(SupportTicket.updated_at.desc())
    )

    if status and status.strip().lower() != "all":
        try:
            query = query.filter(SupportTicket.status == TicketStatus(status.strip().lower()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter") from exc

    if category and category.strip().lower() != "all":
        try:
            query = query.filter(SupportTicket.category == TicketCategory(category.strip().lower()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category filter") from exc

    if sla_status and sla_status.strip().lower() != "all":
        try:
            query = query.filter(SupportTicket.sla_status == SlaStatus(sla_status.strip().lower()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid slaStatus filter") from exc

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.join(SupportTicket.customer).filter(
            (SupportTicket.subject.ilike(term))
            | (SupportTicket.ticket_number.ilike(term))
            | (User.first_name.ilike(term))
            | (User.last_name.ilike(term))
        )

    total = query.count()
    offset = (page - 1) * size
    rows = query.offset(offset).limit(size).all()
    pages = max(1, math.ceil(total / size)) if total else 1

    return PaginatedTicketsOut(
        items=[SupportTicketListItemOut.from_model(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def get_ticket(db: Session, ticket_id: str) -> SupportTicketDetailOut:
    ticket = (
        db.query(SupportTicket)
        .options(
            joinedload(SupportTicket.customer),
            joinedload(SupportTicket.assigned_to),
            joinedload(SupportTicket.messages).joinedload(TicketMessage.sender),
        )
        .filter(SupportTicket.id == ticket_id)
        .one_or_none()
    )
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return SupportTicketDetailOut.from_model(ticket)


def update_ticket(db: Session, ticket_id: str, payload: TicketUpdateIn) -> SupportTicketDetailOut:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if payload.status is not None:
        try:
            new_status = TicketStatus(payload.status.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
        ticket.status = new_status
        if new_status in (TicketStatus.resolved, TicketStatus.closed) and not ticket.resolved_at:
            ticket.resolved_at = datetime.now(timezone.utc)

    if payload.priority is not None:
        try:
            ticket.priority = TicketPriority(payload.priority.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid priority") from exc

    if payload.assigned_to_id is not None:
        if payload.assigned_to_id == "":
            ticket.assigned_to_id = None
        else:
            assignee = db.get(User, payload.assigned_to_id)
            if not assignee or assignee.role not in (UserRole.staff, UserRole.admin):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee")
            ticket.assigned_to_id = assignee.id
            if ticket.status == TicketStatus.open:
                ticket.status = TicketStatus.assigned

    db.commit()
    return get_ticket(db, ticket_id)


def add_staff_message(db: Session, ticket_id: str, *, staff_user: User, body: str) -> TicketMessageCreateOut:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    message = TicketMessage(
        ticket_id=ticket.id,
        sender_type=MessageSender.staff,
        sender_id=staff_user.id,
        body=body.strip(),
    )
    db.add(message)

    if not ticket.first_response_at:
        ticket.first_response_at = now
    if ticket.status in (TicketStatus.open, TicketStatus.assigned):
        ticket.status = TicketStatus.in_progress

    db.commit()
    detail = get_ticket(db, ticket_id)
    latest = detail.messages[-1] if detail.messages else TicketMessageOut(
        id=message.id,
        senderType=MessageSender.staff.value,
        senderName=f"{staff_user.first_name} {staff_user.last_name}".strip(),
        body=message.body,
        createdAt=now.isoformat(),
    )
    return TicketMessageCreateOut(ticket=detail, message=latest)


def resolve_ticket(db: Session, ticket_id: str) -> SupportTicketDetailOut:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    ticket.status = TicketStatus.resolved
    ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return get_ticket(db, ticket_id)
