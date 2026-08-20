from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.users.schemas import UserProfileOut


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    purpose: str = Field(pattern="^(login|register)$")
    first_name: str | None = Field(default=None, alias="firstName", max_length=100)
    last_name: str | None = Field(default=None, alias="lastName", max_length=100)
    other_name: str | None = Field(default=None, alias="otherName", max_length=100)


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
