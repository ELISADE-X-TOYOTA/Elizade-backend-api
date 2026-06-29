from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.leads import service
from app.domains.leads.schemas import (
    LeadAssignIn,
    LeadCreateIn,
    LeadDetailOut,
    LeadLostIn,
    LeadNoteCreateIn,
    LeadNoteOut,
    LeadPipelineOut,
    LeadStatusUpdateIn,
    LeadUpdateIn,
    LeadWonIn,
    PaginatedLeadsOut,
)

router = APIRouter(prefix="/admin/leads", tags=["admin-leads"])


@router.get("/pipeline", response_model=LeadPipelineOut)
def get_pipeline(
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadPipelineOut:
    """
    KPI aggregations for the Lead Pipeline chart:
    counts and deal values per status, overall conversion rate,
    and new leads created this week.
    """
    return service.get_lead_pipeline(db)


@router.get("", response_model=PaginatedLeadsOut)
def list_leads(
    current_user: StaffPortalUser,
    status: str | None = Query(default=None, description="Filter by lead status"),
    source: str | None = Query(default=None, description="Filter by source (partial match)"),
    assignedAgentId: str | None = Query(default=None, description="Filter by assigned agent UUID"),
    branchId: str | None = Query(default=None, description="Filter by branch UUID (via linked vehicle)"),
    q: str | None = Query(default=None, description="Search by customer name, phone, email or model"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    size: int = Query(default=20, ge=1, le=100, description="Page size (max 100)"),
    db: Session = Depends(get_db),
) -> PaginatedLeadsOut:
    """
    Paginated list of all leads with optional filters.
    Ordered by most recently updated first.
    """
    return service.list_leads(
        db,
        status_filter=status,
        source=source,
        assigned_agent_id=assignedAgentId,
        branch_id=branchId,
        q=q,
        page=page,
        size=size,
    )


@router.get("/{lead_id}", response_model=LeadDetailOut)
def get_lead(
    lead_id: str,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Full lead detail including linked customer, vehicle, assigned agent,
    and a preview of the most recent activity notes.
    """
    return service.get_lead(db, lead_id)


@router.post("", response_model=LeadDetailOut, status_code=201)
def create_lead(
    payload: LeadCreateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Manually create a lead (showroom walk-in, phone inquiry, etc.).
    New leads always start with status = 'new'.
    """
    return service.create_lead(db, payload, current_user)


@router.patch("/{lead_id}", response_model=LeadDetailOut)
def update_lead(
    lead_id: str,
    payload: LeadUpdateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Update editable lead fields: model, value, source, notes,
    vehicleId, customerId. Partial update — only supplied fields are changed.
    """
    return service.update_lead(db, lead_id, payload)


@router.patch("/{lead_id}/status", response_model=LeadDetailOut)
def update_lead_status(
    lead_id: str,
    payload: LeadStatusUpdateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Move the lead to a new pipeline stage.
    Valid stages: new → contacted → qualified → proposal → negotiation.
    Back-transitions (e.g. negotiation → proposal) are permitted.
    Use /won and /lost endpoints for terminal transitions.
    """
    return service.update_lead_status(db, lead_id, payload, current_user)


@router.patch("/{lead_id}/assign", response_model=LeadDetailOut)
def assign_lead(
    lead_id: str,
    payload: LeadAssignIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Assign or reassign the lead to a staff / admin agent.
    The agent must be active.
    """
    return service.assign_lead(db, lead_id, payload)


@router.post("/{lead_id}/won", response_model=LeadDetailOut)
def mark_won(
    lead_id: str,
    payload: LeadWonIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Mark the lead as won. Optionally link the sold vehicle.
    Sets wonAt timestamp. Returns 409 if already won.
    """
    return service.mark_won(db, lead_id, payload, current_user)


@router.post("/{lead_id}/lost", response_model=LeadDetailOut)
def mark_lost(
    lead_id: str,
    payload: LeadLostIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadDetailOut:
    """
    Mark the lead as lost. lostReason is required.
    Sets lostAt timestamp. Returns 409 if already lost.
    """
    return service.mark_lost(db, lead_id, payload, current_user)


@router.get("/{lead_id}/notes", response_model=list[LeadNoteOut])
def get_notes(
    lead_id: str,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> list[LeadNoteOut]:
    """
    Retrieve the full activity log (notes) for a lead, newest first.
    """
    return service.get_notes(db, lead_id)


@router.post("/{lead_id}/notes", response_model=LeadNoteOut, status_code=201)
def add_note(
    lead_id: str,
    payload: LeadNoteCreateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> LeadNoteOut:
    """
    Append an activity note to a lead (call summary, follow-up, etc.).
    Notes are immutable once created — they serve as an audit trail.
    """
    return service.add_note(db, lead_id, payload, current_user)
