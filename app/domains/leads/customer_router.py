"""Customer lead tracking — `/leads`.

Read-only by design. Customers see their enquiries progress; they do not
create, reassign or re-stage them. Lead creation already happens through the
channels that generate leads (test drive requests, enquiries, showroom
visits), and letting a customer POST a lead here would let them inject
arbitrary rows into the sales pipeline.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.leads import customer_service
from app.domains.leads.customer_schemas import CustomerLeadDetailOut, CustomerLeadOut

router = APIRouter(prefix="/leads", tags=["customer-leads"])


@router.get("", response_model=list[CustomerLeadOut])
def list_my_leads(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[CustomerLeadOut]:
    """Leads belonging to the signed-in customer, newest activity first."""
    return customer_service.list_my_leads(db, current_user.id)


@router.get("/{lead_id}", response_model=CustomerLeadDetailOut)
def get_my_lead(
    lead_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> CustomerLeadDetailOut:
    """One lead with its progress tracker and readable history.

    404 when the lead belongs to another customer — see `customer_service`.
    """
    return customer_service.get_my_lead(db, current_user.id, lead_id)
