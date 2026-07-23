import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import OwnershipRequestStatus


class VehicleOwnershipRequest(Base):
    """Customer request to link a purchased vehicle to their account."""

    __tablename__ = "vehicle_ownership_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    vin: Mapped[str] = mapped_column(String(17), nullable=False, index=True)
    registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    inventory_vehicle_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=True
    )
    status: Mapped[OwnershipRequestStatus] = mapped_column(
        Enum(OwnershipRequestStatus, name="ownership_request_status"),
        default=OwnershipRequestStatus.pending,
        nullable=False,
        index=True,
    )
    document_urls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owned_vehicle_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["User"] = relationship(foreign_keys=[user_id])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    inventory_vehicle: Mapped["Vehicle | None"] = relationship()
    owned_vehicle: Mapped["OwnedVehicle | None"] = relationship()
