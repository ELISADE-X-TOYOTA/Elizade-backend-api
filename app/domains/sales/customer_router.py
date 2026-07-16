from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.sales import service
from app.domains.sales.schemas import TestDriveCreateIn, TestDriveOut

router = APIRouter(prefix="/sales", tags=["customer-sales"])


@router.get("/test-drives", response_model=list[TestDriveOut])
def list_my_test_drives(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[TestDriveOut]:
    return service.list_my_test_drives(db, current_user.id)


@router.post("/test-drives", response_model=TestDriveOut, status_code=status.HTTP_201_CREATED)
def book_test_drive(
    payload: TestDriveCreateIn,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TestDriveOut:
    return service.create_test_drive(db, current_user, payload)
