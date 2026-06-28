from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.analytics import service
from app.domains.analytics.schemas import AnalyticsOverviewOut

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get("/overview", response_model=AnalyticsOverviewOut)
def get_overview(_: StaffPortalUser, db: Session = Depends(get_db)) -> AnalyticsOverviewOut:
    return service.get_analytics_overview(db)
