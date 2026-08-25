from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.shared.enums import BranchType


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    type: str
    city: str
    state: str
    address: str


class BranchAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    type: str
    city: str
    state: str
    address: str
    phone: str | None = None
    openingHours: dict | None = None
    isActive: bool
    vehicleCount: int = 0
    serviceBayCount: int = 0
    createdAt: datetime
    updatedAt: datetime


class BranchSummaryOut(BaseModel):
    total: int
    active: int
    inactive: int
    byType: dict[str, int]


class BranchCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=2, max_length=200)
    type: BranchType
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=5, max_length=500)
    phone: str | None = Field(default=None, max_length=30)
    openingHours: Annotated[dict | None, Field(alias="openingHours")] = None
    isActive: bool = Field(default=True, alias="isActive")

    @field_validator("name", "city", "state", "address")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("phone")
    @classmethod
    def _strip_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None


class BranchUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=2, max_length=200)
    type: BranchType | None = None
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    address: str | None = Field(default=None, min_length=5, max_length=500)
    phone: str | None = Field(default=None, max_length=30)
    openingHours: Annotated[dict | None, Field(alias="openingHours")] = None
    isActive: Annotated[bool | None, Field(alias="isActive")] = None

    @field_validator("name", "city", "state", "address", mode="before")
    @classmethod
    def _strip_optional(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def _strip_phone(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v
