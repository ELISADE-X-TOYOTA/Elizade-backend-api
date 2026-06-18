import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import (
    QuotationStatus,
    ReservationStatus,
    TestDriveStatus,
    TradeInStatus,
)


class TestDriveBooking(Base):
    __tablename__ = "test_drive_bookings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    vehicle_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=False, index=True)
    branch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("branches.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("leads.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[TestDriveStatus] = mapped_column(
        Enum(TestDriveStatus, name="test_drive_status"), default=TestDriveStatus.requested, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="test_drive_bookings")
    vehicle: Mapped["Vehicle"] = relationship(back_populates="test_drive_bookings")
    branch: Mapped["Branch"] = relationship(back_populates="test_drive_bookings")


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    vehicle_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("leads.id"), nullable=True)
    prepared_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    accessories_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotation_status"), default=QuotationStatus.draft, nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="quotations", foreign_keys=[user_id])
    vehicle: Mapped["Vehicle"] = relationship(back_populates="quotations")
    line_items: Mapped[list["QuotationLineItem"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan"
    )


class QuotationLineItem(Base):
    __tablename__ = "quotation_line_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    quotation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("quotations.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    quotation: Mapped["Quotation"] = relationship(back_populates="line_items")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    vehicle_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("leads.id"), nullable=True)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status"), default=ReservationStatus.pending, nullable=False
    )
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="reservations")
    vehicle: Mapped["Vehicle"] = relationship(back_populates="reservations")


class TradeInRequest(Base):
    __tablename__ = "trade_in_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("leads.id"), nullable=True)
    make: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_notes: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TradeInStatus] = mapped_column(
        Enum(TradeInStatus, name="trade_in_status"), default=TradeInStatus.submitted, nullable=False
    )
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    valued_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="trade_in_requests", foreign_keys=[user_id])
