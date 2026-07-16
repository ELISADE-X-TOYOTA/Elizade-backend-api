from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DashboardSummaryOut(BaseModel):
    vehiclesTotal: int
    vehiclesAvailable: int
    vehiclesReserved: int
    vehiclesSold: int
    customersTotal: int
    customersNew30d: int
    customersWithVehicle: int
    staffTotal: int
    staffActive: int
    branchesTotal: int
    branchesActive: int
    openSupportTickets: int
    slaAtRiskTickets: int
    pendingWarrantyClaims: int
    activeNotificationRules: int
    campaignsSent: int
    unreadNotificationsTotal: int
    leadsActive: int
    leadsPipelineValue: float
    leadsNewThisWeek: int
    leadsConversionRate: float
    serviceToday: int
    serviceInProgress: int
    serviceAwaitingApproval: int
    serviceCapacity: int
    serviceCompletedToday: int


class PipelineStageOut(BaseModel):
    stage: str
    status: str
    count: int
    value: float


class LeadSourceOut(BaseModel):
    source: str
    count: int


class HotLeadOut(BaseModel):
    id: str
    customerName: str
    interestedModel: str
    status: str
    value: float
    assignedAgent: str | None = None


class ServiceSlotOut(BaseModel):
    id: str
    time: str
    customerName: str
    vehicleLabel: str
    branchName: str
    bayName: str | None = None
    status: str


class SlaTicketOut(BaseModel):
    id: str
    ticketNumber: str
    subject: str
    assignedTo: str | None = None


class InventoryModelRowOut(BaseModel):
    model: str
    sold: int
    available: int


class ServiceTypeRowOut(BaseModel):
    type: str
    count: int


class BranchRowOut(BaseModel):
    id: str
    name: str
    vehicles: int
    appointmentsToday: int
    activeLeads: int


class WeeklyLoadOut(BaseModel):
    day: str
    booked: int
    completed: int


class MonthlyCountOut(BaseModel):
    month: str
    customers: int


class RevenueMonthOut(BaseModel):
    month: str
    sales: float
    service: float


class ActivityItemOut(BaseModel):
    id: str
    text: str
    meta: str
    time: datetime
    color: str


class StaffPerformanceOut(BaseModel):
    id: str
    name: str
    department: str
    leadsWon: int
    ticketsOpen: int


class DashboardOverviewOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: DashboardSummaryOut
    leadPipeline: list[PipelineStageOut]
    leadSources: list[LeadSourceOut]
    hotLeads: list[HotLeadOut]
    todayService: list[ServiceSlotOut]
    slaTickets: list[SlaTicketOut]
    inventoryByModel: list[InventoryModelRowOut]
    serviceByType: list[ServiceTypeRowOut]
    branchStats: list[BranchRowOut]
    weeklyServiceLoad: list[WeeklyLoadOut]
    customerSignupsByMonth: list[MonthlyCountOut]
    revenueByMonth: list[RevenueMonthOut]
    recentActivity: list[ActivityItemOut]
    staffPerformance: list[StaffPerformanceOut]
