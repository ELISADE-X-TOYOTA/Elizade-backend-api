from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin, StaffPortalUser
from app.domains.inventory import service
from app.domains.inventory.schemas import (
    BulkImportResultOut,
    VehicleAdminDetailOut,
    VehicleAdminListOut,
    VehicleCreateIn,
    VehicleStatusUpdateIn,
    VehicleUpdateIn,
)

router = APIRouter(prefix="/admin/vehicles", tags=["admin-vehicles"])


@router.get("", response_model=VehicleAdminListOut)
def list_vehicles(
    _: StaffPortalUser,
    db: Session = Depends(get_db),
    branchId: str | None = Query(default=None),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    availability: str | None = Query(default=None),
    isPublished: bool | None = Query(default=None),
    includeDeleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-createdAt"),
) -> VehicleAdminListOut:
    return service.admin_list_vehicles(
        db,
        branch_id=branchId,
        make=make,
        model=model,
        availability=availability,
        is_published=isPublished,
        include_deleted=includeDeleted,
        page=page,
        limit=limit,
        sort=sort,
    )


@router.get("/{vehicle_id}", response_model=VehicleAdminDetailOut)
def get_vehicle(
    vehicle_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> VehicleAdminDetailOut:
    return service.admin_get_vehicle(db, vehicle_id)


@router.post("", response_model=VehicleAdminDetailOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleCreateIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> VehicleAdminDetailOut:
    return service.create_vehicle(db, payload, current_user)


@router.post("/bulk-import", response_model=BulkImportResultOut)
def bulk_import_vehicles(
    current_user: CurrentAdmin,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BulkImportResultOut:
    return service.bulk_import_vehicles(db, file, current_user)


@router.patch("/{vehicle_id}", response_model=VehicleAdminDetailOut)
def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> VehicleAdminDetailOut:
    return service.update_vehicle(db, vehicle_id, payload)


@router.patch("/{vehicle_id}/status", response_model=VehicleAdminDetailOut)
def update_vehicle_status(
    vehicle_id: str,
    payload: VehicleStatusUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> VehicleAdminDetailOut:
    return service.update_vehicle_status(db, vehicle_id, payload)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: str,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> Response:
    service.soft_delete_vehicle(db, vehicle_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{vehicle_id}/images", response_model=VehicleAdminDetailOut, status_code=status.HTTP_201_CREATED)
def upload_images(
    vehicle_id: str,
    _: CurrentAdmin,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> VehicleAdminDetailOut:
    return service.add_vehicle_images(db, vehicle_id, files)


@router.delete("/{vehicle_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    vehicle_id: str,
    image_id: str,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> Response:
    service.delete_vehicle_image(db, vehicle_id, image_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
