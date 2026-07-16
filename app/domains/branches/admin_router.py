from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin
from app.domains.branches import service
from app.domains.branches.schemas import BranchAdminOut, BranchCreateIn, BranchSummaryOut, BranchUpdateIn

router = APIRouter(prefix="/admin/branches", tags=["admin-branches"])


@router.get("/summary", response_model=BranchSummaryOut)
def get_summary(_: CurrentAdmin, db: Session = Depends(get_db)) -> BranchSummaryOut:
    return service.get_branch_summary(db)


@router.get("", response_model=list[BranchAdminOut])
def list_branches(
    _: CurrentAdmin,
    q: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    includeInactive: bool = Query(default=True, alias="includeInactive"),
    db: Session = Depends(get_db),
) -> list[BranchAdminOut]:
    return service.list_admin_branches(
        db, q=q, type_filter=type, include_inactive=includeInactive
    )


@router.get("/{branch_id}", response_model=BranchAdminOut)
def get_branch(branch_id: str, _: CurrentAdmin, db: Session = Depends(get_db)) -> BranchAdminOut:
    return service.get_branch_admin(db, branch_id)


@router.post("", response_model=BranchAdminOut, status_code=201)
def create_branch(
    payload: BranchCreateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> BranchAdminOut:
    return service.create_branch(db, payload)


@router.patch("/{branch_id}", response_model=BranchAdminOut)
def update_branch(
    branch_id: str,
    payload: BranchUpdateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> BranchAdminOut:
    return service.update_branch(db, branch_id, payload)
