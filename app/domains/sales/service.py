from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.domains.branches.models import Branch
from app.domains.inventory.models import Vehicle
from app.domains.leads.models import Lead
from app.domains.sales.models import TestDriveBooking
from app.domains.sales.schemas import TestDriveCreateIn, TestDriveOut
from app.domains.shared.enums import AvailabilityStatus, BranchType, LeadStatus, TestDriveStatus
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
