import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClientErrorReport(Base):
    """One API failure as the MOBILE APP experienced it.

    WHY THIS EXISTS. A tester reported "Elizade services are temporarily
    unavailable" across every warranty screen. That message is the client's
    text for an HTTP 5xx, so something genuinely failed — and there was no
    record of it anywhere. Driving all the warranty endpoints against the live
    database for all 45 customer accounts produced 135 requests and zero
    errors, so the fault could not be reproduced and could not be explained.

    The app had the hook for this the whole time: `setApiErrorReporter` was
    defined in `src/api/client.ts`, its comment said the layout registered the
    real reporter, and nothing ever called it. Every client-side failure was
    computed, formatted, shown to the customer and dropped.

    Server logs alone would not have answered it either: a 5xx behind a load
    balancer, a request that never arrived, and a client that gave up at 20
    seconds all look different from the two ends. `request_id` is what joins
    them — the same value the customer can read off the error screen.

    DELIBERATELY NOT STORED: no URL query strings, no request or response
    bodies, no headers. `path` is the route template, which is enough to find
    the endpoint and cannot carry a customer's data.
    """

    __tablename__ = "client_error_reports"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    #: Null for failures while signed out — a broken sign-in is exactly the
    #: kind that needs recording, and it has no user yet.
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True
    )
    #: HTTP status, or 0 when no response arrived at all.
    status: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    #: `client_timeout`, `client_offline`, or the server's own error code.
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The server's `X-Request-ID`, joining this to the server-side log line.
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    #: True when nothing came back — abort, DNS, offline.
    is_network: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
