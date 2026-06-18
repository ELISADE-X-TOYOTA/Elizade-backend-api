import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OwnedVehicle(Base):
    """Customer-owned vehicle — linked after purchase or manual registration."""

    __tablename__ = "owned_vehicles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    inventory_vehicle_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=True
    )
    vin: Mapped[str] = mapped_column(String(17), nullable=False, index=True)
    make: Mapped[str] = mapped_column(String(50), default="Toyota", nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    trim: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(100), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#000000", nullable=False)
    mileage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    registration_number: Mapped[str] = mapped_column(String(50), nullable=False)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_service_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_service_mileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="owned_vehicles")
    service_appointments: Mapped[list["ServiceAppointment"]] = relationship(back_populates="owned_vehicle")
    service_history: Mapped[list["ServiceHistoryItem"]] = relationship(back_populates="owned_vehicle")
    warranty_certificates: Mapped[list["WarrantyCertificate"]] = relationship(back_populates="owned_vehicle")
    warranty_claims: Mapped[list["WarrantyClaim"]] = relationship(back_populates="owned_vehicle")
    recall_notifications: Mapped[list["RecallVehicle"]] = relationship(back_populates="owned_vehicle")


class CustomerNote(Base):
    """Internal CRM notes — visible to staff only."""

    __tablename__ = "customer_notes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["User"] = relationship(back_populates="crm_notes", foreign_keys=[customer_id])
    author: Mapped["User"] = relationship(foreign_keys=[author_id])


class WatchlistItem(Base):
    """Customer vehicle watchlist preferences."""

    __tablename__ = "watchlist_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    trim: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="watchlist_items")
