from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.domains.branches.models import Branch
from app.domains.inventory.models import Vehicle
from app.domains.inventory import service as inventory_service
from app.domains.leads.models import Lead
from app.domains.notifications import catalog
from app.domains.notifications.notify import safe_notify
from app.domains.sales.models import Quotation, QuotationLineItem, Reservation, TestDriveBooking, TradeInRequest
from app.domains.sales.schemas import (
    QuotationOut,
    QuotationRequestIn,
    ReservationCreateIn,
    ReservationOut,
    TestDriveCreateIn,
    TestDriveStatusActionIn,
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
        # `lead` is eager-loaded with the rest: the payload now reports the
        # lead's live stage, and without this a customer with 50 bookings
        # would issue 50 extra queries to render one list.
        .options(
            joinedload(TestDriveBooking.vehicle),
            joinedload(TestDriveBooking.branch),
            joinedload(TestDriveBooking.lead),
        )
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

    # BOOKING A TEST DRIVE SENT NOTHING AT ALL.
    #
    # The only test-drive event in the catalog was `TEST_DRIVE_CONFIRMED`, and
    # nothing fires it because there is no staff endpoint to confirm a test
    # drive — so a customer chose a slot, submitted, and heard nothing, from
    # anywhere, ever. This acknowledges the booking they actually made.
    #
    # "Requested", not "confirmed": the row is created as `requested` and no
    # human has seen it yet. After the commit, so a notification failure
    # cannot cost the customer the booking.
    safe_notify(
        db,
        user=user,
        event=catalog.TEST_DRIVE_REQUESTED,
        context={
            "vehicle_label": _vehicle_label(vehicle),
            "when": scheduled.strftime("%d %b at %H:%M"),
            "branch": branch.name,
        },
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

    # THE APP PROMISES THIS AND NOTHING DELIVERED IT.
    #
    # The success sheet says "A formal quotation ... will be sent to your email
    # and appear in Support shortly", and the row was written with
    # `status=sent` — but nothing was ever sent. There was no failing worker
    # and no queue to repair: the call simply did not exist.
    #
    # `sales.quotation_issued` was already in the notification catalog, with
    # in-app, push and email channels declared, and had never been fired by
    # anything. So this is the missing call, not a new mechanism.
    #
    # `safe_notify` because a quote that was created must stand even if
    # Postmark is down — a customer would rather have a quote and no email
    # than a 500 and neither.
    #
    # AND IT HAS TO CONTAIN THE QUOTE. The first version of this call sent the
    # catalog body and nothing else — "We've prepared your quote for the 2024
    # Corolla. It's valid until 21 September 2026." True, and containing no
    # figures. A customer who opened it still had no quotation, which is the
    # same complaint one step later. The email now carries the breakdown, the
    # total and the reference, so it IS the formal quotation the app promised.
    vehicle_label = f"{vehicle.year} {vehicle.make} {vehicle.model}".strip()
    # Date only: a customer needs the day it lapses, not a timestamp.
    valid_until_label = valid_until.strftime("%d %B %Y")
    quote_email = _quotation_email(
        user=user,
        quotation=loaded,
        vehicle_label=vehicle_label,
        valid_until_label=valid_until_label,
    )

    safe_notify(
        db,
        user=user,
        event=catalog.QUOTATION_ISSUED,
        context={
            "vehicle_label": vehicle_label,
            "valid_until": valid_until_label,
        },
        email_text=quote_email["text"],
        email_html=quote_email["html"],
    )
    return QuotationOut.from_model(loaded)


def _quotation_reference(quotation_id: str) -> str:
    """A short, quotable handle for the customer and the sales desk.

    Derived from the row id rather than a counter so it needs no extra column
    and cannot collide. Uppercased hex reads over the phone far better than a
    full UUID does.
    """
    return f"Q-{quotation_id.replace('-', '')[:8].upper()}"


def _quotation_email(
    *,
    user: User,
    quotation: Quotation,
    vehicle_label: str,
    valid_until_label: str,
) -> dict[str, str]:
    """Render the quotation as an actual document, both plain text and HTML."""
    from app.services.email_templates import (  # noqa: PLC0415 — avoids an import cycle
        build_quotation_html,
        build_quotation_plain_text,
    )

    items = [(li.description, li.amount) for li in sorted(quotation.line_items, key=lambda li: li.sort_order)]
    # A quote with no line items would render an empty table. Falling back to
    # the vehicle itself keeps the document meaningful rather than blank.
    if not items:
        items = [(vehicle_label, quotation.total)]

    fields = {
        "customer_name": (user.first_name or "").strip(),
        "vehicle_label": vehicle_label,
        "line_items": items,
        "total": quotation.total,
        "valid_until": valid_until_label,
        "reference": _quotation_reference(quotation.id),
    }
    return {
        "text": build_quotation_plain_text(**fields),
        "html": build_quotation_html(**fields),
    }


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
    # Through the one door, so Notify Me subscribers hear about it too.
    # Not strict: a mail outage must not fail a customer's reservation.
    inventory_service.set_availability(
        db, vehicle, AvailabilityStatus.reserved, strict_notify=False
    )
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


#: Which transitions are legal. A completed or cancelled booking is finished;
#: reopening one would resurrect a slot the branch has already given away.
_TEST_DRIVE_TERMINAL = (TestDriveStatus.completed, TestDriveStatus.cancelled)


def _load_test_drive(db: Session, booking_id: str) -> TestDriveBooking:
    booking = (
        db.query(TestDriveBooking)
        .options(joinedload(TestDriveBooking.vehicle), joinedload(TestDriveBooking.branch))
        .filter(TestDriveBooking.id == booking_id)
        .one_or_none()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test drive not found")
    return booking


def _test_drive_context(booking: TestDriveBooking) -> dict:
    return {
        "vehicle_label": _vehicle_label(booking.vehicle) if booking.vehicle else "your vehicle",
        "when": booking.scheduled_at.strftime("%d %b at %H:%M"),
        "branch": booking.branch.name if booking.branch else "your branch",
    }


def change_test_drive_status(
    db: Session, booking_id: str, payload: TestDriveStatusActionIn
) -> TestDriveOut:
    """Staff confirm / cancel / complete a test drive.

    THIS DID NOT EXIST. There was no staff endpoint for test drives of any
    kind, so `status` stayed `requested` for the life of the booking and the
    customer's own screen had to fall back to the linked lead's stage to show
    anything at all. It is also why `TEST_DRIVE_CONFIRMED` and
    `TEST_DRIVE_CANCELLED` sat in the catalogue having never once been sent —
    the events were written, and nothing could reach them.
    """
    booking = _load_test_drive(db, booking_id)

    if booking.status in _TEST_DRIVE_TERMINAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This test drive is already {booking.status.value}.",
        )

    action = payload.action
    if action == "confirm":
        booking.status = TestDriveStatus.confirmed
    elif action == "cancel":
        booking.status = TestDriveStatus.cancelled
    else:
        booking.status = TestDriveStatus.completed

    db.commit()
    db.refresh(booking)
    booking = _load_test_drive(db, booking_id)

    # After the commit: the status change stands whether or not the customer
    # can be reached.
    if action == "confirm":
        safe_notify(
            db,
            user=booking.user,
            event=catalog.TEST_DRIVE_CONFIRMED,
            context=_test_drive_context(booking),
        )
    elif action == "cancel":
        safe_notify(
            db,
            user=booking.user,
            event=catalog.TEST_DRIVE_CANCELLED,
            context={"vehicle_label": _test_drive_context(booking)["vehicle_label"]},
        )
    return TestDriveOut.from_model(booking)


def cancel_my_test_drive(db: Session, user: User, booking_id: str) -> TestDriveOut:
    """A customer calling off their own test drive.

    Service appointments have had customer cancel and reschedule since they
    were built; test drives had neither, so a customer who could no longer make
    it had no way to say so and the branch kept the slot held.
    """
    booking = _load_test_drive(db, booking_id)
    if booking.user_id != user.id:
        # 404 rather than 403: whether someone else's booking exists is not
        # this customer's business.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test drive not found")
    if booking.status in _TEST_DRIVE_TERMINAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This test drive is already {booking.status.value}.",
        )

    booking.status = TestDriveStatus.cancelled
    db.commit()
    booking = _load_test_drive(db, booking_id)

    # No notification back to the customer who just pressed cancel — they were
    # there. The branch learns from the booking list.
    return TestDriveOut.from_model(booking)
