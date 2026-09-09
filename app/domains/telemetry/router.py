"""Where the mobile app reports API failures it experienced.

The hook existed in the client from the start and nothing installed it, so
every client-side failure was shown to the customer and thrown away. That is
why a reported outage across the warranty screens could not be explained: 135
live checks found nothing wrong, and there was no record of what the tester
actually hit.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_optional
from app.domains.telemetry.models import ClientErrorReport
from app.domains.telemetry.schemas import ClientErrorBatchIn
from app.domains.users.models import User

logger = logging.getLogger("elizade.telemetry")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/client-errors", status_code=202)
def report_client_errors(
    payload: ClientErrorBatchIn,
    request: Request,
    current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
    db: Session = Depends(get_db),
) -> dict:
    """Accept a small batch of failures the app saw.

    UNAUTHENTICATED IS ALLOWED, deliberately. A failing sign-in is exactly the
    kind worth recording and has no user yet. The batch is capped in the
    schema, nothing here is read back to any customer, and no free text is
    accepted — only a fixed shape — so this cannot become a way to write
    arbitrary content into the database.

    202, not 201: the app must never wait on, or care about, telemetry.
    """
    rows = [
        ClientErrorReport(
            user_id=current_user.id if current_user else None,
            status=item.status,
            code=item.code,
            path=item.path[:300],
            method=item.method,
            request_id=item.requestId,
            is_network=item.isNetwork,
            duration_ms=item.durationMs,
            app_version=item.appVersion,
            platform=item.platform,
        )
        for item in payload.items
    ]
    db.add_all(rows)
    db.commit()

    # Logged as well as stored: a spike is visible in the log stream without
    # anyone thinking to query the table.
    for item in payload.items:
        logger.warning(
            "[CLIENT] %s %s -> status=%s code=%s request_id=%s network=%s",
            item.method,
            item.path,
            item.status,
            item.code,
            item.requestId,
            item.isNetwork,
        )
    return {"accepted": len(rows)}
