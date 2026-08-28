import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.shared.enums import LeadStatus


class Lead(Base):
    """Sales pipeline lead — from web, showroom, test drive, or manual entry."""

    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status"), default=LeadStatus.new, nullable=False, index=True
    )
    interested_model: Mapped[str] = mapped_column(String(200), nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("vehicles.id"), nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True
    )
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["User | None"] = relationship(back_populates="leads", foreign_keys=[customer_id])
    assigned_agent: Mapped["User | None"] = relationship(
        back_populates="assigned_leads", foreign_keys=[assigned_agent_id]
    )
    vehicle: Mapped["Vehicle | None"] = relationship(back_populates="leads")
    activity: Mapped[list["LeadNote"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    status_events: Mapped[list["LeadStatusEvent"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class LeadNote(Base):
    """Activity log on a lead.

    This is an INTERNAL audit trail by default. Agents record candid things
    here — qualification judgements, pricing strategy, what to push. Every
    note written before customer lead tracking existed assumed staff-only
    readership, which is why `is_customer_visible` defaults to False: turning
    tracking on must not retroactively publish years of internal commentary.
    Staff opt a note in deliberately, one at a time.
    """

    __tablename__ = "lead_notes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("leads.id"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Opt-in. See the class docstring — the default is a privacy guarantee,
    #: not a UI preference.
    is_customer_visible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lead: Mapped["Lead"] = relationship(back_populates="activity")
    author: Mapped["User"] = relationship()


class LeadStatusEvent(Base):
    """One recorded pipeline transition.

    Added because the customer-facing tracker promises timestamp history and
    the schema could not supply it: status was overwritten in place, so a
    lead knew it was "qualified" but not when it stopped being "new". Leads
    predating this table have no rows — `tracking.build_timeline` synthesises
    their submission and outcome from `created_at` / `won_at` / `lost_at`.
    """

    __tablename__ = "lead_status_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("leads.id"), nullable=False, index=True)
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus, name="lead_status"), nullable=False)
    #: Nullable so a system-driven transition is not attributed to a person.
    actor_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lead: Mapped["Lead"] = relationship(back_populates="status_events")
