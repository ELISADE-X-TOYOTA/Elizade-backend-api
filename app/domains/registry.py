"""
Import all ORM models so SQLAlchemy registers tables on Base.metadata before create_all().
"""

from app.domains.audit.models import AuditLog
from app.domains.branches.models import Branch
from app.domains.customers.models import (
    CustomerDuplicateReview,
    CustomerNote,
    OwnedVehicle,
    WatchlistItem,
)
from app.domains.inventory.models import (
    Vehicle,
    VehicleAvailabilitySubscription,
    VehicleImage,
)
from app.domains.leads.models import Lead, LeadNote, LeadStatusEvent
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.ownership.models import VehicleOwnershipRequest
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
    ServiceBoardSettings,
    ServiceBoardVehicleModel,
    ServiceHistoryItem,
    ServiceHistoryLine,
    ServiceInterval,
    ServiceInvoice,
    ServiceInvoiceLineItem,
    ServiceItem,
    ServiceJob,
    ServiceJobStage,
    ServicePriceBookEntry,
    ServicePriceBookVersion,
)
from app.domains.support.models import SlaConfig, SupportTicket, TicketMessage
from app.domains.users.models import OtpChallenge, RefreshToken, User
from app.domains.warranty.models import RecallCampaign, RecallVehicle, WarrantyCertificate, WarrantyClaim

__all__ = [
    "AuditLog",
    "Branch",
    "BroadcastCampaign",
    "CustomerNote",
    "CustomerDuplicateReview",
    "Lead",
    "LeadNote",
    "LeadStatusEvent",
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
    "ServiceBoardSettings",
    "ServiceBoardVehicleModel",
    "ServiceHistoryItem",
    "ServiceHistoryLine",
    "ServiceInterval",
    "ServiceItem",
    "ServicePriceBookEntry",
    "ServicePriceBookVersion",
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
    "VehicleOwnershipRequest",
    "Vehicle",
    "VehicleAvailabilitySubscription",
    "VehicleImage",
    "WarrantyCertificate",
    "WarrantyClaim",
    "WatchlistItem",
]
