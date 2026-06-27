from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.branches.models import Branch

router = APIRouter(prefix="/branches", tags=["branches"])


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    type: str
    city: str
    state: str
    address: str


@router.get("", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)) -> list[Branch]:
    return (
        db.query(Branch)
        .filter(Branch.is_active.is_(True))
        .order_by(Branch.name.asc())
        .all()
    )
