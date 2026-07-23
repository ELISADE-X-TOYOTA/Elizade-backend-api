from pydantic import BaseModel


class OwnedVehicleSnapshotOut(BaseModel):
    id: str
    label: str
    registrationNumber: str
    mileage: int
    nextServiceDue: str | None = None
    nextServiceMileage: int | None = None


class UpcomingAppointmentOut(BaseModel):
    id: str
    vehicleLabel: str
    serviceType: str
    scheduledAt: str
    status: str
    branchName: str


class CustomerDashboardSummaryOut(BaseModel):
    ownedVehiclesCount: int
    primaryVehicle: OwnedVehicleSnapshotOut | None = None
    upcomingAppointments: int
    nextAppointment: UpcomingAppointmentOut | None = None
    pendingAdditionalWork: int
    openSupportTickets: int
    unreadNotifications: int
    activeWarrantyCertificates: int
    pendingWarrantyClaims: int
    activeRecalls: int
    watchlistCount: int
    pendingOwnershipRequests: int
    pendingReservations: int
    pendingQuotations: int
    pendingTradeIns: int
    upcomingTestDrives: int
