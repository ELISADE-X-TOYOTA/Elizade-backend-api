"""
Leads service layer — all business logic for the sales pipeline.

State machine (valid forward path):
    new → contacted → qualified → proposal → negotiation → won / lost

Back-transitions (re-qualification) are permitted between non-terminal stages.
won and lost are terminal: they can only be reached via the dedicated
/won and /lost endpoints, and cannot be changed via /status.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.leads.models import Lead, LeadNote
from app.domains.leads.schemas import (
    AgentBrief,
    CustomerBrief,
    LeadAssignIn,
    LeadCreateIn,
    LeadDetailOut,
    LeadListItemOut,
    LeadLostIn,
    LeadNoteCreateIn,
    LeadNoteOut,
    LeadPipelineOut,
    LeadStatusUpdateIn,
    LeadUpdateIn,
    LeadWonIn,
    PaginatedLeadsOut,
    StatusCountOut,
    VehicleBrief,
)
from app.domains.shared.enums import LeadStatus
from app.domains.users.models import User, UserRole

# ---------------------------------------------------------------------------
# Terminal statuses — cannot be changed via /status
# ---------------------------------------------------------------------------
TERMINAL_STATUSES = {LeadStatus.won, LeadStatus.lost}

# Valid pipeline stages reachable via /status (excludes terminal statuses)
PIPELINE_STAGES = [
    LeadStatus.new,
    LeadStatus.contacted,
    LeadStatus.qualified,
    LeadStatus.proposal,
    LeadStatus.negotiation,
]


# ---------------------------------------------------------------------------
# Helper: fetch lead or raise 404
# ---------------------------------------------------------------------------

def _get_lead_or_404(db: Session, lead_id: str) -> Lead:
    """Fetch lead with all eagerly-loaded relationships, raising 404 if absent."""
    lead = (
        db.query(Lead)
        .options(
            joinedload(Lead.customer),
            joinedload(Lead.assigned_agent),
            joinedload(Lead.vehicle),
            selectinload(Lead.activity).joinedload(LeadNote.author),
        )
        .filter(Lead.id == lead_id)
        .one_or_none()
    )
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


# ---------------------------------------------------------------------------
# Helper: map ORM → output schema
# ---------------------------------------------------------------------------

def _note_to_out(note: LeadNote) -> LeadNoteOut:
    author_name = "System"
    if note.author:
        author_name = f"{note.author.first_name} {note.author.last_name}".strip()
    return LeadNoteOut(
        id=note.id,
        leadId=note.lead_id,
        authorId=note.author_id,
        authorName=author_name,
        body=note.body,
        createdAt=note.created_at,
    )


def _agent_brief(user: User | None) -> AgentBrief | None:
    if not user:
        return None
    return AgentBrief(
        id=user.id,
        firstName=user.first_name,
        lastName=user.last_name,
        email=user.email,
    )


def _customer_brief(user: User | None) -> CustomerBrief | None:
    if not user:
        return None
    return CustomerBrief(
        id=user.id,
        firstName=user.first_name,
        lastName=user.last_name,
        email=user.email,
        phone=user.phone_display,
    )


def _vehicle_brief(vehicle) -> VehicleBrief | None:
    if not vehicle:
        return None
    return VehicleBrief(
        id=vehicle.id,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        year=vehicle.year,
        color=vehicle.color,
        price=vehicle.price,
    )


def _lead_to_list_item(lead: Lead) -> LeadListItemOut:
    return LeadListItemOut(
        id=lead.id,
        customerName=lead.customer_name,
        email=lead.email,
        phone=lead.phone,
        source=lead.source,
        status=lead.status.value,
        interestedModel=lead.interested_model,
        value=lead.value,
        assignedAgent=_agent_brief(lead.assigned_agent),
        customer=_customer_brief(lead.customer),
        createdAt=lead.created_at,
        updatedAt=lead.updated_at,
    )


def _lead_to_detail(lead: Lead) -> LeadDetailOut:
    notes_out = sorted(
        [_note_to_out(n) for n in lead.activity],
        key=lambda n: n.createdAt,
        reverse=True,
    )
    return LeadDetailOut(
        id=lead.id,
        customerName=lead.customer_name,
        email=lead.email,
        phone=lead.phone,
        source=lead.source,
        status=lead.status.value,
        interestedModel=lead.interested_model,
        value=lead.value,
        notes=lead.notes,
        wonAt=lead.won_at,
        lostAt=lead.lost_at,
        lostReason=lead.lost_reason,
        assignedAgent=_agent_brief(lead.assigned_agent),
        customer=_customer_brief(lead.customer),
        vehicle=_vehicle_brief(lead.vehicle),
        activity=notes_out,
        createdAt=lead.created_at,
        updatedAt=lead.updated_at,
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_customer(db: Session, customer_id: str) -> User:
    """Return a verified customer User or raise 400."""
    user = db.get(User, customer_id)
    if not user or user.role != UserRole.customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer: user not found or not a customer",
        )
    return user


def _validate_agent(db: Session, agent_id: str) -> User:
    """Return an active staff/admin User or raise 400."""
    user = db.get(User, agent_id)
    if not user or user.role not in (UserRole.staff, UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid agent: user not found or not a staff/admin member",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned agent account is deactivated",
        )
    return user


def _validate_vehicle(db: Session, vehicle_id: str):
    """Return a Vehicle or raise 400."""
    from app.domains.inventory.models import Vehicle  # avoid circular import at module level

    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid vehicle: not found or has been removed",
        )
    return vehicle


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def list_leads(
    db: Session,
    *,
    status_filter: str | None = None,
    source: str | None = None,
    assigned_agent_id: str | None = None,
    branch_id: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedLeadsOut:
    if page < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page must be ≥ 1")
    if not (1 <= size <= 100):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Size must be between 1 and 100")

    query = (
        db.query(Lead)
        .options(
            joinedload(Lead.customer),
            joinedload(Lead.assigned_agent),
        )
    )

    # Status filter
    if status_filter and status_filter.strip().lower() not in ("all", ""):
        try:
            parsed_status = LeadStatus(status_filter.strip().lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{status_filter}'. Valid: {', '.join(s.value for s in LeadStatus)}",
            )
        query = query.filter(Lead.status == parsed_status)

    # Source filter (case-insensitive substring)
    if source and source.strip():
        query = query.filter(Lead.source.ilike(f"%{source.strip()}%"))

    # Agent filter
    if assigned_agent_id and assigned_agent_id.strip():
        query = query.filter(Lead.assigned_agent_id == assigned_agent_id.strip())

    # Branch filter — leads don't have a branch FK directly; filter via vehicle
    if branch_id and branch_id.strip():
        from app.domains.inventory.models import Vehicle
        query = query.join(Lead.vehicle).filter(Vehicle.branch_id == branch_id.strip())

    # Free-text search across customer name, phone, email, interested model
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Lead.customer_name.ilike(term),
                Lead.phone.ilike(term),
                Lead.email.ilike(term),
                Lead.interested_model.ilike(term),
            )
        )

    total = query.count()
    offset = (page - 1) * size
    rows = query.order_by(Lead.updated_at.desc()).offset(offset).limit(size).all()
    pages = math.ceil(total / size) if total > 0 else 0

    return PaginatedLeadsOut(
        items=[_lead_to_list_item(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def get_lead_pipeline(db: Session) -> LeadPipelineOut:
    """Return KPI aggregations for the pipeline chart."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Aggregate count + sum per status in a single pass
    rows = (
        db.query(
            Lead.status,
            func.count(Lead.id).label("cnt"),
            func.coalesce(func.sum(Lead.value), 0).label("val"),
        )
        .group_by(Lead.status)
        .all()
    )

    by_status: list[StatusCountOut] = []
    total_leads = 0
    total_value = Decimal("0")
    won_count = 0
    lost_count = 0

    for row in rows:
        total_leads += row.cnt
        total_value += Decimal(str(row.val))
        by_status.append(
            StatusCountOut(
                status=row.status.value,
                count=row.cnt,
                value=Decimal(str(row.val)),
            )
        )
        if row.status == LeadStatus.won:
            won_count = row.cnt
        elif row.status == LeadStatus.lost:
            lost_count = row.cnt

    # Conversion rate: won / (won + lost) × 100
    decisive = won_count + lost_count
    conversion_rate = round((won_count / decisive) * 100, 2) if decisive > 0 else 0.0

    new_this_week: int = (
        db.query(func.count(Lead.id))
        .filter(Lead.created_at >= week_ago)
        .scalar()
        or 0
    )

    return LeadPipelineOut(
        totalLeads=total_leads,
        totalValue=total_value,
        conversionRate=conversion_rate,
        newThisWeek=new_this_week,
        byStatus=by_status,
    )


def get_lead(db: Session, lead_id: str) -> LeadDetailOut:
    return _lead_to_detail(_get_lead_or_404(db, lead_id))


def create_lead(db: Session, payload: LeadCreateIn, current_user: User) -> LeadDetailOut:
    """Create a lead manually (showroom walk-in / phone inquiry)."""
    customer_id: str | None = None
    vehicle_id: str | None = None
    assigned_agent_id: str | None = None

    if payload.customerId:
        cust = _validate_customer(db, payload.customerId)
        customer_id = cust.id

    if payload.vehicleId:
        veh = _validate_vehicle(db, payload.vehicleId)
        vehicle_id = veh.id

    if payload.assignedAgentId:
        agent = _validate_agent(db, payload.assignedAgentId)
        assigned_agent_id = agent.id

    lead = Lead(
        customer_id=customer_id,
        customer_name=payload.customerName,
        email=payload.email,
        phone=payload.phone,
        source=payload.source,
        status=LeadStatus.new,
        interested_model=payload.interestedModel,
        vehicle_id=vehicle_id,
        assigned_agent_id=assigned_agent_id,
        value=payload.value,
        notes=payload.notes,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _lead_to_detail(_get_lead_or_404(db, lead.id))


def update_lead(db: Session, lead_id: str, payload: LeadUpdateIn) -> LeadDetailOut:
    """Partial update of a lead's editable fields.

    Won/lost leads can still have their notes, source, and value updated
    (e.g. to record the final agreed price), but phone/email/name changes
    are also allowed since records may need to be corrected.
    """
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    if payload.customerName is not None:
        lead.customer_name = payload.customerName.strip()
    if payload.email is not None:
        lead.email = payload.email.strip().lower() if payload.email.strip() else None
    if payload.phone is not None:
        lead.phone = payload.phone.strip()
    if payload.source is not None:
        lead.source = payload.source.strip()
    if payload.interestedModel is not None:
        lead.interested_model = payload.interestedModel.strip()
    if payload.value is not None:
        lead.value = payload.value
    if payload.notes is not None:
        lead.notes = payload.notes

    # Link / unlink customer
    if payload.customerId is not None:
        if payload.customerId == "":
            lead.customer_id = None
        else:
            cust = _validate_customer(db, payload.customerId)
            lead.customer_id = cust.id

    # Link / unlink vehicle
    if payload.vehicleId is not None:
        if payload.vehicleId == "":
            lead.vehicle_id = None
        else:
            veh = _validate_vehicle(db, payload.vehicleId)
            lead.vehicle_id = veh.id

    db.commit()
    return _lead_to_detail(_get_lead_or_404(db, lead_id))


def update_lead_status(
    db: Session, lead_id: str, payload: LeadStatusUpdateIn, current_user: User
) -> LeadDetailOut:
    """Move a lead to a new pipeline stage.

    Rules:
    - won and lost are terminal — they cannot be set via this endpoint.
    - Currently-won / lost leads cannot have their status changed here either.
    - Back-transitions between non-terminal stages are allowed (re-qualification).
    """
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    # Reject terminal statuses
    try:
        new_status = LeadStatus(payload.status.strip().lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{payload.status}'. Valid pipeline stages: {', '.join(s.value for s in PIPELINE_STAGES)}",
        )

    if new_status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Use the /{new_status.value} endpoint to mark a lead as {new_status.value}",
        )

    if lead.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Lead is already {lead.status.value}. Terminal status cannot be changed via /status",
        )

    lead.status = new_status

    # Auto-append a transition note if caller supplied one
    if payload.notes and payload.notes.strip():
        db.add(
            LeadNote(
                lead_id=lead.id,
                author_id=current_user.id,
                body=payload.notes.strip(),
            )
        )

    db.commit()
    return _lead_to_detail(_get_lead_or_404(db, lead_id))


def assign_lead(db: Session, lead_id: str, payload: LeadAssignIn) -> LeadDetailOut:
    """Assign or reassign a lead to a staff / admin agent."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    agent = _validate_agent(db, payload.assignedAgentId)
    lead.assigned_agent_id = agent.id

    db.commit()
    return _lead_to_detail(_get_lead_or_404(db, lead_id))


def mark_won(db: Session, lead_id: str, payload: LeadWonIn, current_user: User) -> LeadDetailOut:
    """Mark a lead as won."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    if lead.status == LeadStatus.won:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead is already marked as won")

    if lead.status == LeadStatus.lost:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead is already lost. Re-open it via /status before marking won",
        )

    vehicle_id = lead.vehicle_id
    if payload.vehicleId:
        veh = _validate_vehicle(db, payload.vehicleId)
        vehicle_id = veh.id

    lead.status = LeadStatus.won
    lead.won_at = datetime.now(timezone.utc)
    lead.vehicle_id = vehicle_id

    if payload.notes and payload.notes.strip():
        db.add(
            LeadNote(
                lead_id=lead.id,
                author_id=current_user.id,
                body=f"[Won] {payload.notes.strip()}",
            )
        )

    db.commit()
    return _lead_to_detail(_get_lead_or_404(db, lead_id))


def mark_lost(db: Session, lead_id: str, payload: LeadLostIn, current_user: User) -> LeadDetailOut:
    """Mark a lead as lost — loss reason is mandatory."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    if lead.status == LeadStatus.lost:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead is already marked as lost")

    if lead.status == LeadStatus.won:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead is already won. Re-open it via /status before marking lost",
        )

    if not payload.lostReason or not payload.lostReason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lostReason is required when marking a lead as lost",
        )

    lead.status = LeadStatus.lost
    lead.lost_at = datetime.now(timezone.utc)
    lead.lost_reason = payload.lostReason.strip()

    if payload.notes and payload.notes.strip():
        db.add(
            LeadNote(
                lead_id=lead.id,
                author_id=current_user.id,
                body=f"[Lost] {payload.notes.strip()}",
            )
        )

    db.commit()
    return _lead_to_detail(_get_lead_or_404(db, lead_id))


def get_notes(db: Session, lead_id: str) -> list[LeadNoteOut]:
    """Return all activity notes for a lead, newest first."""
    # Verify lead exists
    exists = db.query(Lead.id).filter(Lead.id == lead_id).first()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    notes = (
        db.query(LeadNote)
        .options(joinedload(LeadNote.author))
        .filter(LeadNote.lead_id == lead_id)
        .order_by(LeadNote.created_at.desc())
        .all()
    )
    return [_note_to_out(n) for n in notes]


def add_note(
    db: Session, lead_id: str, payload: LeadNoteCreateIn, current_user: User
) -> LeadNoteOut:
    """Append a new activity note to a lead."""
    exists = db.query(Lead.id).filter(Lead.id == lead_id).first()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    note = LeadNote(
        lead_id=lead_id,
        author_id=current_user.id,
        body=payload.body.strip(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    # Re-fetch with author loaded
    note = (
        db.query(LeadNote)
        .options(joinedload(LeadNote.author))
        .filter(LeadNote.id == note.id)
        .one()
    )
    return _note_to_out(note)
