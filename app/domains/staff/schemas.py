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

    first_name: str | None = Field(default=None, alias="firstName", max_length=100)
    last_name: str | None = Field(default=None, alias="lastName", max_length=100)
    email: EmailStr | None = None
    department: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    is_active: bool | None = Field(default=None, alias="isActive")


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
    isActive: bool
    isVerified: bool
    createdAt: str
    updatedAt: str | None = None
