from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.dashboard import service
from app.domains.dashboard.schemas import DashboardSummaryOut

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def get_summary(_: StaffPortalUser, db: Session = Depends(get_db)) -> DashboardSummaryOut:
    return service.get_dashboard_summary(db)
