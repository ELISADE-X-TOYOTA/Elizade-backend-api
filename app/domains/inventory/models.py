import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import AvailabilityStatus


class Vehicle(Base):
    """Inventory listing — vehicles available for sale."""

    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    vin: Mapped[str | None] = mapped_column(String(17), unique=True, nullable=True, index=True)
    stock_number: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    make: Mapped[str] = mapped_column(String(50), default="Toyota", nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    trim: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(100), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#000000", nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    promotional_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    is_promotional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promotion_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fuel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    transmission: Mapped[str] = mapped_column(String(50), nullable=False)
    engine: Mapped[str] = mapped_column(String(100), nullable=False)
    mileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    availability: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus, name="availability_status"),
        default=AvailabilityStatus.available,
        nullable=False,
        index=True,
    )
    branch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("branches.id"), nullable=False, index=True)
    specs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    branch: Mapped["Branch"] = relationship(back_populates="vehicles")
    images: Mapped[list["VehicleImage"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan", order_by="VehicleImage.sort_order"
    )
    test_drive_bookings: Mapped[list["TestDriveBooking"]] = relationship(back_populates="vehicle")
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="vehicle")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="vehicle")
    leads: Mapped[list["Lead"]] = relationship(back_populates="vehicle")


class VehicleImage(Base):
    __tablename__ = "vehicle_images"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    vehicle_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    vehicle: Mapped["Vehicle"] = relationship(back_populates="images")
