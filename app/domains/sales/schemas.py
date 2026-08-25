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
    status: str
    notes: str | None = None
    leadId: str | None = None
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
    photo_urls: list[str] = Field(default_factory=list, alias="photoUrls", max_length=5)


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
