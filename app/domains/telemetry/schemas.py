from pydantic import BaseModel, ConfigDict, Field


class ClientErrorIn(BaseModel):
    """One failure, exactly as `ApiErrorReport` describes it in the app."""

    model_config = ConfigDict(populate_by_name=True)

    #: 0 when no response arrived at all.
    status: int = Field(ge=0, le=599)
    code: str | None = Field(default=None, max_length=100)
    #: Route template only. Query strings are never sent — they can carry
    #: customer data and are not needed to identify an endpoint.
    path: str = Field(min_length=1, max_length=300)
    method: str = Field(min_length=3, max_length=10)
    requestId: str | None = Field(default=None, max_length=100)
    isNetwork: bool = False
    durationMs: int | None = Field(default=None, ge=0)
    appVersion: str | None = Field(default=None, max_length=50)
    platform: str | None = Field(default=None, max_length=20)


class ClientErrorBatchIn(BaseModel):
    """A capped batch.

    Bounded so an offline device coming back online cannot flush a thousand
    buffered failures in one request — the client drops the oldest instead.
    """

    items: list[ClientErrorIn] = Field(min_length=1, max_length=20)
