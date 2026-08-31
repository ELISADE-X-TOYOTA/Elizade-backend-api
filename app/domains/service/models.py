import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import (
    AdditionalWorkStatus,
    AppointmentStatus,
    ServiceHistoryLineSource,
    ServiceItemGroup,
    ServiceJobStatus,
    ServiceOperation,
    ServicePriceBookStatus,
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
    attachment_urls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
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
    assigned_technician: Mapped["User | None"] = relationship(foreign_keys=[assigned_technician_id])
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
    branch: Mapped["Branch"] = relationship(foreign_keys=[branch_id])
    lines: Mapped[list["ServiceHistoryLine"]] = relationship(
        back_populates="history_item",
        cascade="all, delete-orphan",
        order_by="ServiceHistoryLine.created_at",
    )


class ServiceItem(Base):
    """Canonical service-item catalogue. Prices and intervals are added later."""

    __tablename__ = "service_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    group: Mapped[ServiceItemGroup] = mapped_column(
        Enum(ServiceItemGroup, name="service_item_group"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines: Mapped[list["ServiceHistoryLine"]] = relationship(back_populates="service_item")


class ServiceHistoryLine(Base):
    """One catalogue item covered on a completed visit.

    Date and odometer live on the parent `service_history_items` row. Do not
    duplicate them here — a line is not a separate event.
    """

    __tablename__ = "service_history_lines"
    __table_args__ = (
        UniqueConstraint("history_item_id", "service_item_id", name="uq_service_history_line_item"),
        CheckConstraint("quantity IS NULL OR quantity >= 1", name="ck_service_history_line_quantity"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_service_history_line_amount"),
        CheckConstraint(
            "backfill_confidence IS NULL OR (backfill_confidence >= 0 AND backfill_confidence <= 100)",
            name="ck_service_history_line_confidence",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    history_item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_history_items.id"), nullable=False, index=True
    )
    service_item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_items.id"), nullable=False, index=True
    )
    operation: Mapped[ServiceOperation] = mapped_column(
        Enum(ServiceOperation, name="service_operation"), nullable=False
    )
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[ServiceHistoryLineSource] = mapped_column(
        Enum(ServiceHistoryLineSource, name="service_history_line_source"),
        default=ServiceHistoryLineSource.manual_entry,
        nullable=False,
    )
    is_backfilled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backfill_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    history_item: Mapped["ServiceHistoryItem"] = relationship(back_populates="lines")
    service_item: Mapped["ServiceItem"] = relationship(back_populates="lines")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])


# --------------------------------------------------------------------------- #
# Service Board price book (Phase 2)                                          #
# --------------------------------------------------------------------------- #

class ServiceBoardVehicleModel(Base):
    """Supported vehicle model names on the physical / digital price board."""

    __tablename__ = "service_board_vehicle_models"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ServicePriceBookVersion(Base):
    """Versioned price matrix. Only one `published` row should be current."""

    __tablename__ = "service_price_book_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[ServicePriceBookStatus] = mapped_column(
        Enum(ServicePriceBookStatus, name="service_price_book_status"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    price_inclusive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disclaimer: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entries: Mapped[list["ServicePriceBookEntry"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    published_by: Mapped["User | None"] = relationship(foreign_keys=[published_by_id])
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])


class ServicePriceBookEntry(Base):
    """One price cell: item × vehicle model × optional mileage band within a version."""

    __tablename__ = "service_price_book_entries"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "service_item_id",
            "vehicle_model_id",
            "mileage_band_km",
            name="uq_service_price_book_entry_cell",
        ),
        CheckConstraint("price >= 0", name="ck_service_price_book_entry_price"),
        CheckConstraint("mileage_band_km >= 0", name="ck_service_price_book_entry_mileage"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_price_book_versions.id"), nullable=False, index=True
    )
    service_item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_items.id"), nullable=False, index=True
    )
    vehicle_model_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("service_board_vehicle_models.id"), nullable=False, index=True
    )
    #: 0 = not mileage-banded (chassis / engine flat cells). Periodic rows use approved band values.
    mileage_band_km: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    version: Mapped["ServicePriceBookVersion"] = relationship(back_populates="entries")
    service_item: Mapped["ServiceItem"] = relationship()
    vehicle_model: Mapped["ServiceBoardVehicleModel"] = relationship()
