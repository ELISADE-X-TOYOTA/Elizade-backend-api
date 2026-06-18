import enum


class BranchType(str, enum.Enum):
    showroom = "showroom"
    service_centre = "service_centre"
    both = "both"


class AvailabilityStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"
    sold = "sold"
    transferred = "transferred"


class ServiceType(str, enum.Enum):
    periodic = "periodic"
    repair = "repair"
    inspection = "inspection"
    recall = "recall"


class AppointmentStatus(str, enum.Enum):
    requested = "requested"
    confirmed = "confirmed"
    in_progress = "in_progress"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    cancelled = "cancelled"


class ServiceJobStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    cancelled = "cancelled"


class AdditionalWorkStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class TicketCategory(str, enum.Enum):
    sales = "sales"
    service = "service"
    warranty = "warranty"
    billing = "billing"
    general = "general"


class TicketStatus(str, enum.Enum):
    open = "open"
    assigned = "assigned"
    in_progress = "in_progress"
    waiting_customer = "waiting_customer"
    resolved = "resolved"
    closed = "closed"


class TicketPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class MessageSender(str, enum.Enum):
    customer = "customer"
    staff = "staff"
    system = "system"


class ClaimStatus(str, enum.Enum):
    submitted = "submitted"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    escalated = "escalated"
    closed = "closed"


class WarrantyCertificateType(str, enum.Enum):
    standard = "standard"
    extended = "extended"


class WarrantyCertificateStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    voided = "voided"


class RecallSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    proposal = "proposal"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class TestDriveStatus(str, enum.Enum):
    requested = "requested"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"


class QuotationStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    expired = "expired"
    rejected = "rejected"


class ReservationStatus(str, enum.Enum):
    pending = "pending"
    deposit_paid = "deposit_paid"
    confirmed = "confirmed"
    expired = "expired"
    cancelled = "cancelled"


class TradeInStatus(str, enum.Enum):
    submitted = "submitted"
    under_review = "under_review"
    valued = "valued"
    accepted = "accepted"
    rejected = "rejected"


class NotificationCategory(str, enum.Enum):
    service = "service"
    sales = "sales"
    warranty = "warranty"
    support = "support"
    promo = "promo"
    system = "system"


class BroadcastCampaignStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    sending = "sending"
    sent = "sent"
    cancelled = "cancelled"


class SlaStatus(str, enum.Enum):
    ok = "ok"
    at_risk = "at_risk"
    breached = "breached"


class AuditAction(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"
    status_change = "status_change"
    assign = "assign"
    login = "login"

