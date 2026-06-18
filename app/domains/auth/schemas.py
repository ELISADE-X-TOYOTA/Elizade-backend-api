from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.users.schemas import UserProfileOut


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    phone: str = Field(min_length=7, max_length=20)
    purpose: str = Field(pattern="^(login|register)$")
    first_name: str | None = Field(default=None, alias="firstName", max_length=100)
    last_name: str | None = Field(default=None, alias="lastName", max_length=100)
    email: EmailStr | None = None


class OtpRequestOut(BaseModel):
    message: str
    expires_in_minutes: int


class OtpVerifyIn(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    code: str = Field(min_length=4, max_length=8)


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileOut
