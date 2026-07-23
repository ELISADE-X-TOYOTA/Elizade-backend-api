from pydantic import BaseModel, ConfigDict, Field

from app.domains.support.schemas import SupportTicketDetailOut, SupportTicketListItemOut, TicketMessageOut


class CustomerTicketCreateIn(BaseModel):
    category: str
    subject: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=1)
    priority: str = Field(default="medium")


class CustomerTicketMessageIn(BaseModel):
    body: str = Field(min_length=1)


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
