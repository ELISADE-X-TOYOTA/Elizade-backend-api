from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin, StaffPortalUser
from app.domains.service import service
from app.domains.service.schemas import (
    AdditionalWorkCreateIn,
    AdditionalWorkStatusUpdateIn,
    AppointmentBoardItemOut,
    AppointmentDetailOut,
    AppointmentStatusActionIn,
    AppointmentUpdateIn,
    JobDetailOut,
    PaginatedHistoryOut,
    ServiceBayCreateIn,
    ServiceBayOut,
    ServiceBayUpdateIn,
    ServiceHistoryCreateIn,
    ServiceHistoryItemOut,
    ServiceStatsOut,
    StageUpdateIn,
)

router = APIRouter(prefix="/admin/service", tags=["admin-service"])


@router.get("/stats", response_model=ServiceStatsOut)
def get_stats(_: StaffPortalUser, db: Session = Depends(get_db)) -> ServiceStatsOut:
    return service.get_stats(db)


# --------------------------------------------------------------------------- #
# Appointments                                                                #
# --------------------------------------------------------------------------- #

@router.get("/appointments", response_model=list[AppointmentBoardItemOut])
def list_appointments(
    _: StaffPortalUser,
    date: str | None = Query(default=None),
    branchId: str | None = Query(default=None),
    status: str | None = Query(default=None),
    bayId: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AppointmentBoardItemOut]:
    return service.list_appointments(
        db, date=date, branch_id=branchId, status_filter=status, bay_id=bayId
    )


@router.get("/appointments/{appointment_id}", response_model=AppointmentDetailOut)
def get_appointment(
    appointment_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> AppointmentDetailOut:
    return service.get_appointment(db, appointment_id)


@router.patch("/appointments/{appointment_id}", response_model=AppointmentDetailOut)
def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> AppointmentDetailOut:
    return service.update_appointment(db, appointment_id, payload)


@router.patch("/appointments/{appointment_id}/status", response_model=AppointmentDetailOut)
def change_appointment_status(
    appointment_id: str,
    payload: AppointmentStatusActionIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> AppointmentDetailOut:
    return service.change_appointment_status(db, appointment_id, payload)


# --------------------------------------------------------------------------- #
# Jobs                                                                        #
# --------------------------------------------------------------------------- #

@router.get("/jobs/{job_id}", response_model=JobDetailOut)
def get_job(job_id: str, _: StaffPortalUser, db: Session = Depends(get_db)) -> JobDetailOut:
    return service.get_job(db, job_id)


@router.patch("/jobs/{job_id}/stages/{stage_id}", response_model=JobDetailOut)
def update_job_stage(
    job_id: str,
    stage_id: str,
    payload: StageUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> JobDetailOut:
    return service.update_job_stage(db, job_id, stage_id, payload)


@router.post(
    "/jobs/{job_id}/additional-work",
    response_model=JobDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def add_additional_work(
    job_id: str,
    payload: AdditionalWorkCreateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> JobDetailOut:
    return service.add_additional_work(db, job_id, payload)


@router.patch("/jobs/{job_id}/additional-work/{work_id}", response_model=JobDetailOut)
def update_additional_work(
    job_id: str,
    work_id: str,
    payload: AdditionalWorkStatusUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> JobDetailOut:
    return service.update_additional_work(db, job_id, work_id, payload)


# --------------------------------------------------------------------------- #
# Service history                                                             #
# --------------------------------------------------------------------------- #

@router.get("/history", response_model=PaginatedHistoryOut)
def list_history(
    _: StaffPortalUser,
    customerId: str | None = Query(default=None),
    vehicleId: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedHistoryOut:
    return service.list_history(db, customer_id=customerId, owned_vehicle_id=vehicleId, page=page, size=size)


@router.post("/history", response_model=ServiceHistoryItemOut, status_code=status.HTTP_201_CREATED)
def create_history(
    payload: ServiceHistoryCreateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> ServiceHistoryItemOut:
    return service.create_history(db, payload)


@router.delete("/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history(
    history_id: str,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> Response:
    service.delete_history(db, history_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/bays", response_model=list[ServiceBayOut])
def list_bays(
    _: StaffPortalUser,
    branchId: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ServiceBayOut]:
    return service.list_bays(db, branch_id=branchId)


@router.post("/bays", response_model=ServiceBayOut, status_code=status.HTTP_201_CREATED)
def create_bay(
    payload: ServiceBayCreateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> ServiceBayOut:
    return service.create_bay(db, payload)


@router.patch("/bays/{bay_id}", response_model=ServiceBayOut)
def update_bay(
    bay_id: str,
    payload: ServiceBayUpdateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> ServiceBayOut:
    return service.update_bay(db, bay_id, payload)
