from pydantic import BaseModel, ConfigDict, Field

from app.domains.support.schemas import SupportTicketDetailOut, SupportTicketListItemOut, TicketMessageOut


class CustomerTicketCreateIn(BaseModel):
    category: str
    subject: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=1)
    priority: str = Field(default="medium")
    #: Media URLs from `POST /support/attachments/upload`, attached to the
    #: opening message. Same cap and validation as a reply.
    attachments: list[str] = Field(default_factory=list, max_length=5)


#: A reply may carry a handful of photos or a PDF, not an album. The cap is
#: enforced at the schema so an oversized payload is rejected before it reaches
#: the ticket lookup.
MAX_ATTACHMENTS_PER_MESSAGE = 5


class CustomerTicketMessageIn(BaseModel):
    #: Empty body is allowed when attachments are present — "here's the photo"
    #: is a complete reply. Validated in the service, which can see both fields.
    body: str = Field(default="", max_length=5000)
    #: Media URLs previously returned by `POST /support/attachments/upload`.
    attachments: list[str] = Field(default_factory=list, max_length=MAX_ATTACHMENTS_PER_MESSAGE)


class AttachmentUploadOut(BaseModel):
    url: str


class CustomerTicketRateIn(BaseModel):
    rating: int = Field(ge=1, le=5)


class CustomerTicketListOut(SupportTicketListItemOut):
    satisfactionRating: int | None = None

    @staticmethod
    def from_model(ticket) -> "CustomerTicketListOut":
        base = SupportTicketListItemOut.from_model(ticket)
        return CustomerTicketListOut(
            **base.model_dump(),
            satisfactionRating=ticket.satisfaction_rating,
        )


class CustomerTicketDetailOut(SupportTicketDetailOut):
    satisfactionRating: int | None = None

    @staticmethod
    def from_model(ticket) -> "CustomerTicketDetailOut":
        base = SupportTicketDetailOut.from_model(ticket)
        return CustomerTicketDetailOut(
            **base.model_dump(),
            satisfactionRating=ticket.satisfaction_rating,
        )


class CustomerTicketMessageCreateOut(BaseModel):
    ticket: CustomerTicketDetailOut
    message: TicketMessageOut
