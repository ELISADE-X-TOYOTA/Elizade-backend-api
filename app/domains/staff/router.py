from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin
from app.domains.staff import service
from app.domains.staff.schemas import StaffCreateIn, StaffOut, StaffUpdateIn

router = APIRouter(prefix="/admin/staff", tags=["admin-staff"])


@router.get("", response_model=list[StaffOut])
def list_staff_members(_: CurrentAdmin, db: Session = Depends(get_db)) -> list[StaffOut]:
    return service.list_staff(db)


@router.post("", response_model=StaffOut, status_code=201)
def create_staff_member(
    payload: StaffCreateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> StaffOut:
    return service.create_staff(db, payload)


@router.patch("/{staff_id}", response_model=StaffOut)
def update_staff_member(
    staff_id: str,
    payload: StaffUpdateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> StaffOut:
    return service.update_staff(db, staff_id, payload)


@router.post("/{staff_id}/send-otp")
def send_staff_otp(
    staff_id: str,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    return service.send_staff_login_otp(db, staff_id)
