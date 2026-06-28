from pydantic import BaseModel, ConfigDict, Field


class DashboardSummaryOut(BaseModel):
    vehiclesTotal: int
    vehiclesAvailable: int
    vehiclesReserved: int
    customersTotal: int
    customersNew30d: int
    staffTotal: int
    staffActive: int
    openSupportTickets: int
    slaAtRiskTickets: int
    pendingWarrantyClaims: int
    activeNotificationRules: int
    campaignsSent: int
    unreadNotificationsTotal: int
    leadsActive: int | None = None
    serviceToday: int | None = None
    serviceCapacity: int | None = None
