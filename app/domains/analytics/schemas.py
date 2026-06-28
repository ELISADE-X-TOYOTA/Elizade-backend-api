from pydantic import BaseModel


class InventoryModelStatOut(BaseModel):
    model: str
    available: int
    reserved: int
    sold: int
    total: int


class NamedCountOut(BaseModel):
    name: str
    count: int


class AnalyticsOverviewOut(BaseModel):
    inventoryByModel: list[InventoryModelStatOut]
    inventoryAvailable: int
    inventoryReserved: int
    inventorySold: int
    customersTotal: int
    customersNew30d: int
    customersWithVehicle: int
    openSupportTickets: int
    slaAtRiskTickets: int
    supportByCategory: list[NamedCountOut]
    pendingWarrantyClaims: int
    warrantyClaimsByStatus: list[NamedCountOut]
    activeCertificates: int
    activeRecalls: int
    campaignsSent: int
    activeNotificationRules: int
    unreadNotificationsTotal: int
    serviceToday: int | None = None
    serviceCapacity: int | None = None
    leadsActive: int | None = None
