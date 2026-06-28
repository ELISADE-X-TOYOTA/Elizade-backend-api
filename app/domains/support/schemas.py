from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SlaConfigOut(BaseModel):
    id: str
    category: str
    responseHours: int
    resolutionHours: int
    isActive: bool

    @staticmethod
    def from_model(row) -> "SlaConfigOut":
        return SlaConfigOut(
            id=row.id,
            category=row.category.value,
            responseHours=row.response_hours,
            resolutionHours=row.resolution_hours,
            isActive=row.is_active,
        )


class TicketMessageOut(BaseModel):
    id: str
    senderType: str
    senderName: str | None = None
    body: str
    createdAt: str

    @staticmethod
    def from_model(row) -> "TicketMessageOut":
        sender_name = None
        if row.sender:
            sender_name = f"{row.sender.first_name} {row.sender.last_name}".strip()
        return TicketMessageOut(
            id=row.id,
            senderType=row.sender_type.value,
            senderName=sender_name,
            body=row.body,
            createdAt=row.created_at.isoformat(),
        )


class SupportTicketListItemOut(BaseModel):
    id: str
    ticketNumber: str
    subject: str
    category: str
    status: str
    priority: str
    slaStatus: str
    customerId: str
    customerName: str
    assignedToId: str | None = None
    assignedToName: str | None = None
    createdAt: str
    updatedAt: str

    @staticmethod
    def from_model(ticket) -> "SupportTicketListItemOut":
        customer_name = f"{ticket.customer.first_name} {ticket.customer.last_name}".strip()
        assigned_name = None
        if ticket.assigned_to:
            assigned_name = f"{ticket.assigned_to.first_name} {ticket.assigned_to.last_name}".strip()
        return SupportTicketListItemOut(
            id=ticket.id,
            ticketNumber=ticket.ticket_number,
            subject=ticket.subject,
            category=ticket.category.value,
            status=ticket.status.value,
            priority=ticket.priority.value,
            slaStatus=ticket.sla_status.value,
            customerId=ticket.user_id,
            customerName=customer_name,
            assignedToId=ticket.assigned_to_id,
            assignedToName=assigned_name,
            createdAt=ticket.created_at.isoformat(),
            updatedAt=ticket.updated_at.isoformat(),
        )


class SupportTicketDetailOut(SupportTicketListItemOut):
    firstResponseDue: str
    resolutionDue: str
    firstResponseAt: str | None = None
    resolvedAt: str | None = None
    messages: list[TicketMessageOut] = []

    @staticmethod
    def from_model(ticket) -> "SupportTicketDetailOut":
        base = SupportTicketListItemOut.from_model(ticket)
        return SupportTicketDetailOut(
            **base.model_dump(),
            firstResponseDue=ticket.first_response_due.isoformat(),
            resolutionDue=ticket.resolution_due.isoformat(),
            firstResponseAt=ticket.first_response_at.isoformat() if ticket.first_response_at else None,
            resolvedAt=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            messages=[TicketMessageOut.from_model(m) for m in ticket.messages],
        )


class PaginatedTicketsOut(BaseModel):
    items: list[SupportTicketListItemOut]
    total: int
    page: int
    size: int
    pages: int


class TicketUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str | None = None
    priority: str | None = None
    assigned_to_id: str | None = Field(default=None, alias="assignedToId")


class TicketMessageCreateIn(BaseModel):
    body: str = Field(min_length=1)


class TicketMessageCreateOut(BaseModel):
    ticket: SupportTicketDetailOut
    message: TicketMessageOut


class AssigneeOut(BaseModel):
    id: str
    name: str


class SupportSummaryOut(BaseModel):
    openTickets: int
    atRiskTickets: int
    unassignedTickets: int
    resolvedToday: int


class SlaConfigUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    response_hours: int | None = Field(default=None, alias="responseHours", ge=1, le=720)
    resolution_hours: int | None = Field(default=None, alias="resolutionHours", ge=1, le=720)
    is_active: bool | None = Field(default=None, alias="isActive")


class TicketCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    customer_id: str = Field(alias="customerId")
    category: str
    subject: str = Field(min_length=3, max_length=300)
    priority: str = Field(default="medium")
    body: str | None = Field(default=None, min_length=1)
