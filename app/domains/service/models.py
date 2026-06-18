import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import (
    AdditionalWorkStatus,
    AppointmentStatus,
    ServiceJobStatus,
    ServiceType,
)


class ServiceBay(Base):
    __tablename__ = "service_bays"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    branch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("branches.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    branch: Mapped["Branch"] = relationship(back_populates="service_bays")
    appointments: Mapped[list["ServiceAppointment"]] = relationship(back_populates="bay")
    jobs: Mapped[list["ServiceJob"]] = relationship(back_populates="bay")


class ServiceAppointment(Base):
    __tablename__ = "service_appointments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    owned_vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("branches.id"), nullable=False, index=True)
    bay_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("service_bays.id"), nullable=True)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType, name="service_type"), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"), default=AppointmentStatus.requested, nullable=False
    )
    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_completion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technician_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mileage_at_booking: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_technician_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["User"] = relationship(back_populates="service_appointments", foreign_keys=[user_id])
    owned_vehicle: Mapped["OwnedVehicle"] = relationship(back_populates="service_appointments")
    branch: Mapped["Branch"] = relationship(back_populates="service_appointments")
    bay: Mapped["ServiceBay | None"] = relationship(back_populates="appointments")
    job: Mapped["ServiceJob | None"] = relationship(back_populates="appointment", uselist=False)


class ServiceJob(Base):
    __tablename__ = "service_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    appointment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_appointments.id"), unique=True, nullable=False
    )
    bay_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("service_bays.id"), nullable=True)
    status: Mapped[ServiceJobStatus] = mapped_column(
        Enum(ServiceJobStatus, name="service_job_status"), default=ServiceJobStatus.pending, nullable=False
    )
    estimated_completion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    appointment: Mapped["ServiceAppointment"] = relationship(back_populates="job")
    bay: Mapped["ServiceBay | None"] = relationship(back_populates="jobs")
    stages: Mapped[list["ServiceJobStage"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="ServiceJobStage.sort_order"
    )
    additional_work: Mapped[list["AdditionalWorkRequest"]] = relationship(back_populates="job")
    invoice: Mapped["ServiceInvoice | None"] = relationship(back_populates="job", uselist=False)


class ServiceJobStage(Base):
    __tablename__ = "service_job_stages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("service_jobs.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    job: Mapped["ServiceJob"] = relationship(back_populates="stages")


class AdditionalWorkRequest(Base):
    __tablename__ = "additional_work_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("service_jobs.id"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[AdditionalWorkStatus] = mapped_column(
        Enum(AdditionalWorkStatus, name="additional_work_status"),
        default=AdditionalWorkStatus.pending_approval,
        nullable=False,
    )
    customer_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job: Mapped["ServiceJob"] = relationship(back_populates="additional_work")


class ServiceInvoice(Base):
    __tablename__ = "service_invoices"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_jobs.id"), unique=True, nullable=False
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job: Mapped["ServiceJob"] = relationship(back_populates="invoice")
    line_items: Mapped[list["ServiceInvoiceLineItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class ServiceInvoiceLineItem(Base):
    __tablename__ = "service_invoice_line_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_invoices.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    invoice: Mapped["ServiceInvoice"] = relationship(back_populates="line_items")


class ServiceHistoryItem(Base):
    """Completed service record for owned vehicle history."""

    __tablename__ = "service_history_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    owned_vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    appointment_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_appointments.id"), nullable=True
    )
    branch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("branches.id"), nullable=False)
    service_type: Mapped[str] = mapped_column(String(100), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owned_vehicle: Mapped["OwnedVehicle"] = relationship(back_populates="service_history")
    customer: Mapped["User"] = relationship(back_populates="service_history")
