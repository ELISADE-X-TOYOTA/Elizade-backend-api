from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.service import service
from app.domains.service.schemas import (
    CustomerAdditionalWorkDecisionIn,
    CustomerAppointmentListItemOut,
    CustomerServiceTrackOut,
    JobDetailOut,
)

router = APIRouter(prefix="/service", tags=["customer-service"])


@router.get("/appointments", response_model=list[CustomerAppointmentListItemOut])
def list_my_appointments(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[CustomerAppointmentListItemOut]:
    return service.list_customer_appointments(db, current_user.id)


@router.get("/appointments/{appointment_id}/track", response_model=CustomerServiceTrackOut)
def track_appointment(
    appointment_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> CustomerServiceTrackOut:
    return service.get_customer_service_track(db, current_user.id, appointment_id)


@router.patch(
    "/jobs/{job_id}/additional-work/{work_id}",
    response_model=JobDetailOut,
)
def respond_additional_work(
    job_id: str,
    work_id: str,
    payload: CustomerAdditionalWorkDecisionIn,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> JobDetailOut:
    return service.customer_respond_additional_work(db, current_user.id, job_id, work_id, payload)
