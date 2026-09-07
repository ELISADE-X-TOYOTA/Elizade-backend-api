from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BoardVehicleModelOut(BaseModel):
    id: str
    name: str
    sortOrder: int
    isActive: bool

    @staticmethod
    def from_model(row) -> "BoardVehicleModelOut":
        return BoardVehicleModelOut(
            id=row.id,
            name=row.name,
            sortOrder=row.sort_order,
            isActive=row.is_active,
        )


class PriceBookEntryOut(BaseModel):
    id: str
    serviceItemId: str
    serviceItemCode: str
    serviceItemName: str
    serviceItemGroup: str
    vehicleModelId: str
    vehicleModel: str
    mileageBandKm: int
    price: Decimal

    @staticmethod
    def from_model(row) -> "PriceBookEntryOut":
        item = row.service_item
        model = row.vehicle_model
        return PriceBookEntryOut(
            id=row.id,
            serviceItemId=row.service_item_id,
            serviceItemCode=item.code if item else "",
            serviceItemName=item.name if item else "",
            serviceItemGroup=item.group.value if item else "",
            vehicleModelId=row.vehicle_model_id,
            vehicleModel=model.name if model else "",
            mileageBandKm=row.mileage_band_km,
            price=row.price,
        )


class PriceBookVersionOut(BaseModel):
    id: str
    versionNumber: int
    status: str
    currency: str
    priceInclusive: bool
    effectiveFrom: str | None = None
    disclaimer: str | None = None
    publishedAt: str | None = None
    entryCount: int = 0

    @staticmethod
    def from_model(version, *, entry_count: int = 0) -> "PriceBookVersionOut":
        return PriceBookVersionOut(
            id=version.id,
            versionNumber=version.version_number,
            status=version.status.value,
            currency=version.currency,
            priceInclusive=version.price_inclusive,
            effectiveFrom=version.effective_from.isoformat() if version.effective_from else None,
            disclaimer=version.disclaimer,
            publishedAt=version.published_at.isoformat() if version.published_at else None,
            entryCount=entry_count,
        )


class PriceBookDetailOut(PriceBookVersionOut):
    entries: list[PriceBookEntryOut] = Field(default_factory=list)


class PriceBookBoardOut(BaseModel):
    """Read-only published matrix for staff display."""

    version: PriceBookVersionOut
    mileageBandsKm: list[int]
    vehicleModels: list[str]
    entries: list[PriceBookEntryOut]


class PriceImportRowPreviewOut(BaseModel):
    row: int
    vehicleModel: str
    serviceItemCode: str
    mileageBandKm: int
    price: Decimal
    action: str  # create | update


class PriceImportRowErrorOut(BaseModel):
    row: int
    errors: list[str]


class PriceImportPreviewOut(BaseModel):
    total: int
    valid: int
    failed: int
    duplicateCellsInFile: int
    rows: list[PriceImportRowPreviewOut]
    errors: list[PriceImportRowErrorOut]
    replacesPublishedVersion: bool
    currentPublishedVersion: int | None = None


class PriceImportPublishOut(BaseModel):
    versionId: str
    versionNumber: int
    publishedAt: str
    entryCount: int
    archivedPreviousVersionId: str | None = None


class PricePublishIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    effective_from: datetime | None = Field(default=None, alias="effectiveFrom")
    disclaimer: str | None = Field(default=None, max_length=2000)
