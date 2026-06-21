from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.inventory import service
from app.domains.inventory.schemas import VehicleDetailOut, VehicleListOut

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
) -> VehicleListOut:
    return service.list_vehicles(
        db,
        branch_id=branchId,
        make=make,
        model=model,
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


@router.get("/{vehicle_id}", response_model=VehicleDetailOut)
def get_vehicle(vehicle_id: str, db: Session = Depends(get_db)) -> VehicleDetailOut:
    return service.get_vehicle(db, vehicle_id)
