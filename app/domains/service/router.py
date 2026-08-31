from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin, StaffPortalUser
from app.domains.service import service
from app.domains.service import price_book_service
from app.domains.service import maintenance_service
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
    ServiceHistoryLinesReplaceIn,
    ServiceItemCreateIn,
    ServiceItemOut,
    ServiceItemUpdateIn,
    ServiceStatsOut,
    StageUpdateIn,
)
from app.domains.service.price_book_schemas import (
    BoardVehicleModelOut,
    PriceBookBoardOut,
    PriceBookDetailOut,
    PriceBookVersionOut,
    PriceImportPreviewOut,
    PriceImportPublishOut,
    PricePublishIn,
)
from app.domains.service.maintenance_schemas import (
    BoardSettingsOut,
    BoardSettingsUpdateIn,
    PaginatedMaintenanceSummaryOut,
    ServiceIntervalCreateIn,
    ServiceIntervalOut,
    ServiceIntervalUpdateIn,
    VehicleMaintenanceOut,
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
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> AppointmentDetailOut:
    return service.change_appointment_status(db, appointment_id, payload, actor=current_user)


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
# Service-item catalogue                                                      #
# --------------------------------------------------------------------------- #

@router.get("/items", response_model=list[ServiceItemOut])
def list_items(
    _: StaffPortalUser,
    group: str | None = Query(default=None),
    isActive: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ServiceItemOut]:
    return service.list_items(db, group=group, is_active=isActive)


@router.post("/items", response_model=ServiceItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ServiceItemCreateIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> ServiceItemOut:
    return service.create_item(db, payload, actor_id=current_user.id)


@router.patch("/items/{item_id}", response_model=ServiceItemOut)
def update_item(
    item_id: str,
    payload: ServiceItemUpdateIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> ServiceItemOut:
    return service.update_item(db, item_id, payload, actor_id=current_user.id)


# --------------------------------------------------------------------------- #
# Service history                                                             #
# --------------------------------------------------------------------------- #

@router.get("/history", response_model=PaginatedHistoryOut)
def list_history(
    _: StaffPortalUser,
    customerId: str | None = Query(default=None),
    vehicleId: str | None = Query(default=None),
    unmappedOnly: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedHistoryOut:
    return service.list_history(
        db,
        customer_id=customerId,
        owned_vehicle_id=vehicleId,
        unmapped_only=unmappedOnly,
        page=page,
        size=size,
    )


@router.get("/history/{history_id}", response_model=ServiceHistoryItemOut)
def get_history(
    history_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> ServiceHistoryItemOut:
    return service.get_history(db, history_id)


@router.post("/history", response_model=ServiceHistoryItemOut, status_code=status.HTTP_201_CREATED)
def create_history(
    payload: ServiceHistoryCreateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> ServiceHistoryItemOut:
    return service.create_history(db, payload, actor=current_user)


@router.put("/history/{history_id}/lines", response_model=ServiceHistoryItemOut)
def replace_history_lines(
    history_id: str,
    payload: ServiceHistoryLinesReplaceIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> ServiceHistoryItemOut:
    return service.replace_history_lines(db, history_id, payload, actor=current_user)


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


# --------------------------------------------------------------------------- #
# Price book (Phase 2)                                                        #
# --------------------------------------------------------------------------- #

@router.get("/price-book/board", response_model=PriceBookBoardOut)
def get_published_price_board(_: StaffPortalUser, db: Session = Depends(get_db)) -> PriceBookBoardOut:
    return price_book_service.get_published_board(db)


@router.get("/price-book/models", response_model=list[BoardVehicleModelOut])
def list_board_models(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[BoardVehicleModelOut]:
    return price_book_service.list_board_models(db)


@router.get("/price-book/mileage-bands", response_model=list[int])
def list_mileage_bands(_: StaffPortalUser) -> list[int]:
    return price_book_service.list_mileage_bands()


@router.get("/price-book/versions", response_model=list[PriceBookVersionOut])
def list_price_book_versions(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[PriceBookVersionOut]:
    return price_book_service.list_versions(db)


@router.get("/price-book/versions/{version_id}", response_model=PriceBookDetailOut)
def get_price_book_version(
    version_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> PriceBookDetailOut:
    return price_book_service.get_version(db, version_id)


@router.get("/price-book/import/template")
def price_import_template(_: CurrentAdmin, db: Session = Depends(get_db)) -> Response:
    content = price_book_service.import_template_csv(db)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="elizade-service-price-import-template.csv"'},
    )


@router.post("/price-book/import/preview", response_model=PriceImportPreviewOut)
def preview_price_import(
    _: CurrentAdmin,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PriceImportPreviewOut:
    return price_book_service.preview_price_import(db, file)


@router.post("/price-book/import/publish", response_model=PriceImportPublishOut)
def publish_price_import(
    current_user: CurrentAdmin,
    file: UploadFile = File(...),
    effectiveFrom: str | None = Form(default=None),
    disclaimer: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> PriceImportPublishOut:
    from datetime import datetime

    effective_from = None
    if effectiveFrom:
        effective_from = datetime.fromisoformat(effectiveFrom.replace("Z", "+00:00"))
    payload = PricePublishIn(effectiveFrom=effective_from, disclaimer=disclaimer)
    return price_book_service.publish_price_import(db, file, payload, actor=current_user)


# --------------------------------------------------------------------------- #
# Maintenance status (Phase 3)                                                #
# --------------------------------------------------------------------------- #

@router.get("/maintenance/settings", response_model=BoardSettingsOut)
def get_maintenance_settings(_: StaffPortalUser, db: Session = Depends(get_db)) -> BoardSettingsOut:
    return maintenance_service.get_settings(db)


@router.put("/maintenance/settings", response_model=BoardSettingsOut)
def update_maintenance_settings(
    payload: BoardSettingsUpdateIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> BoardSettingsOut:
    return maintenance_service.update_settings(db, payload, actor=current_user)


@router.get("/maintenance/intervals", response_model=list[ServiceIntervalOut])
def list_maintenance_intervals(
    _: StaffPortalUser,
    db: Session = Depends(get_db),
    serviceItemId: str | None = Query(default=None),
) -> list[ServiceIntervalOut]:
    return maintenance_service.list_intervals(db, service_item_id=serviceItemId)


@router.post("/maintenance/intervals", response_model=ServiceIntervalOut, status_code=status.HTTP_201_CREATED)
def create_maintenance_interval(
    payload: ServiceIntervalCreateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> ServiceIntervalOut:
    return maintenance_service.create_interval(db, payload)


@router.patch("/maintenance/intervals/{interval_id}", response_model=ServiceIntervalOut)
def update_maintenance_interval(
    interval_id: str,
    payload: ServiceIntervalUpdateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> ServiceIntervalOut:
    return maintenance_service.update_interval(db, interval_id, payload)


@router.get("/maintenance/due-soon", response_model=PaginatedMaintenanceSummaryOut)
def list_due_soon_vehicles(
    _: StaffPortalUser,
    db: Session = Depends(get_db),
    model: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedMaintenanceSummaryOut:
    return maintenance_service.list_due_soon(db, model=model, page=page, size=size)


@router.get("/maintenance/overdue", response_model=PaginatedMaintenanceSummaryOut)
def list_overdue_vehicles(
    _: StaffPortalUser,
    db: Session = Depends(get_db),
    model: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedMaintenanceSummaryOut:
    return maintenance_service.list_overdue(db, model=model, page=page, size=size)


@router.get("/maintenance/call-list", response_model=PaginatedMaintenanceSummaryOut)
def list_call_list(
    _: StaffPortalUser,
    db: Session = Depends(get_db),
    model: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedMaintenanceSummaryOut:
    return maintenance_service.list_call_list(db, model=model, page=page, size=size)


@router.get("/maintenance/vehicles/{owned_vehicle_id}", response_model=VehicleMaintenanceOut)
def get_vehicle_maintenance(
    owned_vehicle_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> VehicleMaintenanceOut:
    return maintenance_service.get_vehicle_maintenance(db, owned_vehicle_id)
