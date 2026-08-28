from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StaffCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    phone: str = Field(min_length=7, max_length=20)
    first_name: str = Field(alias="firstName", min_length=1, max_length=100)
    last_name: str = Field(alias="lastName", min_length=1, max_length=100)
    email: EmailStr
    department: str = Field(min_length=1, max_length=100)
    city: str = "Lagos"
    state: str = "Lagos"
    send_welcome_otp: bool = Field(default=True, alias="sendWelcomeOtp")


class StaffUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: Annotated[str | None, Field(alias="firstName", max_length=100)] = None
    last_name: Annotated[str | None, Field(alias="lastName", max_length=100)] = None
    email: EmailStr | None = None
    department: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    is_active: Annotated[bool | None, Field(alias="isActive")] = None


class StaffOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    firstName: str
    lastName: str
    email: str
    phone: str
    department: str
    city: str
    state: str
    role: str
    isActive: bool
    isVerified: bool
    createdAt: str
    updatedAt: str | None = None
