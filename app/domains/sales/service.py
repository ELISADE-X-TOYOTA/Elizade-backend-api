from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.domains.branches.models import Branch
from app.domains.inventory.models import Vehicle
from app.domains.leads.models import Lead
from app.domains.sales.models import Quotation, QuotationLineItem, Reservation, TestDriveBooking, TradeInRequest
from app.domains.sales.schemas import (
    QuotationOut,
    QuotationRequestIn,
    ReservationCreateIn,
    ReservationOut,
    TestDriveCreateIn,
    TestDriveOut,
    TradeInCreateIn,
    TradeInOut,
)
from app.domains.shared.enums import (
    AvailabilityStatus,
    BranchType,
    LeadStatus,
    QuotationStatus,
    ReservationStatus,
    TestDriveStatus,
    TradeInStatus,
)
from app.domains.users.models import User


def _vehicle_label(vehicle: Vehicle) -> str:
    return f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim}".strip()


def list_my_test_drives(db: Session, user_id: str) -> list[TestDriveOut]:
    rows = (
        db.query(TestDriveBooking)
        .options(joinedload(TestDriveBooking.vehicle), joinedload(TestDriveBooking.branch))
        .filter(TestDriveBooking.user_id == user_id)
        .order_by(TestDriveBooking.scheduled_at.desc())
        .limit(50)
        .all()
    )
    return [TestDriveOut.from_model(row) for row in rows]


def create_test_drive(db: Session, user: User, payload: TestDriveCreateIn) -> TestDriveOut:
    vehicle = db.get(Vehicle, payload.vehicle_id)
    if not vehicle or vehicle.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if vehicle.availability not in (AvailabilityStatus.available, AvailabilityStatus.reserved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vehicle is not available for test drive")

    branch = db.get(Branch, payload.branch_id)
    if not branch or not branch.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch not found")
    if branch.type == BranchType.service_centre:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a showroom branch")

    scheduled = payload.scheduled_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    if scheduled <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scheduled time must be in the future")

    price = vehicle.promotional_price if vehicle.promotional_price is not None else vehicle.price
    lead = Lead(
        customer_id=user.id,
        customer_name=f"{user.first_name} {user.last_name}".strip() or user.phone_display,
        email=user.email,
        phone=user.phone_display,
        source="Mobile app",
        status=LeadStatus.new,
        interested_model=_vehicle_label(vehicle),
        vehicle_id=vehicle.id,
        value=price,
        notes="Test drive requested via Elizade Connect mobile app.",
    )
    db.add(lead)
    db.flush()

    booking = TestDriveBooking(
        user_id=user.id,
        vehicle_id=vehicle.id,
        branch_id=branch.id,
        lead_id=lead.id,
        scheduled_at=scheduled,
        status=TestDriveStatus.requested,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    booking = (
        db.query(TestDriveBooking)
        .options(joinedload(TestDriveBooking.vehicle), joinedload(TestDriveBooking.branch))
        .filter(TestDriveBooking.id == booking.id)
        .one()
    )
    return TestDriveOut.from_model(booking)


def _get_available_vehicle(db: Session, vehicle_id: str) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if vehicle.availability not in (AvailabilityStatus.available, AvailabilityStatus.reserved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vehicle is not available")
    return vehicle


def _create_sales_lead(db: Session, user: User, vehicle: Vehicle, *, source: str, notes: str) -> Lead:
    price = vehicle.promotional_price if vehicle.promotional_price is not None else vehicle.price
    lead = Lead(
        customer_id=user.id,
        customer_name=f"{user.first_name} {user.last_name}".strip() or user.phone_display,
        email=user.email,
        phone=user.phone_display,
        source=source,
        status=LeadStatus.new,
        interested_model=_vehicle_label(vehicle),
        vehicle_id=vehicle.id,
        value=price,
        notes=notes,
    )
    db.add(lead)
    db.flush()
    return lead


def list_my_quotations(db: Session, user_id: str) -> list[QuotationOut]:
    rows = (
        db.query(Quotation)
        .options(joinedload(Quotation.vehicle), joinedload(Quotation.line_items))
        .filter(Quotation.user_id == user_id)
        .order_by(Quotation.created_at.desc())
        .limit(50)
        .all()
    )
    return [QuotationOut.from_model(r) for r in rows]


def request_quotation(db: Session, user: User, payload: QuotationRequestIn) -> QuotationOut:
    vehicle = _get_available_vehicle(db, payload.vehicle_id)
    lead = _create_sales_lead(
        db,
        user,
        vehicle,
        source="Mobile app",
        notes=payload.notes.strip() if payload.notes else "Quotation requested via Elizade Connect.",
    )
    base = vehicle.promotional_price if vehicle.promotional_price is not None else vehicle.price
    valid_until = datetime.now(timezone.utc) + timedelta(days=14)
    row = Quotation(
        user_id=user.id,
        vehicle_id=vehicle.id,
        lead_id=lead.id,
        base_price=base,
        accessories_total=Decimal("0"),
        discount=Decimal("0"),
        total=base,
        status=QuotationStatus.sent,
        valid_until=valid_until,
    )
    db.add(row)
    db.flush()
    db.add(
        QuotationLineItem(
            quotation_id=row.id,
            description=f"{vehicle.year} {vehicle.model} {vehicle.trim}",
            amount=base,
            sort_order=0,
        )
    )
    db.commit()
    loaded = (
        db.query(Quotation)
        .options(joinedload(Quotation.vehicle), joinedload(Quotation.line_items))
        .filter(Quotation.id == row.id)
        .one()
    )
    return QuotationOut.from_model(loaded)


def list_my_reservations(db: Session, user_id: str) -> list[ReservationOut]:
    rows = (
        db.query(Reservation)
        .options(joinedload(Reservation.vehicle))
        .filter(Reservation.user_id == user_id)
        .order_by(Reservation.created_at.desc())
        .limit(50)
        .all()
    )
    return [ReservationOut.from_model(r) for r in rows]


def create_reservation(db: Session, user: User, payload: ReservationCreateIn) -> ReservationOut:
    vehicle = _get_available_vehicle(db, payload.vehicle_id)
    existing = (
        db.query(Reservation)
        .filter(
            Reservation.vehicle_id == vehicle.id,
            Reservation.status.in_((ReservationStatus.pending, ReservationStatus.deposit_paid, ReservationStatus.confirmed)),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vehicle already has an active reservation")

    lead = _create_sales_lead(
        db,
        user,
        vehicle,
        source="Mobile app",
        notes="Vehicle reservation requested via Elizade Connect.",
    )
    deposit = Decimal(str(payload.deposit_amount or 0))
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    row = Reservation(
        user_id=user.id,
        vehicle_id=vehicle.id,
        lead_id=lead.id,
        status=ReservationStatus.pending,
        deposit_amount=deposit,
        expires_at=expires_at,
    )
    db.add(row)
    vehicle.availability = AvailabilityStatus.reserved
    db.commit()
    loaded = db.query(Reservation).options(joinedload(Reservation.vehicle)).filter(Reservation.id == row.id).one()
    return ReservationOut.from_model(loaded)


def list_my_trade_ins(db: Session, user_id: str) -> list[TradeInOut]:
    rows = (
        db.query(TradeInRequest)
        .filter(TradeInRequest.user_id == user_id)
        .order_by(TradeInRequest.created_at.desc())
        .limit(50)
        .all()
    )
    return [TradeInOut.from_model(r) for r in rows]


def submit_trade_in(db: Session, user: User, payload: TradeInCreateIn) -> TradeInOut:
    from app.domains.shared.documents import normalize_document_urls

    photo_urls = normalize_document_urls(payload.photo_urls)
    lead = Lead(
        customer_id=user.id,
        customer_name=f"{user.first_name} {user.last_name}".strip() or user.phone_display,
        email=user.email,
        phone=user.phone_display,
        source="Mobile app",
        status=LeadStatus.new,
        interested_model=f"{payload.year} {payload.make} {payload.model}",
        notes=f"Trade-in: {payload.condition_notes.strip()}",
    )
    db.add(lead)
    db.flush()
    row = TradeInRequest(
        user_id=user.id,
        lead_id=lead.id,
        make=payload.make.strip(),
        model=payload.model.strip(),
        year=payload.year,
        mileage=payload.mileage,
        condition_notes=payload.condition_notes.strip(),
        photo_urls=photo_urls,
        status=TradeInStatus.submitted,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return TradeInOut.from_model(row)
