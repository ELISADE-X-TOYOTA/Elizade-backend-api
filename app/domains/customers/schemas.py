from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class OwnedVehicleBrief(BaseModel):
    id: str
    vin: str
    make: str
    model: str
    year: int
    registration_number: str = Field(alias="registrationNumber")
    purchase_date: datetime | None = Field(default=None, alias="purchaseDate")

    model_config = {"from_attributes": True, "populate_by_name": True}


class CustomerNoteBrief(BaseModel):
    id: str
    body: str
    created_at: datetime = Field(alias="createdAt")
    author_name: str = Field(alias="authorName")

    model_config = {"from_attributes": True, "populate_by_name": True}


class LeadBrief(BaseModel):
    id: str
    interested_model: str = Field(alias="interestedModel")
    status: str
    value: Decimal
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class ServiceAppointmentBrief(BaseModel):
    id: str
    service_type: str = Field(alias="serviceType")
    scheduled_at: datetime = Field(alias="scheduledAt")
    status: str
    issue_description: str = Field(alias="issueDescription")

    model_config = {"from_attributes": True, "populate_by_name": True}


class SupportTicketBrief(BaseModel):
    id: str
    ticket_number: str = Field(alias="ticketNumber")
    subject: str
    status: str
    priority: str
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class CustomerDetailOut(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str | None
    phone: str
    city: str
    state: str
    avatar: str | None
    isActive: bool
    isVerified: bool
    createdAt: datetime
    updatedAt: datetime
    ownedVehicles: list[OwnedVehicleBrief] = []
    crmNotes: list[CustomerNoteBrief] = []
    leads: list[LeadBrief] = []
    serviceAppointments: list[ServiceAppointmentBrief] = []
    supportTickets: list[SupportTicketBrief] = []

    @staticmethod
    def from_user(user) -> "CustomerDetailOut":
        # Safe extraction of notes with author names
        notes_brief = []
        for note in getattr(user, "crm_notes", []):
            author_name = "System"
            if note.author:
                author_name = f"{note.author.first_name} {note.author.last_name}".strip()
            notes_brief.append(
                CustomerNoteBrief(
                    id=note.id,
                    body=note.body,
                    createdAt=note.created_at,
                    authorName=author_name,
                )
            )

        vehicles_brief = [
            OwnedVehicleBrief.model_validate(v) for v in getattr(user, "owned_vehicles", [])
        ]
        leads_brief = [
            LeadBrief(
                id=l.id,
                interestedModel=l.interested_model,
                status=l.status.value if hasattr(l.status, "value") else str(l.status),
                value=l.value,
                createdAt=l.created_at,
            )
            for l in getattr(user, "leads", [])
        ]
        appointments_brief = [
            ServiceAppointmentBrief(
                id=a.id,
                serviceType=a.service_type.value if hasattr(a.service_type, "value") else str(a.service_type),
                scheduledAt=a.scheduled_at,
                status=a.status.value if hasattr(a.status, "value") else str(a.status),
                issueDescription=a.issue_description,
            )
            for a in getattr(user, "service_appointments", [])
        ]
        tickets_brief = [
            SupportTicketBrief(
                id=t.id,
                ticketNumber=t.ticket_number,
                subject=t.subject,
                status=t.status.value if hasattr(t.status, "value") else str(t.status),
                priority=t.priority.value if hasattr(t.priority, "value") else str(t.priority),
                createdAt=t.created_at,
            )
            for t in getattr(user, "support_tickets", [])
        ]

        return CustomerDetailOut(
            id=user.id,
            firstName=user.first_name,
            lastName=user.last_name,
            email=user.email,
            phone=user.phone_display,
            city=user.city,
            state=user.state,
            avatar=user.avatar_url,
            isActive=user.is_active,
            isVerified=user.is_verified,
            createdAt=user.created_at,
            updatedAt=user.updated_at,
            ownedVehicles=vehicles_brief,
            crmNotes=notes_brief,
            leads=leads_brief,
            serviceAppointments=appointments_brief,
            supportTickets=tickets_brief,
        )


class PaginatedCustomersOut(BaseModel):
    items: list[CustomerDetailOut]
    total: int
    page: int
    size: int
    pages: int


class CustomerContact(BaseModel):
    id: str
    firstName: str = Field(alias="firstName")
    lastName: str = Field(alias="lastName")
    email: str | None
    phone: str
    city: str
    state: str
    avatar: str | None
    isActive: bool = Field(alias="isActive")
    isVerified: bool = Field(alias="isVerified")
    createdAt: datetime = Field(alias="createdAt")
    updatedAt: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class CustomerPreferences(BaseModel):
    pushEnabled: bool = Field(alias="pushEnabled")
    smsEnabled: bool = Field(alias="smsEnabled")
    emailEnabled: bool = Field(alias="emailEnabled")
    marketingOptIn: bool = Field(alias="marketingOptIn")

    model_config = {"populate_by_name": True}


class CustomerActivityItem(BaseModel):
    id: str
    type: str  # e.g., "note", "lead", "appointment", "ticket", "test_drive", "quotation", "reservation", "trade_in", "warranty_claim", "vehicle"
    title: str
    description: str
    status: str | None = None
    timestamp: datetime

    model_config = {"populate_by_name": True}


class CustomerProfileOut(BaseModel):
    contact: CustomerContact
    preferences: CustomerPreferences
    activity: list[CustomerActivityItem] = []


class ServiceHistoryItemOut(BaseModel):
    id: str
    serviceType: str
    performedAt: datetime
    mileage: int
    description: str
    cost: float
    appointmentId: str | None = None

    model_config = {"populate_by_name": True}


class CustomerVehicleOut(BaseModel):
    id: str
    vin: str
    make: str
    model: str
    trim: str
    year: int
    color: str
    colorHex: str
    mileage: int
    registrationNumber: str
    purchaseDate: datetime | None = None
    imageUrl: str | None = None
    isPrimary: bool
    nextServiceDue: datetime | None = None
    nextServiceMileage: int | None = None
    createdAt: datetime
    serviceHistory: list[ServiceHistoryItemOut] = []

    model_config = {"populate_by_name": True}


class CustomerVehiclesOut(BaseModel):
    customerId: str
    vehicles: list[CustomerVehicleOut]
    totalVehicles: int


class CustomerTimelineOut(BaseModel):
    customerId: str
    timeline: list[CustomerActivityItem]
    totalItems: int

    model_config = {"populate_by_name": True}


class CustomerNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CustomerNoteOut(BaseModel):
    id: str
    customerId: str = Field(alias="customerId")
    authorId: str = Field(alias="authorId")
    authorName: str = Field(alias="authorName")
    body: str
    createdAt: datetime = Field(alias="createdAt")
    updatedAt: datetime = Field(alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class CustomerSegmentsOut(BaseModel):
    total: int = 0
    active: int = 0
    inactive: int = 0
    verified: int = 0
    unverified: int = 0
    hasVehicle: int = 0
    noVehicle: int = 0
    new: int = 0
    premium: int = 0
    atRisk: int = 0
