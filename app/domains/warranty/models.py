import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import (
    ClaimStatus,
    RecallSeverity,
    WarrantyCertificateStatus,
    WarrantyCertificateType,
)


class WarrantyCertificate(Base):
    __tablename__ = "warranty_certificates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    owned_vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    certificate_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type: Mapped[WarrantyCertificateType] = mapped_column(
        Enum(WarrantyCertificateType, name="warranty_certificate_type"), nullable=False
    )
    coverage_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    coverage_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[WarrantyCertificateStatus] = mapped_column(
        Enum(WarrantyCertificateStatus, name="warranty_certificate_status"),
        default=WarrantyCertificateStatus.active,
        nullable=False,
    )
    coverage_details: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    issued_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owned_vehicle: Mapped["OwnedVehicle"] = relationship(back_populates="warranty_certificates")
    customer: Mapped["User"] = relationship(back_populates="warranty_certificates", foreign_keys=[user_id])


class WarrantyClaim(Base):
    __tablename__ = "warranty_claims"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    owned_vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=False, index=True
    )
    certificate_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("warranty_certificates.id"), nullable=True
    )
    claim_type: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claim_status"), default=ClaimStatus.submitted, nullable=False, index=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["User"] = relationship(back_populates="warranty_claims", foreign_keys=[user_id])
    owned_vehicle: Mapped["OwnedVehicle"] = relationship(back_populates="warranty_claims")
    certificate: Mapped["WarrantyCertificate | None"] = relationship()
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])


class RecallCampaign(Base):
    __tablename__ = "recall_campaigns"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[RecallSeverity] = mapped_column(Enum(RecallSeverity, name="recall_severity"), nullable=False)
    affected_models: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    affected_year_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affected_year_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    affected_vehicles: Mapped[list["RecallVehicle"]] = relationship(
        back_populates="recall", cascade="all, delete-orphan"
    )


class RecallVehicle(Base):
    """Links recall campaigns to owned vehicles and tracks notification status."""

    __tablename__ = "recall_vehicles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    recall_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("recall_campaigns.id"), nullable=False, index=True
    )
    owned_vehicle_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("owned_vehicles.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recall: Mapped["RecallCampaign"] = relationship(back_populates="affected_vehicles")
    owned_vehicle: Mapped["OwnedVehicle"] = relationship(back_populates="recall_notifications")
    customer: Mapped["User"] = relationship(back_populates="recall_notifications")
