from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.dashboard.customer_schemas import CustomerDashboardSummaryOut
from app.domains.dashboard.customer_service import get_customer_summary

router = APIRouter(prefix="/dashboard", tags=["customer-dashboard"])


@router.get("/summary", response_model=CustomerDashboardSummaryOut)
def customer_summary(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerDashboardSummaryOut:
    return get_customer_summary(db, current_user.id)
