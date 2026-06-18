import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import BranchType


class Branch(Base):
    """Showroom and service centre locations."""

    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[BranchType] = mapped_column(Enum(BranchType, name="branch_type"), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="branch")
    service_bays: Mapped[list["ServiceBay"]] = relationship(back_populates="branch")
    service_appointments: Mapped[list["ServiceAppointment"]] = relationship(back_populates="branch")
    test_drive_bookings: Mapped[list["TestDriveBooking"]] = relationship(back_populates="branch")
