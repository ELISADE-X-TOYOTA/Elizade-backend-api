from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TestDriveCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vehicle_id: str = Field(alias="vehicleId")
    branch_id: str = Field(alias="branchId")
    scheduled_at: datetime = Field(alias="scheduledAt")
    notes: str | None = None


class TestDriveOut(BaseModel):
    id: str
    vehicleId: str
    vehicleLabel: str
    branchId: str
    branchName: str
    scheduledAt: str
    #: THE BOOKING's own status. Set to `requested` at creation and never
    #: changed by anything in this codebase — there is no admin endpoint for
    #: test drive bookings at all. Kept because clients read it, but it is not
    #: the field to show a customer.
    status: str
    notes: str | None = None
    leadId: str | None = None

    #: The LIVE pipeline stage, from the lead this booking created.
    #:
    #: THIS IS THE FIX FOR "status is stuck on Requested". Booking a test drive
    #: creates two rows: a TestDriveBooking and a Lead. Sales staff advance the
    #: LEAD through the pipeline; nothing ever touches the booking. The app was
    #: reading `status`, so it showed "Requested" forever no matter how far the
    #: enquiry had actually progressed.
    #:
    #: Mapped through `leads.tracking.to_stage`, the same function the customer
    #: lead screens use, so the two can never disagree about what a customer is
    #: told. Null only when a booking predates lead linking.
    leadStage: str | None = None
    leadStageLabel: str | None = None
    #: Position in the tracker, so a card can render progress without
    #: duplicating the mapping rules.
    leadStepIndex: int | None = None
    leadStepCount: int | None = None
    createdAt: str

    @staticmethod
    def from_model(booking) -> "TestDriveOut":
        vehicle = booking.vehicle
        branch = booking.branch
        vehicle_label = (
            f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim}".strip()
            if vehicle
            else "Vehicle"
        )
        # Imported here rather than at module scope: sales already imports
        # leads elsewhere and a top-level import closes the cycle.
        from app.domains.leads.tracking import STAGE_LABELS, STAGE_ORDER, step_index, to_stage

        lead = getattr(booking, "lead", None)
        stage = to_stage(lead.status) if lead is not None else None

        return TestDriveOut(
            id=booking.id,
            vehicleId=booking.vehicle_id,
            vehicleLabel=vehicle_label,
            branchId=booking.branch_id,
            branchName=branch.name if branch else "",
            scheduledAt=booking.scheduled_at.isoformat(),
            status=booking.status.value,
            notes=booking.notes,
            leadId=booking.lead_id,
            leadStage=stage.value if stage else None,
            leadStageLabel=STAGE_LABELS[stage] if stage else None,
            leadStepIndex=step_index(stage) if stage else None,
            leadStepCount=len(STAGE_ORDER) if stage else None,
            createdAt=booking.created_at.isoformat(),
        )


class QuotationRequestIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vehicle_id: str = Field(alias="vehicleId")
    notes: str | None = Field(default=None, max_length=2000)


class QuotationLineItemOut(BaseModel):
    description: str
    amount: str

    @staticmethod
    def from_model(row) -> "QuotationLineItemOut":
        return QuotationLineItemOut(description=row.description, amount=str(row.amount))


class QuotationOut(BaseModel):
    id: str
    vehicleId: str
    vehicleLabel: str
    status: str
    basePrice: str
    accessoriesTotal: str
    discount: str
    total: str
    validUntil: str
    lineItems: list[QuotationLineItemOut]
    createdAt: str

    @staticmethod
    def from_model(row) -> "QuotationOut":
        vehicle = row.vehicle
        label = f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim}".strip() if vehicle else "Vehicle"
        return QuotationOut(
            id=row.id,
            vehicleId=row.vehicle_id,
            vehicleLabel=label,
            status=row.status.value,
            basePrice=str(row.base_price),
            accessoriesTotal=str(row.accessories_total),
            discount=str(row.discount),
            total=str(row.total),
            validUntil=row.valid_until.isoformat(),
            lineItems=[QuotationLineItemOut.from_model(li) for li in row.line_items],
            createdAt=row.created_at.isoformat(),
        )


class ReservationCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vehicle_id: str = Field(alias="vehicleId")
    deposit_amount: Annotated[float | None, Field(alias="depositAmount", ge=0)] = None


class ReservationOut(BaseModel):
    id: str
    vehicleId: str
    vehicleLabel: str
    status: str
    depositAmount: str
    expiresAt: str
    confirmedAt: str | None = None
    createdAt: str

    @staticmethod
    def from_model(row) -> "ReservationOut":
        vehicle = row.vehicle
        label = f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim}".strip() if vehicle else "Vehicle"
        return ReservationOut(
            id=row.id,
            vehicleId=row.vehicle_id,
            vehicleLabel=label,
            status=row.status.value,
            depositAmount=str(row.deposit_amount),
            expiresAt=row.expires_at.isoformat(),
            confirmedAt=row.confirmed_at.isoformat() if row.confirmed_at else None,
            createdAt=row.created_at.isoformat(),
        )


class TradeInCreateIn(BaseModel):
    make: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1980, le=2100)
    mileage: int = Field(ge=0)
    condition_notes: str = Field(alias="conditionNotes", min_length=10, max_length=2000)
    photo_urls: Annotated[list[str], Field(alias="photoUrls", max_length=5)] = Field(default_factory=list)


class TradeInOut(BaseModel):
    id: str
    make: str
    model: str
    year: int
    mileage: int
    conditionNotes: str
    photoUrls: list[str] = Field(default_factory=list)
    status: str
    estimatedValue: str | None = None
    createdAt: str

    @staticmethod
    def from_model(row) -> "TradeInOut":
        return TradeInOut(
            id=row.id,
            make=row.make,
            model=row.model,
            year=row.year,
            mileage=row.mileage,
            conditionNotes=row.condition_notes,
            photoUrls=list(row.photo_urls or []),
            status=row.status.value,
            estimatedValue=str(row.estimated_value) if row.estimated_value is not None else None,
            createdAt=row.created_at.isoformat(),
        )
