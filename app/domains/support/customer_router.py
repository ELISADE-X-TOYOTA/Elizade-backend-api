from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.support import service
from app.domains.support.schemas import TicketMessageOut
from app.domains.support.customer_schemas import (
    AttachmentUploadOut,
    CustomerTicketCreateIn,
    CustomerTicketDetailOut,
    CustomerTicketListOut,
    CustomerTicketMessageCreateOut,
    CustomerTicketMessageIn,
    CustomerTicketRateIn,
)

router = APIRouter(prefix="/support", tags=["customer-support"])


@router.get("/tickets", response_model=list[CustomerTicketListOut])
def list_my_tickets(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[CustomerTicketListOut]:
    return service.list_customer_tickets(db, current_user.id)


@router.post("/tickets", response_model=CustomerTicketDetailOut, status_code=201)
def create_ticket(
    payload: CustomerTicketCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerTicketDetailOut:
    return service.create_customer_ticket(db, current_user, payload)


@router.get("/tickets/{ticket_id}", response_model=CustomerTicketDetailOut)
def get_ticket(
    ticket_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerTicketDetailOut:
    return service.get_customer_ticket(db, current_user.id, ticket_id)


@router.post("/tickets/{ticket_id}/messages", response_model=CustomerTicketMessageCreateOut)
def reply_to_ticket(
    ticket_id: str,
    payload: CustomerTicketMessageIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerTicketMessageCreateOut:
    return service.add_customer_message(
        db, current_user.id, ticket_id, payload.body, payload.attachments
    )


@router.get("/tickets/{ticket_id}/messages", response_model=list[TicketMessageOut])
def list_ticket_messages(
    ticket_id: str,
    current_user: CustomerUser,
    since: datetime | None = Query(
        default=None,
        description="ISO-8601. Returns only messages created strictly after this instant.",
    ),
    db: Session = Depends(get_db),
) -> list[TicketMessageOut]:
    """Messages on a ticket, for catching up after a dropped connection.

    The realtime socket is best-effort; this is the guarantee. A client that
    reconnects asks for everything after the last message it holds, so nothing
    sent during the outage is lost.
    """
    return service.list_customer_messages_since(db, current_user.id, ticket_id, since)


@router.post("/attachments/upload", response_model=AttachmentUploadOut)
def upload_attachment(
    current_user: CustomerUser,
    file: UploadFile = File(...),
) -> AttachmentUploadOut:
    """Store a file and return its URL, for use in a reply's `attachments`.

    Two-step (upload, then send the URL with the message) mirrors
    `/ownership/documents/upload`, and lets a client attach several files to
    one reply without a multipart body per message.
    """
    return service.upload_attachment(file)


@router.post("/tickets/{ticket_id}/rate", response_model=CustomerTicketDetailOut)
def rate_ticket(
    ticket_id: str,
    payload: CustomerTicketRateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerTicketDetailOut:
    return service.rate_customer_ticket(db, current_user.id, ticket_id, payload.rating)
