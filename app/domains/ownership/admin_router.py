from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.ownership import service
from app.domains.ownership.schemas import (
    OwnershipRequestListItemOut,
    OwnershipRequestUpdateIn,
    PaginatedOwnershipRequestsOut,
)

router = APIRouter(prefix="/admin/ownership", tags=["admin-ownership"])


@router.get("/requests", response_model=PaginatedOwnershipRequestsOut)
def list_requests(
    _: StaffPortalUser,
    status: str | None = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedOwnershipRequestsOut:
    return service.list_requests_admin(db, status_filter=status, page=page, size=size)


@router.get("/requests/{request_id}", response_model=OwnershipRequestListItemOut)
def get_request(
    request_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> OwnershipRequestListItemOut:
    return service.get_request_admin(db, request_id)


@router.patch("/requests/{request_id}", response_model=OwnershipRequestListItemOut)
def update_request(
    request_id: str,
    payload: OwnershipRequestUpdateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> OwnershipRequestListItemOut:
    return service.update_request_admin(db, request_id, payload, reviewer_id=current_user.id)
