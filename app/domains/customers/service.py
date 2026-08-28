import math
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status
from sqlalchemy import or_, func, case, and_
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.customers.schemas import (
    CustomerActivityItem,
    CustomerContact,
    CustomerDetailOut,
    CustomerNoteCreate,
    CustomerNoteOut,
    CustomerPreferences,
    CustomerProfileOut,
    CustomerTimelineOut,
    CustomerVehicleOut,
    CustomerVehiclesOut,
    PaginatedCustomersOut,
    ServiceHistoryItemOut,
    CustomerSegmentsOut,
)
from app.domains.customers.models import CustomerNote, OwnedVehicle
from app.domains.customers.models import CustomerDuplicateReview, WatchlistItem
from app.domains.audit.models import AuditLog
from app.domains.inventory.models import VehicleAvailabilitySubscription
from app.domains.leads.models import Lead
from app.domains.notifications.models import UserNotification
from app.domains.ownership.models import VehicleOwnershipRequest
from app.domains.sales.models import Quotation, Reservation, TestDriveBooking, TradeInRequest
from app.domains.service.models import ServiceAppointment, ServiceHistoryItem
from app.domains.shared.enums import AuditAction, DuplicateReviewStatus
from app.domains.support.models import SupportTicket
from app.domains.users.models import User, UserRole
from app.domains.warranty.models import RecallVehicle, WarrantyCertificate, WarrantyClaim


def list_customers(
    db: Session,
    q: str | None = None,
    segment: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedCustomersOut:
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be 1 or greater.",
        )
    if size < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page size must be 1 or greater.",
        )

    # Base query filters only customers
    query = db.query(User).filter(User.role == UserRole.customer)

    # Apply search query
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.email.ilike(search_term),
                User.phone_normalized.ilike(search_term),
                User.phone_display.ilike(search_term),
            )
        )

    # Apply segment filter
    if segment and segment != "all":
        segment = segment.strip().lower()
        if segment == "active":
            query = query.filter(User.is_active == True)
        elif segment == "inactive":
            query = query.filter(User.is_active == False)
        elif segment == "verified":
            query = query.filter(User.is_verified == True)
        elif segment == "unverified":
            query = query.filter(User.is_verified == False)
        elif segment == "has_vehicle":
            query = query.filter(User.owned_vehicles.any())
        elif segment == "no_vehicle":
            query = query.filter(~User.owned_vehicles.any())
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid segment filter '{segment}'. Valid options: all, active, inactive, verified, unverified, has_vehicle, no_vehicle.",
            )

    # Get total count before pagination
    total = query.count()

    # Apply offset and limit.
    # Eager-load every relationship that CustomerDetailOut.from_user walks so the
    # serialization below issues a fixed number of queries instead of N+1 per row.
    offset = (page - 1) * size
    users = (
        query.options(
            selectinload(User.owned_vehicles),
            selectinload(User.crm_notes).joinedload(CustomerNote.author),
            selectinload(User.leads),
            selectinload(User.service_appointments),
            selectinload(User.support_tickets),
        )
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(size)
        .all()
    )

    # Calculate total pages
    pages = math.ceil(total / size) if total > 0 else 0

    # Build output detail list
    items = [CustomerDetailOut.from_user(u) for u in users]

    return PaginatedCustomersOut(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def get_customer_profile(db: Session, customer_id: str) -> CustomerProfileOut:
    user = db.query(User).filter(User.id == customer_id, User.role == UserRole.customer).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # 1. Contact Info
    contact = CustomerContact(
        id=user.id,
        firstName=user.first_name,
        lastName=user.last_name,
        email=user.email,
        phone=user.phone_display,
        city=user.city,
        state=user.state,
        avatar=user.avatar_url,
        isActive=user.is_active,
        isVerified=user.is_verified,
        createdAt=user.created_at,
        updatedAt=user.updated_at,
    )

    # 2. Preferences
    prefs_dict = user.preferences or {}
    preferences = CustomerPreferences(
        pushEnabled=prefs_dict.get("push_enabled", True),
        smsEnabled=prefs_dict.get("sms_enabled", True),
        emailEnabled=prefs_dict.get("email_enabled", True),
        marketingOptIn=prefs_dict.get("marketing_opt_in", False),
    )

    # 3. Activity Timeline
    activities = []

    # CRM Notes
    for n in getattr(user, "crm_notes", []):
        author_name = "System"
        if n.author:
            author_name = f"{n.author.first_name} {n.author.last_name}".strip()
        activities.append(
            CustomerActivityItem(
                id=n.id,
                type="note",
                title="Internal CRM Note Added",
                description=f"Note by {author_name}: {n.body}",
                status=None,
                timestamp=n.created_at,
            )
        )

    # Sales Leads
    for l in getattr(user, "leads", []):
        activities.append(
            CustomerActivityItem(
                id=l.id,
                type="lead",
                title="Sales Lead Created",
                description=f"Interested in {l.interested_model} via {l.source}",
                status=l.status.value if hasattr(l.status, "value") else str(l.status),
                timestamp=l.created_at,
            )
        )

    # Service Appointments
    for a in getattr(user, "service_appointments", []):
        activities.append(
            CustomerActivityItem(
                id=a.id,
                type="appointment",
                title="Service Appointment Booked",
                description=f"Service Type: {a.service_type.value if hasattr(a.service_type, 'value') else str(a.service_type)} - {a.issue_description}",
                status=a.status.value if hasattr(a.status, "value") else str(a.status),
                timestamp=a.created_at,
            )
        )

    # Support Tickets
    for t in getattr(user, "support_tickets", []):
        activities.append(
            CustomerActivityItem(
                id=t.id,
                type="ticket",
                title="Support Ticket Opened",
                description=f"Ticket #{t.ticket_number}: {t.subject}",
                status=t.status.value if hasattr(t.status, "value") else str(t.status),
                timestamp=t.created_at,
            )
        )

    # Test Drive Bookings
    for tb in getattr(user, "test_drive_bookings", []):
        activities.append(
            CustomerActivityItem(
                id=tb.id,
                type="test_drive",
                title="Test Drive Booked",
                description=f"Booked for {tb.scheduled_at.strftime('%Y-%m-%d %H:%M')}",
                status=tb.status.value if hasattr(tb.status, "value") else str(tb.status),
                timestamp=tb.created_at,
            )
        )

    # Quotations
    for q in getattr(user, "quotations", []):
        activities.append(
            CustomerActivityItem(
                id=q.id,
                type="quotation",
                title="Quotation Requested",
                description=f"Quotation prepared for amount: {q.total}",
                status=q.status.value if hasattr(q.status, "value") else str(q.status),
                timestamp=q.created_at,
            )
        )

    # Reservations
    for r in getattr(user, "reservations", []):
        activities.append(
            CustomerActivityItem(
                id=r.id,
                type="reservation",
                title="Vehicle Reservation Made",
                description=f"Deposit: {r.deposit_amount}",
                status=r.status.value if hasattr(r.status, "value") else str(r.status),
                timestamp=r.created_at,
            )
        )

    # Trade In Requests
    for tr in getattr(user, "trade_in_requests", []):
        activities.append(
            CustomerActivityItem(
                id=tr.id,
                type="trade_in",
                title="Trade-in Requested",
                description=f"Vehicle: {tr.year} {tr.make} {tr.model} ({tr.mileage} miles)",
                status=tr.status.value if hasattr(tr.status, "value") else str(tr.status),
                timestamp=tr.created_at,
            )
        )

    # Warranty Claims
    for wc in getattr(user, "warranty_claims", []):
        activities.append(
            CustomerActivityItem(
                id=wc.id,
                type="warranty_claim",
                title="Warranty Claim Filed",
                description=f"Claim Type: {wc.claim_type} - {wc.description}",
                status=wc.status.value if hasattr(wc.status, "value") else str(wc.status),
                timestamp=wc.created_at,
            )
        )

    # Owned Vehicles
    for ov in getattr(user, "owned_vehicles", []):
        ts = ov.purchase_date if ov.purchase_date else ov.created_at if hasattr(ov, "created_at") else datetime.min.replace(tzinfo=timezone.utc)
        activities.append(
            CustomerActivityItem(
                id=ov.id,
                type="vehicle",
                title="Owned Vehicle Registered",
                description=f"Vehicle: {ov.year} {ov.make} {ov.model} (VIN: {ov.vin})",
                status=None,
                timestamp=ts,
            )
        )

    # Sort activities chronologically (newest first)
    activities.sort(key=lambda x: x.timestamp, reverse=True)

    return CustomerProfileOut(
        contact=contact,
        preferences=preferences,
        activity=activities,
    )


def get_customer_vehicles(db: Session, customer_id: str) -> CustomerVehiclesOut:
    """
    Return all owned vehicles for a customer together with their full service history
    (embedded inline per vehicle, newest first).
    """
    # Validate the customer exists and is actually a customer role
    user = db.query(User).filter(User.id == customer_id, User.role == UserRole.customer).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    vehicles_out: list[CustomerVehicleOut] = []

    for ov in getattr(user, "owned_vehicles", []):
        # Build service history items sorted newest first
        history: list[ServiceHistoryItemOut] = [
            ServiceHistoryItemOut(
                id=sh.id,
                serviceType=sh.service_type,
                performedAt=sh.performed_at,
                mileage=sh.mileage,
                description=sh.description,
                cost=float(sh.cost),
                appointmentId=sh.appointment_id,
            )
            for sh in sorted(
                getattr(ov, "service_history", []),
                key=lambda x: x.performed_at,
                reverse=True,
            )
        ]

        vehicles_out.append(
            CustomerVehicleOut(
                id=ov.id,
                vin=ov.vin,
                make=ov.make,
                model=ov.model,
                trim=ov.trim,
                year=ov.year,
                color=ov.color,
                colorHex=ov.color_hex,
                mileage=ov.mileage,
                registrationNumber=ov.registration_number,
                purchaseDate=ov.purchase_date,
                imageUrl=ov.image_url,
                isPrimary=ov.is_primary,
                nextServiceDue=ov.next_service_due,
                nextServiceMileage=ov.next_service_mileage,
                createdAt=ov.created_at,
                serviceHistory=history,
            )
        )

    return CustomerVehiclesOut(
        customerId=customer_id,
        vehicles=vehicles_out,
        totalVehicles=len(vehicles_out),
    )


def get_customer_timeline(db: Session, customer_id: str) -> CustomerTimelineOut:
    """
    Retrieve customer activity timeline containing only Leads, Support Tickets, and Service Appointments.
    Sorted chronologically, newest first.
    """
    user = db.query(User).filter(User.id == customer_id, User.role == UserRole.customer).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    timeline_items = []

    # 1. Sales Leads
    for l in getattr(user, "leads", []):
        timeline_items.append(
            CustomerActivityItem(
                id=l.id,
                type="lead",
                title="Sales Lead Created",
                description=f"Interested in {l.interested_model} via {l.source}",
                status=l.status.value if hasattr(l.status, "value") else str(l.status),
                timestamp=l.created_at,
            )
        )

    # 2. Support Tickets
    for t in getattr(user, "support_tickets", []):
        timeline_items.append(
            CustomerActivityItem(
                id=t.id,
                type="ticket",
                title="Support Ticket Opened",
                description=f"Ticket #{t.ticket_number}: {t.subject}",
                status=t.status.value if hasattr(t.status, "value") else str(t.status),
                timestamp=t.created_at,
            )
        )

    # 3. Service Appointments
    for a in getattr(user, "service_appointments", []):
        timeline_items.append(
            CustomerActivityItem(
                id=a.id,
                type="appointment",
                title="Service Appointment Booked",
                description=f"Service Type: {a.service_type.value if hasattr(a.service_type, 'value') else str(a.service_type)} - {a.issue_description}",
                status=a.status.value if hasattr(a.status, "value") else str(a.status),
                timestamp=a.created_at,
            )
        )

    # Sort chronologically (newest first)
    timeline_items.sort(key=lambda x: x.timestamp, reverse=True)

    return CustomerTimelineOut(
        customerId=customer_id,
        timeline=timeline_items,
        totalItems=len(timeline_items),
    )


def map_note_to_out(note: CustomerNote) -> CustomerNoteOut:
    author_name = "System"
    if note.author:
        author_name = f"{note.author.first_name} {note.author.last_name}".strip()
    return CustomerNoteOut(
        id=note.id,
        customerId=note.customer_id,
        authorId=note.author_id,
        authorName=author_name,
        body=note.body,
        createdAt=note.created_at,
        updatedAt=note.updated_at,
    )


def _get_customer_or_404(db: Session, customer_id: str) -> User:
    """Fetch a customer by ID, raising 404 on not found or invalid UUID format."""
    try:
        customer = db.get(User, customer_id)
    except DataError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )
    return customer


def create_customer_note(
    db: Session, customer_id: str, author_id: str, body: str
) -> CustomerNoteOut:
    _get_customer_or_404(db, customer_id)

    note = CustomerNote(
        customer_id=customer_id,
        author_id=author_id,
        body=body,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return map_note_to_out(note)


def get_customer_notes(db: Session, customer_id: str) -> list[CustomerNoteOut]:
    _get_customer_or_404(db, customer_id)

    notes = (
        db.query(CustomerNote)
        .filter(CustomerNote.customer_id == customer_id)
        .order_by(CustomerNote.created_at.desc())
        .all()
    )
    return [map_note_to_out(n) for n in notes]


def update_customer_note(
    db: Session, customer_id: str, note_id: str, user_id: str, body: str
) -> CustomerNoteOut:
    _get_customer_or_404(db, customer_id)

    try:
        note = (
            db.query(CustomerNote)
            .filter(CustomerNote.id == note_id, CustomerNote.customer_id == customer_id)
            .first()
        )
    except DataError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )

    if note.author_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit notes that you authored",
        )

    note.body = body
    db.commit()
    db.refresh(note)
    return map_note_to_out(note)


def delete_customer_note(db: Session, customer_id: str, note_id: str) -> dict:
    _get_customer_or_404(db, customer_id)

    try:
        note = (
            db.query(CustomerNote)
            .filter(CustomerNote.id == note_id, CustomerNote.customer_id == customer_id)
            .first()
        )
    except DataError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )

    db.delete(note)
    db.commit()
    return {"detail": "Note deleted successfully"}


def get_customer_segments_count(db: Session) -> CustomerSegmentsOut:
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    # Subquery to get vehicle count per customer
    vehicle_counts = (
        db.query(
            OwnedVehicle.user_id,
            func.count(OwnedVehicle.id).label('vehicle_count')
        )
        .group_by(OwnedVehicle.user_id)
        .subquery()
    )
    
    # Aggregate all counts in a single query
    result = db.query(
        func.count(User.id).label("total"),
        func.count(case((User.is_active == True, 1))).label("active"),
        func.count(case((User.is_active == False, 1))).label("inactive"),
        func.count(case((User.is_verified == True, 1))).label("verified"),
        func.count(case((User.is_verified == False, 1))).label("unverified"),
        func.count(case((User.created_at >= thirty_days_ago, 1))).label("new"),
        func.count(case((vehicle_counts.c.vehicle_count > 0, 1))).label("has_vehicle"),
        func.count(case((or_(vehicle_counts.c.vehicle_count == None, vehicle_counts.c.vehicle_count == 0), 1))).label("no_vehicle"),
        func.count(case((vehicle_counts.c.vehicle_count >= 2, 1))).label("premium"),
        func.count(
            case((
                or_(
                    User.is_active == False,
                    and_(
                        or_(vehicle_counts.c.vehicle_count == None, vehicle_counts.c.vehicle_count == 0),
                        User.is_verified == False
                    )
                ), 1
            ))
        ).label("at_risk"),
    ).outerjoin(vehicle_counts, User.id == vehicle_counts.c.user_id).filter(User.role == UserRole.customer).first()
    
    return CustomerSegmentsOut(
        total=result.total or 0,
        active=result.active or 0,
        inactive=result.inactive or 0,
        verified=result.verified or 0,
        unverified=result.unverified or 0,
        hasVehicle=result.has_vehicle or 0,
        noVehicle=result.no_vehicle or 0,
        new=result.new or 0,
        premium=result.premium or 0,
        atRisk=result.at_risk or 0,
    )


# --------------------------------------------------------------------------- #
# Duplicate detection and merge                                               #
# --------------------------------------------------------------------------- #

def _contact_from_user(user: User) -> CustomerContact:
    return CustomerContact(
        id=user.id,
        firstName=user.first_name,
        lastName=user.last_name,
        email=user.email,
        phone=user.phone_display,
        city=user.city,
        state=user.state,
        avatar=user.avatar_url,
        isActive=user.is_active,
        isVerified=user.is_verified,
        createdAt=user.created_at,
        updatedAt=user.updated_at,
    )


def _duplicate_review_to_out(review: CustomerDuplicateReview) -> dict:
    return {
        "id": review.id,
        "customerId": review.customer_id,
        "duplicateCustomerId": review.duplicate_customer_id,
        "customer": _contact_from_user(review.customer),
        "duplicateCustomer": _contact_from_user(review.duplicate_customer),
        "matchFields": list(review.match_fields or []),
        "confidence": review.confidence,
        "status": review.status.value,
        "reviewedById": review.reviewed_by_id,
        "reviewedAt": review.reviewed_at,
        "mergedIntoId": review.merged_into_id,
        "createdAt": review.created_at,
    }


def _duplicate_match(left: User, right: User) -> tuple[list[str], int]:
    fields: list[str] = []
    if left.email and right.email and left.email.strip().lower() == right.email.strip().lower():
        fields.append("email")
    if left.phone_normalized and left.phone_normalized == right.phone_normalized:
        fields.append("phone")
    same_name = (
        left.first_name.strip().casefold() == right.first_name.strip().casefold()
        and left.last_name.strip().casefold() == right.last_name.strip().casefold()
    )
    if same_name:
        fields.append("name")
        if left.city.strip().casefold() == right.city.strip().casefold() and left.state.strip().casefold() == right.state.strip().casefold():
            fields.append("location")

    confidence = 0
    if "email" in fields or "phone" in fields:
        confidence = 100
    elif "name" in fields and "location" in fields:
        confidence = 85
    elif "name" in fields:
        confidence = 70
    return fields, confidence


def detect_duplicate_customers(
    db: Session,
    *,
    review_status: str | None = None,
) -> list:
    """Find likely duplicate customer pairs and persist them for review."""
    customers = (
        db.query(User)
        .filter(User.role == UserRole.customer)
        .order_by(User.id.asc())
        .all()
    )
    found: list[CustomerDuplicateReview] = []
    for index, left in enumerate(customers):
        for right in customers[index + 1:]:
            match_fields, confidence = _duplicate_match(left, right)
            if not match_fields:
                continue
            review = (
                db.query(CustomerDuplicateReview)
                .filter(
                    CustomerDuplicateReview.customer_id == left.id,
                    CustomerDuplicateReview.duplicate_customer_id == right.id,
                )
                .one_or_none()
            )
            if review is None:
                review = CustomerDuplicateReview(
                    customer_id=left.id,
                    duplicate_customer_id=right.id,
                    match_fields=match_fields,
                    confidence=confidence,
                    status=DuplicateReviewStatus.pending,
                )
                db.add(review)
            elif review.status == DuplicateReviewStatus.pending:
                review.match_fields = match_fields
                review.confidence = confidence
            found.append(review)

    db.commit()
    if review_status:
        try:
            wanted_status = DuplicateReviewStatus(review_status.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid duplicate review status") from exc
        found = [review for review in found if review.status == wanted_status]
    return [_duplicate_review_to_out(review) for review in found]


def list_duplicate_customers(db: Session, *, review_status: str | None = None) -> list:
    # Detection is deliberately run on every list request so new duplicates
    # are reviewable without a separate background worker.
    return detect_duplicate_customers(db, review_status=review_status)


def review_duplicate_customer(
    db: Session,
    review_id: str,
    *,
    status_value: str,
    reviewer_id: str,
) -> dict:
    review = db.get(CustomerDuplicateReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Duplicate review not found")
    try:
        next_status = DuplicateReviewStatus(status_value.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid duplicate review status") from exc
    if next_status == DuplicateReviewStatus.merged:
        raise HTTPException(status_code=400, detail="Use the merge endpoint to mark a duplicate as merged")

    review.status = next_status
    review.reviewed_by_id = reviewer_id
    review.reviewed_at = datetime.now(timezone.utc)
    audit = AuditLog(
        actor_id=reviewer_id,
        action=AuditAction.review,
        entity_type="customer_duplicate_review",
        entity_id=review.id,
        changes={"status": next_status.value, "customerId": review.customer_id, "duplicateCustomerId": review.duplicate_customer_id},
    )
    db.add(audit)
    db.commit()
    db.refresh(review)
    return _duplicate_review_to_out(review)


def merge_customers(
    db: Session,
    *,
    source_customer_id: str,
    target_customer_id: str,
    actor_id: str,
) -> dict:
    """Move all customer-owned records to target in one transaction."""
    if source_customer_id == target_customer_id:
        raise HTTPException(status_code=400, detail="Source and target customers must be different")

    source = db.get(User, source_customer_id)
    target = db.get(User, target_customer_id)
    if not source or source.role != UserRole.customer or not target or target.role != UserRole.customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    reassigned: dict[str, int] = {}

    def move(model, column, key: str) -> None:
        count = (
            db.query(model)
            .filter(column == source.id)
            .update({column: target.id}, synchronize_session=False)
        )
        reassigned[key] = count

    try:
        move(OwnedVehicle, OwnedVehicle.user_id, "ownedVehicles")
        move(CustomerNote, CustomerNote.customer_id, "crmNotes")
        move(WatchlistItem, WatchlistItem.user_id, "watchlistItems")
        move(Lead, Lead.customer_id, "leads")
        move(TestDriveBooking, TestDriveBooking.user_id, "testDrives")
        move(Quotation, Quotation.user_id, "quotations")
        move(Reservation, Reservation.user_id, "reservations")
        move(TradeInRequest, TradeInRequest.user_id, "tradeIns")
        move(ServiceAppointment, ServiceAppointment.user_id, "serviceAppointments")
        move(ServiceHistoryItem, ServiceHistoryItem.user_id, "serviceHistory")
        move(WarrantyCertificate, WarrantyCertificate.user_id, "warrantyCertificates")
        move(WarrantyClaim, WarrantyClaim.user_id, "warrantyClaims")
        move(RecallVehicle, RecallVehicle.user_id, "recallVehicles")
        move(SupportTicket, SupportTicket.user_id, "supportTickets")
        move(UserNotification, UserNotification.user_id, "notifications")
        move(VehicleOwnershipRequest, VehicleOwnershipRequest.user_id, "ownershipRequests")

        # The pair is unique per user and vehicle, so coalesce duplicate
        # Notify Me subscriptions instead of violating the unique constraint.
        source_subscriptions = (
            db.query(VehicleAvailabilitySubscription)
            .filter(VehicleAvailabilitySubscription.user_id == source.id)
            .all()
        )
        moved_subscriptions = 0
        for subscription in source_subscriptions:
            existing = (
                db.query(VehicleAvailabilitySubscription)
                .filter(
                    VehicleAvailabilitySubscription.user_id == target.id,
                    VehicleAvailabilitySubscription.vehicle_id == subscription.vehicle_id,
                )
                .one_or_none()
            )
            if existing:
                if subscription.is_active and not existing.is_active:
                    existing.is_active = True
                    existing.notified_at = None
                db.delete(subscription)
            else:
                subscription.user_id = target.id
                moved_subscriptions += 1
        reassigned["availabilitySubscriptions"] = moved_subscriptions

        source.is_active = False
        source.preferences = {**(source.preferences or {}), "merged_into": target.id}

        audit = AuditLog(
            actor_id=actor_id,
            action=AuditAction.merge,
            entity_type="customer",
            entity_id=target.id,
            changes={
                "sourceCustomerId": source.id,
                "targetCustomerId": target.id,
                "reassigned": reassigned,
            },
        )
        db.add(audit)

        db.query(CustomerDuplicateReview).filter(
            CustomerDuplicateReview.customer_id == source.id,
            CustomerDuplicateReview.duplicate_customer_id == target.id,
        ).update(
            {
                CustomerDuplicateReview.status: DuplicateReviewStatus.merged,
                CustomerDuplicateReview.reviewed_by_id: actor_id,
                CustomerDuplicateReview.reviewed_at: datetime.now(timezone.utc),
                CustomerDuplicateReview.merged_into_id: target.id,
            },
            synchronize_session=False,
        )
        db.query(CustomerDuplicateReview).filter(
            CustomerDuplicateReview.customer_id == target.id,
            CustomerDuplicateReview.duplicate_customer_id == source.id,
        ).update(
            {
                CustomerDuplicateReview.status: DuplicateReviewStatus.merged,
                CustomerDuplicateReview.reviewed_by_id: actor_id,
                CustomerDuplicateReview.reviewed_at: datetime.now(timezone.utc),
                CustomerDuplicateReview.merged_into_id: target.id,
            },
            synchronize_session=False,
        )
        db.flush()
        audit_id = audit.id
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "survivingCustomerId": target.id,
        "mergedCustomerId": source.id,
        "reassigned": reassigned,
        "auditId": audit_id,
    }
