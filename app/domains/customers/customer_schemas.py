from pydantic import BaseModel, ConfigDict, Field


class WatchlistItemOut(BaseModel):
    id: str
    model: str
    trim: str | None = None
    color: str | None = None
    isActive: bool
    createdAt: str

    @staticmethod
    def from_model(row) -> "WatchlistItemOut":
        return WatchlistItemOut(
            id=row.id,
            model=row.model,
            trim=row.trim,
            color=row.color,
            isActive=row.is_active,
            createdAt=row.created_at.isoformat(),
        )


class WatchlistCreateIn(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    trim: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=100)


class WatchlistUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trim: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=100)
    is_active: bool | None = Field(default=None, alias="isActive")
