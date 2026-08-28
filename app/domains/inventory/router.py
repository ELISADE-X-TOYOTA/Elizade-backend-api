from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.inventory import service
from app.domains.inventory.schemas import (
    NotifyMeStatusOut,
    VehicleDetailOut,
    VehicleListOut,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=VehicleListOut)
def list_vehicles(
    db: Session = Depends(get_db),
    branchId: str | None = Query(default=None),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    minPrice: float | None = Query(default=None, ge=0),
    maxPrice: float | None = Query(default=None, ge=0),
    fuelType: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    availability: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-createdAt"),
    q: str | None = Query(default=None, min_length=1, max_length=100),
) -> VehicleListOut:
    return service.list_vehicles(
        db,
        branch_id=branchId,
        make=make,
        model=model,
        q=q,
        min_price=minPrice,
        max_price=maxPrice,
        fuel_type=fuelType,
        transmission=transmission,
        availability=availability,
        page=page,
        limit=limit,
        sort=sort,
    )


# Declared before the /{vehicle_id} route so "compare" is not matched as an id.
@router.get("/compare", response_model=list[VehicleDetailOut])
def compare_vehicles(
    ids: str = Query(..., description="Comma-separated vehicle ids (exactly two)"),
    db: Session = Depends(get_db),
) -> list[VehicleDetailOut]:
    return service.compare_vehicles(db, ids)


@router.get("/{vehicle_id}/notify-me", response_model=NotifyMeStatusOut)
def get_availability_subscription_status(
    vehicle_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> NotifyMeStatusOut:
    return service.get_vehicle_availability_subscription_status(db, vehicle_id, current_user.id)


@router.post(
    "/{vehicle_id}/notify-me",
    response_model=NotifyMeStatusOut,
    status_code=status.HTTP_201_CREATED,
)
def subscribe_to_availability(
    vehicle_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> NotifyMeStatusOut:
    subscription = service.subscribe_to_vehicle_availability(db, vehicle_id, current_user.id)
    return service.notify_me_status_out(vehicle_id, subscription)


@router.delete("/{vehicle_id}/notify-me", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_from_availability(
    vehicle_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> Response:
    service.unsubscribe_from_vehicle_availability(db, vehicle_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{vehicle_id}", response_model=VehicleDetailOut)
def get_vehicle(vehicle_id: str, db: Session = Depends(get_db)) -> VehicleDetailOut:
    return service.get_vehicle(db, vehicle_id)
