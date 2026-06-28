from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.support import service
from app.domains.support.schemas import (
    AssigneeOut,
    PaginatedTicketsOut,
    SlaConfigOut,
    SlaConfigUpdateIn,
    SupportSummaryOut,
    SupportTicketDetailOut,
    TicketCreateIn,
    TicketMessageCreateIn,
    TicketMessageCreateOut,
    TicketUpdateIn,
)

router = APIRouter(prefix="/admin/support", tags=["admin-support"])


@router.get("/summary", response_model=SupportSummaryOut)
def get_summary(_: StaffPortalUser, db: Session = Depends(get_db)) -> SupportSummaryOut:
    return service.get_summary(db)


@router.get("/assignees", response_model=list[AssigneeOut])
def list_assignees(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[AssigneeOut]:
    return service.list_assignees(db)


@router.get("/sla-configs", response_model=list[SlaConfigOut])
def list_sla_configs(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[SlaConfigOut]:
    return service.list_sla_configs(db)


@router.patch("/sla-configs/{config_id}", response_model=SlaConfigOut)
def update_sla_config(
    config_id: str,
    payload: SlaConfigUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> SlaConfigOut:
    return service.update_sla_config(db, config_id, payload)


@router.get("/tickets", response_model=PaginatedTicketsOut)
def list_tickets(
    _: StaffPortalUser,
    status: str | None = Query(default="all"),
    category: str | None = Query(default="all"),
    sla_status: str | None = Query(default="all", alias="slaStatus"),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedTicketsOut:
    return service.list_tickets(
        db,
        status=status,
        category=category,
        sla_status=sla_status,
        q=q,
        page=page,
        size=size,
    )


@router.post("/tickets", response_model=SupportTicketDetailOut, status_code=201)
def create_ticket(
    payload: TicketCreateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> SupportTicketDetailOut:
    return service.create_ticket(db, payload)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetailOut)
def get_ticket(ticket_id: str, _: StaffPortalUser, db: Session = Depends(get_db)) -> SupportTicketDetailOut:
    return service.get_ticket(db, ticket_id)


@router.patch("/tickets/{ticket_id}", response_model=SupportTicketDetailOut)
def update_ticket(
    ticket_id: str,
    payload: TicketUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> SupportTicketDetailOut:
    return service.update_ticket(db, ticket_id, payload)


@router.post("/tickets/{ticket_id}/messages", response_model=TicketMessageCreateOut)
def reply_to_ticket(
    ticket_id: str,
    payload: TicketMessageCreateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> TicketMessageCreateOut:
    return service.add_staff_message(db, ticket_id, staff_user=current_user, body=payload.body)


@router.post("/tickets/{ticket_id}/resolve", response_model=SupportTicketDetailOut)
def resolve_ticket(
    ticket_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> SupportTicketDetailOut:
    return service.resolve_ticket(db, ticket_id)
