from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class VehicleImageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    url: str
    altText: str | None = None
    sortOrder: int
    isPrimary: bool


class VehicleListItemOut(BaseModel):
    """Catalogue card — the lightweight shape returned by list endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    make: str
    model: str
    trim: str
    year: int
    color: str
    colorHex: str
    price: Decimal
    promotionalPrice: Decimal | None = None
    isPromotional: bool
    promotionLabel: str | None = None
    fuelType: str
    transmission: str
    availability: str
    branchId: str
    primaryImageUrl: str | None = None
    createdAt: str


class VehicleListOut(BaseModel):
    items: list[VehicleListItemOut]
    page: int
    limit: int
    total: int
    totalPages: int


class VehicleDetailOut(BaseModel):
    """Full vehicle detail for the detail page and side-by-side compare."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    make: str
    model: str
    trim: str
    year: int
    color: str
    colorHex: str
    price: Decimal
    promotionalPrice: Decimal | None = None
    isPromotional: bool
    promotionLabel: str | None = None
    fuelType: str
    transmission: str
    engine: str
    mileage: int | None = None
    availability: str
    branchId: str
    branchName: str
    branchCity: str
    branchState: str
    specs: dict
    images: list[VehicleImageOut]
    createdAt: str
    updatedAt: str | None = None


# --------------------------------------------------------------------------- #
# Admin (staff portal) schemas                                                #
# --------------------------------------------------------------------------- #

class VehicleAdminListItemOut(BaseModel):
    """Row in the admin inventory grid — all statuses, includes internal fields."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    vin: str | None = None
    stockNumber: str | None = None
    make: str
    model: str
    trim: str
    year: int
    color: str
    price: Decimal
    promotionalPrice: Decimal | None = None
    isPromotional: bool
    availability: str
    branchId: str
    branchName: str
    isPublished: bool
    primaryImageUrl: str | None = None
    createdAt: str
    updatedAt: str | None = None


class VehicleAdminListOut(BaseModel):
    items: list[VehicleAdminListItemOut]
    page: int
    limit: int
    total: int
    totalPages: int


class VehicleAdminDetailOut(BaseModel):
    """Full admin view for edit-form prefill."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    vin: str | None = None
    stockNumber: str | None = None
    make: str
    model: str
    trim: str
    year: int
    color: str
    colorHex: str
    price: Decimal
    promotionalPrice: Decimal | None = None
    isPromotional: bool
    promotionLabel: str | None = None
    fuelType: str
    transmission: str
    engine: str
    mileage: int | None = None
    availability: str
    branchId: str
    branchName: str
    branchCity: str
    branchState: str
    specs: dict
    images: list[VehicleImageOut]
    isPublished: bool
    publishedAt: str | None = None
    createdById: str | None = None
    createdAt: str
    updatedAt: str | None = None
    deletedAt: str | None = None


class VehicleCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vin: str | None = Field(default=None, max_length=17)
    stock_number: str | None = Field(default=None, alias="stockNumber", max_length=50)
    make: str = Field(default="Toyota", min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    trim: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1900, le=2100)
    color: str = Field(min_length=1, max_length=100)
    color_hex: str = Field(default="#000000", alias="colorHex", max_length=7)
    price: Decimal = Field(gt=0)
    promotional_price: Decimal | None = Field(default=None, alias="promotionalPrice", gt=0)
    is_promotional: bool = Field(default=False, alias="isPromotional")
    promotion_label: str | None = Field(default=None, alias="promotionLabel", max_length=200)
    fuel_type: str = Field(alias="fuelType", min_length=1, max_length=50)
    transmission: str = Field(min_length=1, max_length=50)
    engine: str = Field(min_length=1, max_length=100)
    mileage: int | None = Field(default=None, ge=0)
    availability: str = "available"
    branch_id: str = Field(alias="branchId")
    specs: dict = Field(default_factory=dict)
    is_published: bool = Field(default=True, alias="isPublished")
    published_at: datetime | None = Field(default=None, alias="publishedAt")


class VehicleUpdateIn(BaseModel):
    """Partial update. Availability is NOT here — it is changed via the status endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    vin: str | None = Field(default=None, max_length=17)
    stock_number: str | None = Field(default=None, alias="stockNumber", max_length=50)
    make: str | None = Field(default=None, min_length=1, max_length=50)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    trim: str | None = Field(default=None, min_length=1, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)
    color: str | None = Field(default=None, min_length=1, max_length=100)
    color_hex: str | None = Field(default=None, alias="colorHex", max_length=7)
    price: Decimal | None = Field(default=None, gt=0)
    promotional_price: Decimal | None = Field(default=None, alias="promotionalPrice", gt=0)
    is_promotional: bool | None = Field(default=None, alias="isPromotional")
    promotion_label: str | None = Field(default=None, alias="promotionLabel", max_length=200)
    fuel_type: str | None = Field(default=None, alias="fuelType", min_length=1, max_length=50)
    transmission: str | None = Field(default=None, min_length=1, max_length=50)
    engine: str | None = Field(default=None, min_length=1, max_length=100)
    mileage: int | None = Field(default=None, ge=0)
    branch_id: str | None = Field(default=None, alias="branchId")
    specs: dict | None = None
    is_published: bool | None = Field(default=None, alias="isPublished")
    published_at: datetime | None = Field(default=None, alias="publishedAt")


class VehicleStatusUpdateIn(BaseModel):
    availability: str


class BulkImportRowErrorOut(BaseModel):
    row: int  # 1-based row number in the file (header is row 1)
    errors: list[str]


class BulkImportResultOut(BaseModel):
    total: int  # data rows processed (excludes the header row)
    created: int
    failed: int
    createdIds: list[str]
    errors: list[BulkImportRowErrorOut]
