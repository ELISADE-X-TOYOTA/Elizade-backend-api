from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


def _normalize_vin(vin: str) -> str:
    return vin.strip().upper().replace(" ", "")


class VinLookupOut(BaseModel):
    found: bool
    vin: str
    canSubmit: bool
    reason: str | None = None
    vehiclePreview: "VehiclePreviewOut | None" = None


class VehiclePreviewOut(BaseModel):
    inventoryVehicleId: str | None = None
    make: str
    model: str
    trim: str
    year: int
    color: str
    availability: str | None = None


class OwnershipRequestCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vin: str = Field(min_length=11, max_length=17)
    registration_number: Annotated[str | None, Field(alias="registrationNumber", max_length=50)] = None
    customer_notes: Annotated[str | None, Field(alias="customerNotes", max_length=2000)] = None
    document_urls: list[str] = Field(default_factory=list, alias="documentUrls")


class OwnershipRequestOut(BaseModel):
    id: str
    vin: str
    registrationNumber: str | None = None
    status: str
    documentUrls: list[str]
    customerNotes: str | None = None
    adminNotes: str | None = None
    vehiclePreview: VehiclePreviewOut | None = None
    ownedVehicleId: str | None = None
    createdAt: str
    updatedAt: str

    @staticmethod
    def from_model(row, *, preview: VehiclePreviewOut | None = None) -> "OwnershipRequestOut":
        return OwnershipRequestOut(
            id=row.id,
            vin=row.vin,
            registrationNumber=row.registration_number,
            status=row.status.value,
            documentUrls=list(row.document_urls or []),
            customerNotes=row.customer_notes,
            adminNotes=row.admin_notes,
            vehiclePreview=preview,
            ownedVehicleId=row.owned_vehicle_id,
            createdAt=row.created_at.isoformat(),
            updatedAt=row.updated_at.isoformat(),
        )


class OwnershipRequestListItemOut(OwnershipRequestOut):
    customerId: str
    customerName: str
    customerEmail: str | None = None

    @staticmethod
    def from_model(row, *, preview: VehiclePreviewOut | None = None) -> "OwnershipRequestListItemOut":
        base = OwnershipRequestOut.from_model(row, preview=preview)
        customer_name = f"{row.customer.first_name} {row.customer.last_name}".strip()
        return OwnershipRequestListItemOut(
            **base.model_dump(),
            customerId=row.user_id,
            customerName=customer_name,
            customerEmail=row.customer.email,
        )


class PaginatedOwnershipRequestsOut(BaseModel):
    items: list[OwnershipRequestListItemOut]
    total: int
    page: int
    size: int
    pages: int


class OwnershipRequestUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str | None = None
    admin_notes: Annotated[str | None, Field(alias="adminNotes")] = None
    registration_number: Annotated[str | None, Field(alias="registrationNumber")] = None


class OwnedVehicleOut(BaseModel):
    id: str
    vin: str
    make: str
    model: str
    trim: str
    year: int
    color: str
    registrationNumber: str
    mileage: int
    purchaseDate: str | None = None
    isPrimary: bool
    imageUrl: str | None = None

    @staticmethod
    def from_model(row) -> "OwnedVehicleOut":
        return OwnedVehicleOut(
            id=row.id,
            vin=row.vin,
            make=row.make,
            model=row.model,
            trim=row.trim,
            year=row.year,
            color=row.color,
            registrationNumber=row.registration_number,
            mileage=row.mileage,
            purchaseDate=row.purchase_date.isoformat() if row.purchase_date else None,
            isPrimary=row.is_primary,
            imageUrl=row.image_url,
        )


class DocumentUploadOut(BaseModel):
    url: str


class DocumentsAppendIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_urls: list[str] = Field(default_factory=list, alias="documentUrls")
