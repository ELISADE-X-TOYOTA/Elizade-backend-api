from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BoardSettingsOut(BaseModel):
    dueSoonKm: int
    dueSoonDays: int
    mileageStaleDays: int
    updatedAt: str

    @staticmethod
    def from_model(row) -> "BoardSettingsOut":
        return BoardSettingsOut(
            dueSoonKm=row.due_soon_km,
            dueSoonDays=row.due_soon_days,
            mileageStaleDays=row.mileage_stale_days,
            updatedAt=row.updated_at.isoformat(),
        )


class BoardSettingsUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    due_soon_km: int | None = Field(default=None, alias="dueSoonKm", ge=0)
    due_soon_days: int | None = Field(default=None, alias="dueSoonDays", ge=0)
    mileage_stale_days: int | None = Field(default=None, alias="mileageStaleDays", ge=1)


class ServiceIntervalOut(BaseModel):
    id: str
    serviceItemId: str
    serviceItemCode: str
    serviceItemName: str
    vehicleModelId: str | None = None
    vehicleModel: str | None = None
    kind: str
    intervalKm: int | None = None
    intervalMonths: int | None = None
    isActive: bool

    @staticmethod
    def from_model(row) -> "ServiceIntervalOut":
        item = row.service_item
        model = row.vehicle_model
        return ServiceIntervalOut(
            id=row.id,
            serviceItemId=row.service_item_id,
            serviceItemCode=item.code if item else "",
            serviceItemName=item.name if item else "",
            vehicleModelId=row.vehicle_model_id,
            vehicleModel=model.name if model else None,
            kind=row.kind.value,
            intervalKm=row.interval_km,
            intervalMonths=row.interval_months,
            isActive=row.is_active,
        )


class ServiceIntervalCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    service_item_id: str = Field(alias="serviceItemId")
    vehicle_model_id: str | None = Field(default=None, alias="vehicleModelId")
    kind: str
    interval_km: int | None = Field(default=None, alias="intervalKm", gt=0)
    interval_months: int | None = Field(default=None, alias="intervalMonths", gt=0)


class ServiceIntervalUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str | None = None
    interval_km: int | None = Field(default=None, alias="intervalKm", gt=0)
    interval_months: int | None = Field(default=None, alias="intervalMonths", gt=0)
    is_active: bool | None = Field(default=None, alias="isActive")


class ItemMaintenanceStatusOut(BaseModel):
    serviceItemId: str
    serviceItemCode: str
    serviceItemName: str
    serviceItemGroup: str
    status: str
    reason: str
    dueAtKm: int | None = None
    dueAt: str | None = None
    mileageStale: bool = False
    lastPerformedAt: str | None = None
    lastMileage: int | None = None
    lastOperation: str | None = None


class VehicleMaintenanceOut(BaseModel):
    ownedVehicleId: str
    customerId: str
    customerName: str
    customerPhone: str
    customerEmail: str
    vehicleLabel: str
    model: str
    currentMileage: int
    items: list[ItemMaintenanceStatusOut]


class MaintenanceVehicleSummaryOut(BaseModel):
    ownedVehicleId: str
    customerId: str
    customerName: str
    customerPhone: str
    customerEmail: str
    vehicleLabel: str
    model: str
    currentMileage: int
    worstStatus: str
    dueSoonCount: int
    overdueCount: int
    notOnRecordCount: int
    topReason: str | None = None


class PaginatedMaintenanceSummaryOut(BaseModel):
    items: list[MaintenanceVehicleSummaryOut]
    total: int
    page: int
    size: int
    pages: int
