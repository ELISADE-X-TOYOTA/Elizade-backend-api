from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


def _full_name(user) -> str:
    return f"{user.first_name} {user.last_name}".strip() if user else ""


def _vehicle_label(vehicle) -> str:
    return f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else ""


# --------------------------------------------------------------------------- #
# Stats                                                                       #
# --------------------------------------------------------------------------- #

class ServiceStatsOut(BaseModel):
    """KPI tiles for the daily Service Operations board (today-scoped)."""

    todaysAppointments: int
    inProgress: int
    awaitingApproval: int
    completed: int


# --------------------------------------------------------------------------- #
# Bays                                                                        #
# --------------------------------------------------------------------------- #

class ServiceBayOut(BaseModel):
    id: str
    branchId: str
    branchName: str
    name: str
    isActive: bool
    createdAt: str

    @staticmethod
    def from_model(bay) -> "ServiceBayOut":
        return ServiceBayOut(
            id=bay.id,
            branchId=bay.branch_id,
            branchName=bay.branch.name if bay.branch else "",
            name=bay.name,
            isActive=bay.is_active,
            createdAt=bay.created_at.isoformat(),
        )


class ServiceBayCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    branch_id: str = Field(alias="branchId")
    name: str = Field(min_length=1, max_length=100)


class ServiceBayUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = Field(default=None, alias="isActive")


# --------------------------------------------------------------------------- #
# Appointments                                                                #
# --------------------------------------------------------------------------- #

class AppointmentJobSummaryOut(BaseModel):
    id: str
    status: str
    estimatedCompletion: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None

    @staticmethod
    def from_model(job) -> "AppointmentJobSummaryOut":
        return AppointmentJobSummaryOut(
            id=job.id,
            status=job.status.value,
            estimatedCompletion=job.estimated_completion.isoformat() if job.estimated_completion else None,
            startedAt=job.started_at.isoformat() if job.started_at else None,
            completedAt=job.completed_at.isoformat() if job.completed_at else None,
        )


class AppointmentBoardItemOut(BaseModel):
    """Row on the daily schedule board."""

    id: str
    customerId: str
    customerName: str
    vehicleId: str
    vehicleLabel: str
    registrationNumber: str
    serviceType: str
    scheduledAt: str
    status: str
    branchId: str
    branchName: str
    bayId: str | None = None
    bayName: str | None = None
    technicianId: str | None = None
    technicianName: str | None = None
    jobId: str | None = None
    jobStatus: str | None = None

    @staticmethod
    def from_model(appt) -> "AppointmentBoardItemOut":
        vehicle = appt.owned_vehicle
        tech = appt.assigned_technician
        return AppointmentBoardItemOut(
            id=appt.id,
            customerId=appt.user_id,
            customerName=_full_name(appt.customer),
            vehicleId=appt.owned_vehicle_id,
            vehicleLabel=_vehicle_label(vehicle),
            registrationNumber=vehicle.registration_number if vehicle else "",
            serviceType=appt.service_type.value,
            scheduledAt=appt.scheduled_at.isoformat(),
            status=appt.status.value,
            branchId=appt.branch_id,
            branchName=appt.branch.name if appt.branch else "",
            bayId=appt.bay_id,
            bayName=appt.bay.name if appt.bay else None,
            technicianId=appt.assigned_technician_id,
            technicianName=_full_name(tech) if tech else None,
            jobId=appt.job.id if appt.job else None,
            jobStatus=appt.job.status.value if appt.job else None,
        )


class AppointmentDetailOut(AppointmentBoardItemOut):
    issueDescription: str
    technicianNotes: str | None = None
    estimatedCompletion: str | None = None
    mileageAtBooking: int
    createdAt: str
    updatedAt: str
    job: AppointmentJobSummaryOut | None = None

    @staticmethod
    def from_model(appt) -> "AppointmentDetailOut":
        base = AppointmentBoardItemOut.from_model(appt)
        return AppointmentDetailOut(
            **base.model_dump(),
            issueDescription=appt.issue_description,
            technicianNotes=appt.technician_notes,
            estimatedCompletion=appt.estimated_completion.isoformat() if appt.estimated_completion else None,
            mileageAtBooking=appt.mileage_at_booking,
            createdAt=appt.created_at.isoformat(),
            updatedAt=appt.updated_at.isoformat(),
            job=AppointmentJobSummaryOut.from_model(appt.job) if appt.job else None,
        )


class AppointmentUpdateIn(BaseModel):
    """Update slot / bay / technician / ETA. Status changes go via the status endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    scheduled_at: datetime | None = Field(default=None, alias="scheduledAt")
    bay_id: str | None = Field(default=None, alias="bayId")
    assigned_technician_id: str | None = Field(default=None, alias="technicianId")
    estimated_completion: datetime | None = Field(default=None, alias="estimatedCompletion")


class AppointmentStatusActionIn(BaseModel):
    action: str  # confirm | start | complete | cancel


# --------------------------------------------------------------------------- #
# Jobs                                                                        #
# --------------------------------------------------------------------------- #

class JobStageOut(BaseModel):
    id: str
    label: str
    completed: bool
    completedAt: str | None = None
    sortOrder: int

    @staticmethod
    def from_model(stage) -> "JobStageOut":
        return JobStageOut(
            id=stage.id,
            label=stage.label,
            completed=stage.completed,
            completedAt=stage.completed_at.isoformat() if stage.completed_at else None,
            sortOrder=stage.sort_order,
        )


class AdditionalWorkOut(BaseModel):
    id: str
    description: str
    cost: Decimal
    status: str
    customerRespondedAt: str | None = None
    createdAt: str

    @staticmethod
    def from_model(work) -> "AdditionalWorkOut":
        return AdditionalWorkOut(
            id=work.id,
            description=work.description,
            cost=work.cost,
            status=work.status.value,
            customerRespondedAt=work.customer_responded_at.isoformat() if work.customer_responded_at else None,
            createdAt=work.created_at.isoformat(),
        )


class InvoiceLineItemOut(BaseModel):
    id: str
    description: str
    amount: Decimal
    sortOrder: int

    @staticmethod
    def from_model(item) -> "InvoiceLineItemOut":
        return InvoiceLineItemOut(
            id=item.id,
            description=item.description,
            amount=item.amount,
            sortOrder=item.sort_order,
        )


class JobInvoiceOut(BaseModel):
    id: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    issuedAt: str
    lineItems: list[InvoiceLineItemOut]

    @staticmethod
    def from_model(invoice) -> "JobInvoiceOut":
        return JobInvoiceOut(
            id=invoice.id,
            subtotal=invoice.subtotal,
            tax=invoice.tax,
            total=invoice.total,
            issuedAt=invoice.issued_at.isoformat(),
            lineItems=[InvoiceLineItemOut.from_model(li) for li in sorted(invoice.line_items, key=lambda x: x.sort_order)],
        )


class JobDetailOut(BaseModel):
    id: str
    appointmentId: str
    status: str
    serviceType: str
    customerName: str
    vehicleLabel: str
    bayId: str | None = None
    bayName: str | None = None
    estimatedCompletion: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    stagesTotal: int
    stagesCompleted: int
    stages: list[JobStageOut]
    additionalWork: list[AdditionalWorkOut]
    invoice: JobInvoiceOut | None = None
    createdAt: str
    updatedAt: str

    @staticmethod
    def from_model(job) -> "JobDetailOut":
        appt = job.appointment
        customer = appt.customer if appt else None
        vehicle = appt.owned_vehicle if appt else None
        stages = sorted(job.stages, key=lambda s: s.sort_order)
        work = sorted(job.additional_work, key=lambda w: w.created_at)
        return JobDetailOut(
            id=job.id,
            appointmentId=job.appointment_id,
            status=job.status.value,
            serviceType=appt.service_type.value if appt else "",
            customerName=_full_name(customer),
            vehicleLabel=_vehicle_label(vehicle),
            bayId=job.bay_id,
            bayName=job.bay.name if job.bay else None,
            estimatedCompletion=job.estimated_completion.isoformat() if job.estimated_completion else None,
            startedAt=job.started_at.isoformat() if job.started_at else None,
            completedAt=job.completed_at.isoformat() if job.completed_at else None,
            stagesTotal=len(stages),
            stagesCompleted=sum(1 for s in stages if s.completed),
            stages=[JobStageOut.from_model(s) for s in stages],
            additionalWork=[AdditionalWorkOut.from_model(w) for w in work],
            invoice=JobInvoiceOut.from_model(job.invoice) if job.invoice else None,
            createdAt=job.created_at.isoformat(),
            updatedAt=job.updated_at.isoformat(),
        )


class StageUpdateIn(BaseModel):
    completed: bool = True


class AdditionalWorkCreateIn(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    cost: Decimal = Field(gt=0)


class AdditionalWorkStatusUpdateIn(BaseModel):
    status: str  # pending_approval | approved | rejected


# --------------------------------------------------------------------------- #
# Service history                                                             #
# --------------------------------------------------------------------------- #

class ServiceHistoryItemOut(BaseModel):
    id: str
    ownedVehicleId: str
    customerId: str
    customerName: str
    vehicleLabel: str
    registrationNumber: str
    branchId: str
    branchName: str
    appointmentId: str | None = None
    serviceType: str
    performedAt: str
    mileage: int
    description: str
    cost: Decimal
    createdAt: str

    @staticmethod
    def from_model(item) -> "ServiceHistoryItemOut":
        vehicle = item.owned_vehicle
        customer = item.customer
        branch = item.branch
        return ServiceHistoryItemOut(
            id=item.id,
            ownedVehicleId=item.owned_vehicle_id,
            customerId=item.user_id,
            customerName=_full_name(customer),
            vehicleLabel=_vehicle_label(vehicle),
            registrationNumber=vehicle.registration_number if vehicle else "",
            branchId=item.branch_id,
            branchName=branch.name if branch else "",
            appointmentId=item.appointment_id,
            serviceType=item.service_type,
            performedAt=item.performed_at.isoformat(),
            mileage=item.mileage,
            description=item.description,
            cost=item.cost,
            createdAt=item.created_at.isoformat(),
        )


class PaginatedHistoryOut(BaseModel):
    items: list[ServiceHistoryItemOut]
    total: int
    page: int
    size: int
    pages: int


class ServiceHistoryCreateIn(BaseModel):
    """Manual history entry for a walk-in serviced without an online booking."""

    model_config = ConfigDict(populate_by_name=True)

    owned_vehicle_id: str = Field(alias="ownedVehicleId")
    branch_id: str = Field(alias="branchId")
    service_type: str = Field(alias="serviceType", min_length=1, max_length=100)
    performed_at: datetime = Field(alias="performedAt")
    mileage: int = Field(ge=0)
    description: str = Field(min_length=1)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
