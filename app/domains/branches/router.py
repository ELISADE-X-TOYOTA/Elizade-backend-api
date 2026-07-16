from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.branches import service
from app.domains.branches.schemas import BranchOut

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)) -> list[BranchOut]:
    return service.list_public_branches(db)
