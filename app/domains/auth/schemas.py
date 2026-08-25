from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.users.schemas import UserProfileOut


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    purpose: str = Field(pattern="^(login|register)$")
    # `Annotated[...]` rather than `str | None = Field(alias=...)`: newer
    # pydantic attaches the Field to a single union member and silently drops
    # the alias, so `firstName` from the client stops binding and registration
    # fails with "first and last name are required". Annotated attaches it to
    # the FIELD, which is unambiguous.
    first_name: Annotated[str | None, Field(alias="firstName", max_length=100)] = None
    last_name: Annotated[str | None, Field(alias="lastName", max_length=100)] = None
    other_name: Annotated[str | None, Field(alias="otherName", max_length=100)] = None


class OtpRequestOut(BaseModel):
    message: str
    expires_in_minutes: int


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileOut


class EmailAvailabilityOut(BaseModel):
    """Whether an email can be used to register a new account."""

    email: EmailStr
    available: bool
    reason: str | None = None
