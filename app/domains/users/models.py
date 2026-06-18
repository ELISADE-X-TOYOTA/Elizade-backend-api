import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    customer = "customer"
    staff = "staff"
    admin = "admin"


class OtpPurpose(str, enum.Enum):
    login = "login"
    register = "register"


DEFAULT_PREFERENCES = {
    "push_enabled": True,
    "sms_enabled": True,
    "email_enabled": True,
    "marketing_opt_in": False,
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_normalized: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    phone_display: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), default="Lagos", nullable=False)
    state: Mapped[str] = mapped_column(String(100), default="Lagos", nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.customer, nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=DEFAULT_PREFERENCES, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    otp_challenges: Mapped[list["OtpChallenge"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    # Customer profile
    owned_vehicles: Mapped[list["OwnedVehicle"]] = relationship(back_populates="owner")
    watchlist_items: Mapped[list["WatchlistItem"]] = relationship(back_populates="user")
    crm_notes: Mapped[list["CustomerNote"]] = relationship(
        back_populates="customer", foreign_keys="CustomerNote.customer_id"
    )

    # Sales
    leads: Mapped[list["Lead"]] = relationship(back_populates="customer", foreign_keys="Lead.customer_id")
    assigned_leads: Mapped[list["Lead"]] = relationship(
        back_populates="assigned_agent", foreign_keys="Lead.assigned_agent_id"
    )
    test_drive_bookings: Mapped[list["TestDriveBooking"]] = relationship(back_populates="user")
    quotations: Mapped[list["Quotation"]] = relationship(
        back_populates="user", foreign_keys="Quotation.user_id"
    )
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="user")
    trade_in_requests: Mapped[list["TradeInRequest"]] = relationship(
        back_populates="user", foreign_keys="TradeInRequest.user_id"
    )

    # Service
    service_appointments: Mapped[list["ServiceAppointment"]] = relationship(
        back_populates="customer", foreign_keys="ServiceAppointment.user_id"
    )
    service_history: Mapped[list["ServiceHistoryItem"]] = relationship(back_populates="customer")

    # Warranty
    warranty_certificates: Mapped[list["WarrantyCertificate"]] = relationship(
        back_populates="customer", foreign_keys="WarrantyCertificate.user_id"
    )
    warranty_claims: Mapped[list["WarrantyClaim"]] = relationship(
        back_populates="customer", foreign_keys="WarrantyClaim.user_id"
    )
    recall_notifications: Mapped[list["RecallVehicle"]] = relationship(back_populates="customer")

    # Support
    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="customer", foreign_keys="SupportTicket.user_id"
    )
    assigned_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="assigned_to", foreign_keys="SupportTicket.assigned_to_id"
    )

    # Notifications
    notifications: Mapped[list["UserNotification"]] = relationship(back_populates="user")


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_normalized: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[OtpPurpose] = mapped_column(Enum(OtpPurpose, name="otp_purpose"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="otp_challenges")
