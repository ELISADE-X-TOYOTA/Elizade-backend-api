from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPreferences(BaseModel):
    push_enabled: bool = True
    sms_enabled: bool = True
    email_enabled: bool = True
    marketing_opt_in: bool = False


class UserPublic(BaseModel):
    id: str
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    email: str
    phone: str
    city: str
    state: str
    avatar: str | None = Field(default=None, alias="avatar")
    role: str
    department: str | None = None
    preferences: UserPreferences

    model_config = {"from_attributes": True, "populate_by_name": True}


class UserPreferencesOut(BaseModel):
    pushEnabled: bool
    smsEnabled: bool
    emailEnabled: bool
    marketingOptIn: bool

    @staticmethod
    def from_db(prefs: dict) -> "UserPreferencesOut":
        return UserPreferencesOut(
            pushEnabled=bool(prefs.get("push_enabled", True)),
            smsEnabled=bool(prefs.get("sms_enabled", True)),
            emailEnabled=bool(prefs.get("email_enabled", True)),
            marketingOptIn=bool(prefs.get("marketing_opt_in", False)),
        )


class UserProfileOut(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str
    phone: str
    city: str
    state: str
    avatar: str | None = None
    role: str
    department: str | None = None
    preferences: UserPreferencesOut

    @staticmethod
    def from_user(user) -> "UserProfileOut":
        email = user.email or f"{user.phone_normalized}@placeholder.elizade.local"
        return UserProfileOut(
            id=user.id,
            firstName=user.first_name,
            lastName=user.last_name,
            email=email,
            phone=user.phone_display,
            city=user.city,
            state=user.state,
            avatar=user.avatar_url,
            role=user.role.value,
            department=user.department,
            preferences=UserPreferencesOut.from_db(user.preferences or {}),
        )


class UserProfileUpdateIn(BaseModel):
    """Profile fields a signed-in user may update. Phone changes require OTP re-auth via /auth."""

    model_config = ConfigDict(populate_by_name=True)

    first_name: str | None = Field(default=None, alias="firstName", max_length=100)
    last_name: str | None = Field(default=None, alias="lastName", max_length=100)
    email: EmailStr | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    avatar: str | None = Field(default=None, alias="avatar", max_length=512)


class UserPreferencesUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    push_enabled: bool | None = Field(default=None, alias="pushEnabled")
    sms_enabled: bool | None = Field(default=None, alias="smsEnabled")
    email_enabled: bool | None = Field(default=None, alias="emailEnabled")
    marketing_opt_in: bool | None = Field(default=None, alias="marketingOptIn")
