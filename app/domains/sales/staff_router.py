"""Staff actions on the sales pipeline.

There were none for test drives. `/sales` exposed list and create, both for
the customer, so a booking was created as `requested` and nothing anywhere
could move it: no confirmation, no cancellation, no completion. The customer's
own screen worked around it by showing the linked LEAD's stage instead of the
booking's own status.

It is also why `TEST_DRIVE_CONFIRMED` and `TEST_DRIVE_CANCELLED` had never
been sent once. Both were written, catalogued and wired to three channels, and
there was no action in the system capable of reaching them.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.sales import service
from app.domains.sales.schemas import TestDriveOut, TestDriveStatusActionIn

router = APIRouter(prefix="/sales", tags=["staff-sales"])


@router.patch("/test-drives/{booking_id}/status", response_model=TestDriveOut)
def change_test_drive_status(
    booking_id: str,
    payload: TestDriveStatusActionIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> TestDriveOut:
    """Confirm, cancel or complete a customer's test drive.

    Confirming notifies the customer; so does cancelling. Completing does not —
    they were there.
    """
    return service.change_test_drive_status(db, booking_id, payload)
