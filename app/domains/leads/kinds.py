"""What KIND of enquiry a lead is — a test drive, a quote, a reservation.

THE LIST COULD NOT SAY. Every lead is created with `source="Mobile app"` and
a free-text note, so "My Leads" showed five rows that differed only by
vehicle: a customer who had booked a test drive, asked for a quote and
reserved a car saw three identical-looking entries. The detail screen managed
a "Test Drive" chip only because the screen that opened it passed the kind
along in the route — which means it was right when opened from Bookings and
blank when opened from anywhere else.

RESOLVED FROM THE LINK, NOT THE NOTE. Each channel already records
`lead_id` on the row it creates, so the kind is a fact about what exists in
the database rather than a string somebody might reword. Parsing
`notes` was the alternative and it is one copy-edit away from breaking
silently.

A lead can in principle be referenced by more than one channel; the order in
`_RESOLVERS` decides which wins, and it is the order of commitment — a
reservation says more about the customer's intent than the quote that
preceded it.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.sales.models import Quotation, Reservation, TestDriveBooking, TradeInRequest


class LeadKind(str, Enum):
    """The customer-facing label for how an enquiry began."""

    test_drive = "test_drive"
    quotation = "quotation"
    reservation = "reservation"
    trade_in = "trade_in"
    #: Linked to nothing we can name — a walk-in, or a channel added later
    #: that forgot to set lead_id. Shown as a neutral "Enquiry".
    enquiry = "enquiry"


#: Most committed first — see the module docstring.
_RESOLVERS: tuple[tuple[LeadKind, type], ...] = (
    (LeadKind.reservation, Reservation),
    (LeadKind.trade_in, TradeInRequest),
    (LeadKind.test_drive, TestDriveBooking),
    (LeadKind.quotation, Quotation),
)

KIND_LABELS: dict[LeadKind, str] = {
    LeadKind.test_drive: "Test Drive",
    LeadKind.quotation: "Quote",
    LeadKind.reservation: "Reservation",
    LeadKind.trade_in: "Trade-In",
    LeadKind.enquiry: "Enquiry",
}


def resolve_kinds(db: Session, lead_ids: list[str]) -> dict[str, LeadKind]:
    """Map each lead id to its kind, in four queries rather than four per lead.

    Batched deliberately: the obvious implementation asks each table about
    one lead at a time, which turns a ten-row list into forty round trips on
    a managed database with a twenty-five connection cap.
    """
    if not lead_ids:
        return {}

    found: dict[str, LeadKind] = {}
    # Least committed first, so a more committed kind overwrites it.
    for kind, model in reversed(_RESOLVERS):
        rows = db.execute(
            select(model.lead_id).where(model.lead_id.in_(lead_ids))
        ).scalars().all()
        for lead_id in rows:
            if lead_id:
                found[lead_id] = kind

    return {lead_id: found.get(lead_id, LeadKind.enquiry) for lead_id in lead_ids}
