from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Nested brief schemas (embedded in list / detail responses)
# ---------------------------------------------------------------------------


class AgentBrief(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class CustomerBrief(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str | None = None
    phone: str

    model_config = {"from_attributes": True, "populate_by_name": True}


class VehicleBrief(BaseModel):
    id: str
    make: str
    model: str
    trim: str
    year: int
    color: str
    price: Decimal

    model_config = {"from_attributes": True, "populate_by_name": True}


class LeadNoteOut(BaseModel):
    id: str
    leadId: str
    authorId: str
    authorName: str
    body: str
    createdAt: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


# ---------------------------------------------------------------------------
# List / detail output schemas
# ---------------------------------------------------------------------------


class LeadListItemOut(BaseModel):
    id: str
    customerName: str
    email: str | None = None
    phone: str
    source: str
    status: str
    interestedModel: str
    value: Decimal
    assignedAgent: AgentBrief | None = None
    customer: CustomerBrief | None = None
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class LeadDetailOut(BaseModel):
    id: str
    customerName: str
    email: str | None = None
    phone: str
    source: str
    status: str
    interestedModel: str
    value: Decimal
    notes: str | None = None
    wonAt: datetime | None = None
    lostAt: datetime | None = None
    lostReason: str | None = None
    assignedAgent: AgentBrief | None = None
    customer: CustomerBrief | None = None
    vehicle: VehicleBrief | None = None
    activity: list[LeadNoteOut] = []
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class PaginatedLeadsOut(BaseModel):
    items: list[LeadListItemOut]
    total: int
    page: int
    size: int
    pages: int


# ---------------------------------------------------------------------------
# Pipeline KPI schema
# ---------------------------------------------------------------------------


class StatusCountOut(BaseModel):
    status: str
    count: int
    value: Decimal


class LeadPipelineOut(BaseModel):
    totalLeads: int
    totalValue: Decimal
    conversionRate: float  # won / (won + lost) * 100, rounded to 2 dp
    newThisWeek: int
    byStatus: list[StatusCountOut]


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class LeadCreateIn(BaseModel):
    """Create a lead manually (showroom walk-in, phone inquiry, etc.)."""

    model_config = {"populate_by_name": True}

    customerName: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    phone: str = Field(min_length=7, max_length=30)
    source: str = Field(min_length=1, max_length=100)
    interestedModel: str = Field(min_length=1, max_length=200)
    value: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=5000)
    # Optional links
    customerId: str | None = Field(default=None)
    vehicleId: str | None = Field(default=None)
    assignedAgentId: str | None = Field(default=None)

    @field_validator("email")
    @classmethod
    def _strip_email(cls, v: str | None) -> str | None:
        return v.strip().lower() if v and v.strip() else None

    @field_validator("phone", "source", "interestedModel", "customerName")
    @classmethod
    def _strip_str(cls, v: str) -> str:
        return v.strip()


class LeadUpdateIn(BaseModel):
    """Partial update of editable lead fields."""

    model_config = {"populate_by_name": True}

    customerName: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    source: str | None = Field(default=None, min_length=1, max_length=100)
    interestedModel: str | None = Field(default=None, min_length=1, max_length=200)
    value: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=5000)
    customerId: str | None = Field(default=None)
    vehicleId: str | None = Field(default=None)


class LeadStatusUpdateIn(BaseModel):
    """Move the lead to a new pipeline stage (not won/lost — use dedicated endpoints)."""

    status: str = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=5000, description="Optional internal note on this transition")


class LeadAssignIn(BaseModel):
    """Assign or reassign the lead to a staff / admin agent."""

    assignedAgentId: str = Field(min_length=1, description="UUID of the staff/admin user to assign")


class LeadWonIn(BaseModel):
    """Mark lead as won."""

    vehicleId: str | None = Field(default=None, description="Optionally link the sold vehicle")
    notes: str | None = Field(default=None, max_length=5000)


class LeadLostIn(BaseModel):
    """Mark lead as lost — loss reason is mandatory."""

    lostReason: str = Field(min_length=1, max_length=500, description="Required reason for losing this lead")
    notes: str | None = Field(default=None, max_length=5000)


class LeadNoteCreateIn(BaseModel):
    """Add an activity note (call summary, follow-up record, etc.)."""

    body: str = Field(min_length=1, max_length=5000)
