"""
Import all ORM models so SQLAlchemy registers tables on Base.metadata before create_all().
"""

from app.domains.audit.models import AuditLog
from app.domains.branches.models import Branch
from app.domains.customers.models import CustomerNote, OwnedVehicle, WatchlistItem
from app.domains.inventory.models import Vehicle, VehicleImage
from app.domains.leads.models import Lead, LeadNote
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.sales.models import (
    Quotation,
    QuotationLineItem,
    Reservation,
    TestDriveBooking,
    TradeInRequest,
)
from app.domains.service.models import (
    AdditionalWorkRequest,
    ServiceAppointment,
    ServiceBay,
    ServiceHistoryItem,
    ServiceInvoice,
    ServiceInvoiceLineItem,
    ServiceJob,
    ServiceJobStage,
)
from app.domains.support.models import SlaConfig, SupportTicket, TicketMessage
from app.domains.users.models import OtpChallenge, User
from app.domains.warranty.models import RecallCampaign, RecallVehicle, WarrantyCertificate, WarrantyClaim

__all__ = [
    "AuditLog",
    "Branch",
    "BroadcastCampaign",
    "CustomerNote",
    "Lead",
    "LeadNote",
    "NotificationRule",
    "OtpChallenge",
    "OwnedVehicle",
    "Quotation",
    "QuotationLineItem",
    "RecallCampaign",
    "RecallVehicle",
    "Reservation",
    "ServiceAppointment",
    "ServiceBay",
    "ServiceHistoryItem",
    "ServiceInvoice",
    "ServiceInvoiceLineItem",
    "ServiceJob",
    "ServiceJobStage",
    "AdditionalWorkRequest",
    "SlaConfig",
    "SupportTicket",
    "TestDriveBooking",
    "TicketMessage",
    "TradeInRequest",
    "User",
    "UserNotification",
    "Vehicle",
    "VehicleImage",
    "WarrantyCertificate",
    "WarrantyClaim",
    "WatchlistItem",
]
