from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.branches.models import Branch
from app.domains.branches.schemas import (
    BranchAdminOut,
    BranchCreateIn,
    BranchOut,
    BranchSummaryOut,
    BranchUpdateIn,
)
from app.domains.inventory.models import Vehicle
from app.domains.service.models import ServiceBay
from app.domains.shared.enums import BranchType


def _counts(db: Session, branch_id: str) -> tuple[int, int]:
    vehicles = (
        db.query(func.count(Vehicle.id))
        .filter(Vehicle.branch_id == branch_id, Vehicle.deleted_at.is_(None))
        .scalar()
        or 0
    )
    bays = db.query(func.count(ServiceBay.id)).filter(ServiceBay.branch_id == branch_id).scalar() or 0
    return vehicles, bays


def _to_admin_out(db: Session, branch: Branch) -> BranchAdminOut:
    vehicle_count, bay_count = _counts(db, branch.id)
    return BranchAdminOut(
        id=branch.id,
        name=branch.name,
        type=branch.type.value,
        city=branch.city,
        state=branch.state,
        address=branch.address,
        phone=branch.phone,
        openingHours=branch.opening_hours,
        isActive=branch.is_active,
        vehicleCount=vehicle_count,
        serviceBayCount=bay_count,
        createdAt=branch.created_at,
        updatedAt=branch.updated_at,
    )


def list_public_branches(db: Session) -> list[BranchOut]:
    rows = (
        db.query(Branch)
        .filter(Branch.is_active.is_(True))
        .order_by(Branch.name.asc())
        .all()
    )
    return [BranchOut.model_validate(row) for row in rows]


def list_admin_branches(
    db: Session,
    *,
    q: str | None = None,
    type_filter: str | None = None,
    include_inactive: bool = True,
) -> list[BranchAdminOut]:
    query = db.query(Branch).order_by(Branch.name.asc())
    if not include_inactive:
        query = query.filter(Branch.is_active.is_(True))
    if type_filter and type_filter.strip().lower() not in ("all", ""):
        try:
            wanted = BranchType(type_filter.strip().lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid type '{type_filter}'. Valid: showroom, service_centre, both",
            )
        query = query.filter(Branch.type == wanted)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            (Branch.name.ilike(term))
            | (Branch.city.ilike(term))
            | (Branch.state.ilike(term))
            | (Branch.address.ilike(term))
        )
    return [_to_admin_out(db, row) for row in query.all()]


def get_branch_summary(db: Session) -> BranchSummaryOut:
    rows = db.query(Branch.type, Branch.is_active, func.count(Branch.id)).group_by(Branch.type, Branch.is_active).all()
    by_type: dict[str, int] = {t.value: 0 for t in BranchType}
    total = active = inactive = 0
    for branch_type, is_active, count in rows:
        total += count
        if is_active:
            active += count
        else:
            inactive += count
        by_type[branch_type.value] = by_type.get(branch_type.value, 0) + count
    return BranchSummaryOut(total=total, active=active, inactive=inactive, byType=by_type)


def get_branch_admin(db: Session, branch_id: str) -> BranchAdminOut:
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return _to_admin_out(db, branch)


def _assert_unique_name(db: Session, *, name: str, city: str, exclude_id: str | None = None) -> None:
    query = db.query(Branch).filter(
        func.lower(Branch.name) == name.lower(),
        func.lower(Branch.city) == city.lower(),
    )
    if exclude_id:
        query = query.filter(Branch.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A branch with this name already exists in this city",
        )


def create_branch(db: Session, payload: BranchCreateIn) -> BranchAdminOut:
    _assert_unique_name(db, name=payload.name, city=payload.city)
    branch = Branch(
        name=payload.name,
        type=payload.type,
        city=payload.city,
        state=payload.state,
        address=payload.address,
        phone=payload.phone,
        opening_hours=payload.openingHours,
        is_active=payload.isActive,
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return _to_admin_out(db, branch)


def update_branch(db: Session, branch_id: str, payload: BranchUpdateIn) -> BranchAdminOut:
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    data = payload.model_dump(exclude_unset=True)
    new_name = data.get("name", branch.name)
    new_city = data.get("city", branch.city)
    if "name" in data or "city" in data:
        _assert_unique_name(db, name=new_name, city=new_city, exclude_id=branch.id)

    if "name" in data:
        branch.name = data["name"]
    if "type" in data and data["type"] is not None:
        branch.type = data["type"]
    if "city" in data:
        branch.city = data["city"]
    if "state" in data:
        branch.state = data["state"]
    if "address" in data:
        branch.address = data["address"]
    if "phone" in data:
        branch.phone = data["phone"]
    if "openingHours" in data:
        branch.opening_hours = data["openingHours"]
    if "isActive" in data and data["isActive"] is not None:
        branch.is_active = data["isActive"]

    db.commit()
    db.refresh(branch)
    return _to_admin_out(db, branch)
