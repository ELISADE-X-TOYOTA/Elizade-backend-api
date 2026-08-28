from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin, StaffPortalUser
from app.domains.customers import service
from app.domains.customers.schemas import (
    CustomerMergeIn,
    CustomerMergeOut,
    CustomerNoteCreate,
    CustomerNoteOut,
    CustomerProfileOut,
    CustomerTimelineOut,
    CustomerVehiclesOut,
    DuplicateCustomerCandidateOut,
    DuplicateCustomerReviewIn,
    PaginatedCustomersOut,
    CustomerSegmentsOut,
)

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"])


@router.get("/segments", response_model=CustomerSegmentsOut)
def get_customer_segments(
    current_user: StaffPortalUser,
    db: Session = Depends(get_db)
):
    """
    Retrieve counts of customers broken down by various segments 
    (active, inactive, new, premium, at-risk, etc.).
    Requires Admin or Staff access.
    """
    return service.get_customer_segments_count(db)


@router.get("/duplicates", response_model=list[DuplicateCustomerCandidateOut])
def list_duplicate_customers(
    _: StaffPortalUser,
    status: str | None = Query(default=None, description="pending, confirmed, dismissed, or merged"),
    db: Session = Depends(get_db),
) -> list[DuplicateCustomerCandidateOut]:
    return service.list_duplicate_customers(db, review_status=status)


@router.post("/duplicates/detect", response_model=list[DuplicateCustomerCandidateOut])
def detect_duplicate_customers(
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> list[DuplicateCustomerCandidateOut]:
    return service.detect_duplicate_customers(db)


@router.patch("/duplicates/{review_id}", response_model=DuplicateCustomerCandidateOut)
def review_duplicate_customer(
    review_id: str,
    payload: DuplicateCustomerReviewIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> DuplicateCustomerCandidateOut:
    return service.review_duplicate_customer(
        db,
        review_id,
        status_value=payload.status,
        reviewer_id=current_user.id,
    )


@router.post("/duplicates/{review_id}/review", response_model=DuplicateCustomerCandidateOut)
def review_duplicate_customer_action(
    review_id: str,
    payload: DuplicateCustomerReviewIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> DuplicateCustomerCandidateOut:
    return service.review_duplicate_customer(
        db,
        review_id,
        status_value=payload.status,
        reviewer_id=current_user.id,
    )


@router.post("/merge", response_model=CustomerMergeOut)
def merge_customers(
    payload: CustomerMergeIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> CustomerMergeOut:
    source_id = payload.sourceCustomerId or payload.mergedCustomerId or payload.duplicateCustomerId
    target_id = payload.targetCustomerId or payload.survivingCustomerId or payload.keepCustomerId
    if not source_id or not target_id:
        raise HTTPException(
            status_code=422,
            detail="sourceCustomerId and targetCustomerId are required",
        )
    return service.merge_customers(
        db,
        source_customer_id=source_id,
        target_customer_id=target_id,
        actor_id=current_user.id,
    )


@router.get("", response_model=PaginatedCustomersOut)
def get_customers(
    current_user: StaffPortalUser,
    q: str | None = Query(default=None, description="Search query matching name, email or phone"),
    segment: str | None = Query(
        default="all",
        description="Filter segment: all, active, inactive, verified, unverified, has_vehicle, no_vehicle",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    size: int = Query(default=20, ge=1, description="Page size"),
    db: Session = Depends(get_db),
) -> PaginatedCustomersOut:
    return service.list_customers(db, q=q, segment=segment, page=page, size=size)


@router.get("/{customer_id}", response_model=CustomerProfileOut)
def get_customer_profile(
    customer_id: str,
    current_user: StaffPortalUser,  # Only admin/staff can access customer profiles and CRM notes
    db: Session = Depends(get_db),
) -> CustomerProfileOut:
    return service.get_customer_profile(db, customer_id=customer_id)


@router.get("/{customer_id}/vehicles", response_model=CustomerVehiclesOut)
def get_customer_vehicles(
    customer_id: str,
    current_user: StaffPortalUser,  # Only admin/staff can access vehicle + service history data
    db: Session = Depends(get_db),
) -> CustomerVehiclesOut:
    return service.get_customer_vehicles(db, customer_id=customer_id)


@router.get("/{customer_id}/timeline", response_model=CustomerTimelineOut)
def get_customer_timeline(
    customer_id: str,
    current_user: CurrentAdmin,  # ONLY ADMIN is allowed for this endpoint as requested
    db: Session = Depends(get_db),
) -> CustomerTimelineOut:
    return service.get_customer_timeline(db, customer_id=customer_id)


@router.post("/{customer_id}/notes", response_model=CustomerNoteOut, status_code=201)
def create_customer_note(
    customer_id: str,
    payload: CustomerNoteCreate,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> CustomerNoteOut:
    return service.create_customer_note(
        db, customer_id=customer_id, author_id=current_user.id, body=payload.body
    )


@router.get("/{customer_id}/notes", response_model=list[CustomerNoteOut])
def get_customer_notes(
    customer_id: str,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> list[CustomerNoteOut]:
    return service.get_customer_notes(db, customer_id=customer_id)


@router.patch("/{customer_id}/notes/{note_id}", response_model=CustomerNoteOut)
def update_customer_note_path(
    customer_id: str,
    note_id: str,
    payload: CustomerNoteCreate,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> CustomerNoteOut:
    return service.update_customer_note(
        db,
        customer_id=customer_id,
        note_id=note_id,
        user_id=current_user.id,
        body=payload.body,
    )


@router.delete("/{customer_id}/notes/{note_id}")
def delete_customer_note(
    customer_id: str,
    note_id: str,
    current_user: CurrentAdmin,  # STRICTLY ADMIN ONLY
    db: Session = Depends(get_db),
):
    return service.delete_customer_note(db, customer_id=customer_id, note_id=note_id)



