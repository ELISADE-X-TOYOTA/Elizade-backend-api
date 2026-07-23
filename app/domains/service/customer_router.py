from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.service import service
from app.domains.service.schemas import (
    CustomerAdditionalWorkDecisionIn,
    CustomerAppointmentCreateIn,
    CustomerAppointmentListItemOut,
    CustomerServiceTrackOut,
    JobDetailOut,
    PaginatedHistoryOut,
)

router = APIRouter(prefix="/service", tags=["customer-service"])


@router.get("/appointments", response_model=list[CustomerAppointmentListItemOut])
def list_my_appointments(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[CustomerAppointmentListItemOut]:
    return service.list_customer_appointments(db, current_user.id)


@router.post("/appointments", response_model=CustomerAppointmentListItemOut, status_code=status.HTTP_201_CREATED)
def book_appointment(
    payload: CustomerAppointmentCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerAppointmentListItemOut:
    return service.create_customer_appointment(db, current_user, payload)


@router.get("/appointments/{appointment_id}/track", response_model=CustomerServiceTrackOut)
def track_appointment(
    appointment_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerServiceTrackOut:
    return service.get_customer_service_track(db, current_user.id, appointment_id)


@router.get("/history", response_model=PaginatedHistoryOut)
def list_my_service_history(
    current_user: CustomerUser,
    vehicleId: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedHistoryOut:
    return service.list_customer_history(
        db, current_user.id, owned_vehicle_id=vehicleId, page=page, size=size
    )


@router.patch(
    "/jobs/{job_id}/additional-work/{work_id}",
    response_model=JobDetailOut,
)
def respond_additional_work(
    job_id: str,
    work_id: str,
    payload: CustomerAdditionalWorkDecisionIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> JobDetailOut:
    return service.customer_respond_additional_work(db, current_user.id, job_id, work_id, payload)
