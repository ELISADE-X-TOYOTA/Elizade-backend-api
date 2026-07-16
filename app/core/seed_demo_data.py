"""Seed branches, catalogue vehicles, CRM customers, and ops data for local demos."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random

from sqlalchemy.orm import Session

from app.domains.branches.models import Branch
from app.domains.customers.models import CustomerNote, OwnedVehicle
from app.domains.inventory.models import Vehicle, VehicleImage
from app.domains.notifications.models import BroadcastCampaign, NotificationRule
from app.domains.shared.enums import (
    AdditionalWorkStatus,
    AppointmentStatus,
    AvailabilityStatus,
    BranchType,
    BroadcastCampaignStatus,
    ClaimStatus,
    LeadStatus,
    RecallSeverity,
    ServiceJobStatus,
    ServiceType,
    SlaStatus,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    WarrantyCertificateStatus,
    WarrantyCertificateType,
)
from app.domains.support.models import SlaConfig, SupportTicket
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole
from app.domains.warranty.models import RecallCampaign, RecallVehicle, WarrantyCertificate, WarrantyClaim

_LEAD_SPECS: list[tuple] = [
    ("Chidi Eze", "08031234567", "chidi.eze@email.com", "Website", LeadStatus.new, "Camry XSE", Decimal("18500000")),
    ("Fatima Bello", "08042345678", "fatima.b@email.com", "Showroom walk-in", LeadStatus.contacted, "RAV4 Hybrid", Decimal("24500000")),
    ("Emeka Nwosu", "08053456789", None, "Test drive", LeadStatus.qualified, "Corolla", Decimal("12800000")),
    ("Amina Yusuf", "08064567890", "amina.y@email.com", "Referral", LeadStatus.proposal, "Highlander", Decimal("32000000")),
    ("Tunde Adeyemi", "08075678901", "tunde.a@email.com", "Phone inquiry", LeadStatus.negotiation, "Hilux", Decimal("27500000")),
    ("Grace Okoro", "08086789012", "grace.o@email.com", "Website", LeadStatus.won, "Camry", Decimal("19200000")),
    ("Ibrahim Musa", "08097890123", None, "Showroom walk-in", LeadStatus.lost, "Fortuner", Decimal("31000000")),
    ("Ngozi Okafor", "08108901234", "ngozi.o@email.com", "Social media", LeadStatus.new, "Yaris Cross", Decimal("15500000")),
]


def _seed_leads(db: Session, assignee_id: str | None) -> None:
    from app.domains.leads.models import Lead

    if db.query(Lead).count() >= len(_LEAD_SPECS):
        return

    vehicles = db.query(Vehicle).filter(Vehicle.deleted_at.is_(None)).limit(8).all()
    now = datetime.now(timezone.utc)

    for i, (name, phone, email, source, lead_status, model, value) in enumerate(_LEAD_SPECS):
        if db.query(Lead).filter(Lead.phone == phone, Lead.interested_model == model).one_or_none():
            continue
        vehicle = vehicles[i % len(vehicles)] if vehicles else None
        lead = Lead(
            customer_name=name,
            email=email,
            phone=phone,
            source=source,
            status=lead_status,
            interested_model=model,
            vehicle_id=vehicle.id if vehicle else None,
            assigned_agent_id=assignee_id,
            value=value,
            notes="Demo pipeline lead for Elizade Connect.",
        )
        if lead_status == LeadStatus.won:
            lead.won_at = now - timedelta(days=3)
        if lead_status == LeadStatus.lost:
            lead.lost_at = now - timedelta(days=5)
            lead.lost_reason = "Chose competitor offer"
        db.add(lead)

_CAR_IMAGE_POOL: list[str] = [
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQzGVzVg_2I0uBcIXbPHfbrnu_zMcCmkJBp0n8OB3al2w&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ3emKlXRIgpEufUk4Mt9uoIn-qnywLE6xud6L5BFZb5Q&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTNdhZDZdxnUn6HXoZNjid90Vf0i959TY9iYL4sBQkr7A&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTjglcsy8b8ReSpFb_8qnNMzi1LLF2k-HBZyvDSOqxCEg&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQKa-7w7jNoL-irPZQZFGZTVc34wuM6gZbd2bZua3j0ag&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRlzgyVHZ99X4Egasb6Y2avWJEXlNSC0cacJr2I5hDdgA&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTnEnmNXW4WoQUoWXiL_Q5mXC4dPDD5bZUUUg6_PKC5hw&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTG0AYvNme00ghOXHfbsMTxPzAAd9q9di5mGvlMF-PW6Q&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTiDJVGABoKldXIwzw6pjDaxT9uO2xCUBOpbSA2GQAVRw&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRX-_FmsHoM1uJFtS11VcoLfNgnce9Z1Eo5UeYB--VGzA&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTSgSiOHiqQRkKXB8DCeDMsiBpXa7hsF_WL7paRQJzB8g&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQxH4Zbw3B1UWEkzNW4DOmUyQJgYBDVkynhPVdOnQ4W6w&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR2GJvZkQnIzSXu771TMJT2HpqPs9S2LkCZoP7KoLuxzQ&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSNc7FkvwpE_ZXf9Q5KTxosBtJWtJ8LeXaX7GK92jkYMA&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ2u008SQNPT9Ux1JktTFYEOpQNC5LyaosPSXrp-65oSw&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRkAgif1oNjvYUqUaEn18DxsZXrqGCGeR2Y4dEqkmFmfg&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTR2h18adya8hReoah7JMw89tr_fKOevUGbu39yQbJQ_w&s",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSlzKG5-Im30q3n9bBTYPR5mRdxFfr3oRg4tikHFWNsNg&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSAF5B83wGoemPvh9d0JrV8rSPAokm-0pkkU-uHHcwprQ&s=10",
]

_DEMO_IMAGE = _CAR_IMAGE_POOL[0]

_UNRELIABLE_IMAGE_HOSTS = ("unsplash.com", "picsum.photos", "wikimedia.org", "upload.wikimedia.org")

_BRANCHES = [
    {
        "name": "Elizade Victoria Island",
        "type": BranchType.both,
        "city": "Lagos",
        "state": "Lagos",
        "address": "141 Ahmadu Bello Way, VI",
        "phone": "08012345678",
    },
    {
        "name": "Elizade Ikeja",
        "type": BranchType.both,
        "city": "Lagos",
        "state": "Lagos",
        "address": "12 Obafemi Awolowo Way, Ikeja",
        "phone": "08012345679",
    },
    {
        "name": "Elizade Abuja",
        "type": BranchType.both,
        "city": "Abuja",
        "state": "FCT",
        "address": "Plot 1234, Central Business District",
        "phone": "08012345680",
    },
]

_VEHICLE_SPECS = {
    "Seating": "5",
    "Fuel Economy": "14.5 km/L",
    "Safety": "Toyota Safety Sense 3.0",
    "Infotainment": "9\" Touchscreen",
    "Warranty": "3 Years / 100,000 km",
}

_MODEL_CATALOGUE = [
    ("Corolla", "XLE", "1.8L 4-Cylinder", "CVT", "Petrol", Decimal("38500000")),
    ("Corolla", "SE", "1.8L 4-Cylinder", "CVT", "Petrol", Decimal("35200000")),
    ("Camry", "XSE", "2.5L Turbo", "8-Speed Auto", "Petrol", Decimal("52000000")),
    ("Camry", "LE", "2.5L 4-Cylinder", "8-Speed Auto", "Petrol", Decimal("46500000")),
    ("RAV4", "Adventure", "2.5L Hybrid", "CVT", "Hybrid", Decimal("48500000")),
    ("RAV4", "XLE Premium", "2.5L Hybrid", "CVT", "Hybrid", Decimal("51000000")),
    ("Highlander", "Platinum", "3.5L V6", "8-Speed Auto", "Petrol", Decimal("62000000")),
    ("Hilux", "SR5", "2.8L Turbo Diesel", "6-Speed Auto", "Diesel", Decimal("44500000")),
    ("Land Cruiser", "VX", "3.5L Twin Turbo V6", "10-Speed Auto", "Petrol", Decimal("98000000")),
    ("Prius", "XLE", "1.8L Hybrid", "CVT", "Hybrid", Decimal("42000000")),
    ("Yaris", "LE", "1.5L 3-Cylinder", "CVT", "Petrol", Decimal("28500000")),
    ("Sienna", "Platinum", "2.5L Hybrid", "CVT", "Hybrid", Decimal("58000000")),
    ("Fortuner", "Legender", "2.8L Turbo Diesel", "6-Speed Auto", "Diesel", Decimal("55500000")),
]

_COLORS = [
    ("Pearl White", "#f5f5f5"),
    ("Midnight Black", "#1a1a1a"),
    ("Blueprint", "#2c4a6e"),
    ("Ruby Flare", "#8b1e1e"),
    ("Celestial Silver", "#b8bcc4"),
    ("Graphite", "#4a4a4a"),
    ("Magnetic Gray", "#6b7280"),
    ("Wind Chill Pearl", "#e8e4dc"),
]

_AVAILABILITY_MIX = (
    [AvailabilityStatus.available] * 18
    + [AvailabilityStatus.reserved] * 7
    + [AvailabilityStatus.sold] * 5
)

_BRANCH_CODES = ["VI", "IKJ", "ABJ"]

_CUSTOMER_PROFILES = [
    ("Adaeze", "Okonkwo", "adaeze.okonkwo@example.com", "Lagos", "Lagos", True, True, True),
    ("Chidi", "Eze", "chidi.eze@example.com", "Abuja", "FCT", True, False, False),
    ("Fatima", "Bello", "fatima.bello@example.com", "Lagos", "Lagos", False, True, False),
    ("Tunde", "Adeyemi", "tunde.adeyemi@example.com", "Lagos", "Lagos", True, True, True),
    ("Ngozi", "Okafor", "ngozi.okafor@example.com", "Port Harcourt", "Rivers", True, True, False),
    ("Emeka", "Nwosu", "emeka.nwosu@example.com", "Enugu", "Enugu", True, False, True),
    ("Aisha", "Yusuf", "aisha.yusuf@example.com", "Kano", "Kano", True, True, False),
    ("Kunle", "Bakare", "kunle.bakare@example.com", "Ibadan", "Oyo", True, True, True),
    ("Blessing", "Etim", "blessing.etim@example.com", "Calabar", "Cross River", False, True, False),
    ("Ibrahim", "Sule", "ibrahim.sule@example.com", "Abuja", "FCT", True, False, False),
    ("Yemi", "Alade", "yemi.alade@example.com", "Lagos", "Lagos", True, True, True),
    ("Funke", "Adebayo", "funke.adebayo@example.com", "Lagos", "Lagos", True, True, False),
    ("Obinna", "Chukwu", "obinna.chukwu@example.com", "Owerri", "Imo", True, True, True),
    ("Halima", "Garba", "halima.garba@example.com", "Kaduna", "Kaduna", True, False, True),
    ("Segun", "Ogunleye", "segun.ogunleye@example.com", "Lagos", "Lagos", True, True, False),
    ("Amaka", "Diallo", "amaka.diallo@example.com", "Abuja", "FCT", True, True, True),
    ("David", "Okoro", "david.okoro@example.com", "Benin City", "Edo", False, True, False),
    ("Zainab", "Abubakar", "zainab.abubakar@example.com", "Maiduguri", "Borno", True, False, False),
    ("Patrick", "Udoh", "patrick.udoh@example.com", "Uyo", "Akwa Ibom", True, True, True),
    ("Chioma", "Nnamdi", "chioma.nnamdi@example.com", "Lagos", "Lagos", True, True, True),
    ("Musa", "Danjuma", "musa.danjuma@example.com", "Jos", "Plateau", True, True, False),
    ("Grace", "Ekanem", "grace.ekanem@example.com", "Lagos", "Lagos", True, False, True),
    ("Victor", "Bassey", "victor.bassey@example.com", "Port Harcourt", "Rivers", True, True, False),
    ("Hauwa", "Mohammed", "hauwa.mohammed@example.com", "Sokoto", "Sokoto", True, True, False),
    ("Daniel", "Afolabi", "daniel.afolabi@example.com", "Lagos", "Lagos", True, True, True),
    ("Ifeoma", "Igwe", "ifeoma.igwe@example.com", "Onitsha", "Anambra", True, True, False),
    ("Samuel", "Adegoke", "samuel.adegoke@example.com", "Abeokuta", "Ogun", False, True, False),
    ("Rukayat", "Lawal", "rukayat.lawal@example.com", "Ilorin", "Kwara", True, True, True),
    ("Peter", "Edem", "peter.edem@example.com", "Uyo", "Akwa Ibom", True, False, False),
    ("Bimpe", "Oladipo", "bimpe.oladipo@example.com", "Lagos", "Lagos", True, True, True),
]

_CRM_NOTES = [
    "Prefers weekend appointments. Interested in extended warranty.",
    "Browsing RAV4 Hybrid — follow up after test drive.",
    "High-value repeat buyer — offer loyalty service discount.",
    "Requested callback on Camry financing options.",
    "Due for 30,000 km service — proactive outreach recommended.",
    "Marketing opt-in — send promo campaigns only.",
    "Inactive for 90 days — re-engagement campaign candidate.",
    "Trade-in enquiry on current Corolla for Highlander.",
]

_OWNED_MODELS = [
    ("Corolla", "XLE", 2022),
    ("Corolla", "LE", 2021),
    ("Camry", "XSE", 2023),
    ("Camry", "SE", 2020),
    ("RAV4", "Adventure", 2024),
    ("RAV4", "Limited", 2022),
    ("Highlander", "XLE", 2023),
    ("Hilux", "SR5", 2021),
    ("Prius", "XLE", 2022),
    ("Yaris", "LE", 2019),
    ("Sienna", "XLE", 2023),
    ("Fortuner", "Legender", 2022),
]


def _generate_catalogue_vehicles(branch_rows: list[Branch], admin_id: str | None) -> list[dict]:
    now = datetime.now(timezone.utc)
    payloads: list[dict] = []
    idx = 1

    for branch_i, branch in enumerate(branch_rows):
        code = _BRANCH_CODES[branch_i % len(_BRANCH_CODES)]
        per_branch = 10 if branch_i < 2 else 10  # 30 total across 3 branches

        for n in range(per_branch):
            model, trim, engine, transmission, fuel_type, base_price = _MODEL_CATALOGUE[(idx - 1) % len(_MODEL_CATALOGUE)]
            color, color_hex = _COLORS[(idx - 1) % len(_COLORS)]
            availability = _AVAILABILITY_MIX[(idx - 1) % len(_AVAILABILITY_MIX)]
            year = 2024 if idx % 4 else 2025
            stock = f"ELZ-{code}-{model[:3].upper()}-{idx:03d}"
            vin = f"JTDBT9234050{idx:05d}"
            is_promo = idx % 7 == 0 and availability == AvailabilityStatus.available

            payload = {
                "vin": vin,
                "stock_number": stock,
                "model": model,
                "trim": trim,
                "year": year,
                "color": color,
                "color_hex": color_hex,
                "price": base_price,
                "promotional_price": (base_price * Decimal("0.96")).quantize(Decimal("1")) if is_promo else None,
                "is_promotional": is_promo,
                "promotion_label": "Seasonal Offer" if is_promo else None,
                "fuel_type": fuel_type,
                "transmission": transmission,
                "engine": engine,
                "availability": availability,
                "branch_id": branch.id,
                "specs": dict(_VEHICLE_SPECS),
                "is_published": availability != AvailabilityStatus.sold,
                "published_at": now if availability != AvailabilityStatus.sold else None,
                "created_by_id": admin_id,
            }
            payloads.append(payload)
            idx += 1
            if idx > 30:
                return payloads

    return payloads


def _seed_key(*parts: str | None) -> str:
    return next((p for p in parts if p), "elizade")


def _images_for_model(model: str, seed_key: str, count: int = 2) -> list[str]:
    pool = _CAR_IMAGE_POOL
    offset = (sum(ord(c) for c in seed_key) + sum(ord(c) for c in model)) % len(pool)
    urls: list[str] = []
    for i in range(min(count, len(pool))):
        url = pool[(offset + i) % len(pool)]
        if url not in urls:
            urls.append(url)
    return urls or [_DEMO_IMAGE]


def _attach_vehicle_images(db: Session, vehicle: Vehicle, *, seed_key: str | None = None) -> None:
    key = _seed_key(seed_key, vehicle.stock_number, vehicle.vin, vehicle.id)
    for sort_order, url in enumerate(_images_for_model(vehicle.model, key, count=2)):
        db.add(
            VehicleImage(
                vehicle_id=vehicle.id,
                url=url,
                alt_text=f"{vehicle.year} Toyota {vehicle.model}",
                sort_order=sort_order,
                is_primary=(sort_order == 0),
            )
        )


def _needs_image_refresh(images: list[VehicleImage]) -> bool:
    if len(images) < 2:
        return True
    return any(any(host in img.url for host in _UNRELIABLE_IMAGE_HOSTS) for img in images)


def _backfill_vehicle_images(db: Session) -> None:
    """Ensure every catalogue vehicle has verified Toyota photos."""
    vehicles = db.query(Vehicle).all()
    for vehicle in vehicles:
        images = (
            db.query(VehicleImage)
            .filter(VehicleImage.vehicle_id == vehicle.id)
            .order_by(VehicleImage.sort_order.asc())
            .all()
        )
        if not _needs_image_refresh(images):
            continue
        for image in images:
            db.delete(image)
        db.flush()
        _attach_vehicle_images(db, vehicle)


def _seed_vehicle(db: Session, payload: dict) -> None:
    stock = payload.get("stock_number")
    vin = payload.get("vin")
    if stock and db.query(Vehicle).filter(Vehicle.stock_number == stock).one_or_none():
        return
    if vin and db.query(Vehicle).filter(Vehicle.vin == vin).one_or_none():
        return

    vehicle = Vehicle(**payload)
    db.add(vehicle)
    db.flush()
    _attach_vehicle_images(db, vehicle, seed_key=stock or vin)


def _find_existing_customer(db: Session, *, phone_normalized: str, email: str | None) -> User | None:
    row = db.query(User).filter(User.phone_normalized == phone_normalized).one_or_none()
    if row:
        return row
    if email:
        return db.query(User).filter(User.email == email).one_or_none()
    return None


def _ensure_owned_vehicle(
    db: Session,
    *,
    user: User,
    index: int,
    has_vehicle: bool,
    state: str,
    now: datetime,
) -> None:
    if not has_vehicle:
        return

    vin = f"OWNED{index:012d}"
    if db.query(OwnedVehicle).filter(OwnedVehicle.vin == vin).one_or_none():
        return

    model, trim, year = _OWNED_MODELS[index % len(_OWNED_MODELS)]
    color, _ = _COLORS[index % len(_COLORS)]
    days_until_service = (index % 5) * 3 - 2
    owned_image = _images_for_model(model, vin, count=1)[0]
    db.add(
        OwnedVehicle(
            user_id=user.id,
            vin=vin,
            model=model,
            trim=trim,
            year=year,
            color=color,
            registration_number=f"{state[:3].upper()}-{100 + index}-{chr(65 + (index % 26))}{chr(66 + (index % 25))}",
            mileage=8000 + (index * 1500),
            is_primary=True,
            image_url=owned_image,
            next_service_due=now + timedelta(days=days_until_service),
            next_service_mileage=8000 + (index * 1500) + 5000,
        )
    )


def _ensure_customer_note(db: Session, *, user: User, admin_id: str, index: int) -> None:
    if index % 3 != 0:
        return
    body = _CRM_NOTES[index % len(_CRM_NOTES)]
    existing = (
        db.query(CustomerNote)
        .filter(CustomerNote.customer_id == user.id, CustomerNote.body == body)
        .one_or_none()
    )
    if existing:
        return
    db.add(CustomerNote(customer_id=user.id, author_id=admin_id, body=body))


def _seed_customers(db: Session, admin_id: str | None) -> list[User]:
    seeded: list[User] = []
    now = datetime.now(timezone.utc)

    for i, (first, last, email, city, state, verified, has_vehicle, marketing_opt_in) in enumerate(_CUSTOMER_PROFILES):
        phone_normalized = f"801555{i:04d}"
        phone_display = f"0801555{i:04d}"

        existing = _find_existing_customer(db, phone_normalized=phone_normalized, email=email)
        if existing:
            seeded.append(existing)
            _ensure_owned_vehicle(
                db,
                user=existing,
                index=i,
                has_vehicle=has_vehicle,
                state=state,
                now=now,
            )
            if admin_id:
                _ensure_customer_note(db, user=existing, admin_id=admin_id, index=i)
            continue

        prefs = dict(DEFAULT_PREFERENCES)
        prefs["marketing_opt_in"] = marketing_opt_in

        user = User(
            phone_normalized=phone_normalized,
            phone_display=phone_display,
            first_name=first,
            last_name=last,
            email=email,
            city=city,
            state=state,
            role=UserRole.customer,
            is_verified=verified,
            is_active=True,
            preferences=prefs,
            created_at=now - timedelta(days=random.randint(1, 120)),
        )
        db.add(user)
        db.flush()
        seeded.append(user)

        _ensure_owned_vehicle(
            db,
            user=user,
            index=i,
            has_vehicle=has_vehicle,
            state=state,
            now=now,
        )

        if admin_id:
            _ensure_customer_note(db, user=user, admin_id=admin_id, index=i)

    return seeded


_DEMO_SERVICE_MARKER = "Demo service:"


def _seed_service_ops(
    db: Session,
    *,
    admin_id: str | None,
    branch_rows: list[Branch],
) -> None:
    """Seed bays and today's service board — runs independently of support/warranty counts."""
    from app.domains.service.models import (
        AdditionalWorkRequest,
        ServiceAppointment,
        ServiceBay,
        ServiceJob,
        ServiceJobStage,
    )

    if not branch_rows:
        return

    if db.query(ServiceBay).count() == 0:
        for branch in branch_rows:
            for bay_num in range(1, 5):
                db.add(ServiceBay(branch_id=branch.id, name=f"Bay {bay_num}", is_active=True))
        db.flush()

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    existing_demo = (
        db.query(ServiceAppointment)
        .filter(ServiceAppointment.issue_description.like(f"{_DEMO_SERVICE_MARKER}%"))
        .order_by(ServiceAppointment.scheduled_at.asc())
        .all()
    )
    if len(existing_demo) >= 8:
        # Roll demo slots to today so the ops board stays populated after restarts.
        for appt in existing_demo:
            hour = max(8, min(appt.scheduled_at.hour, 17))
            appt.scheduled_at = today_start + timedelta(hours=hour)
            appt.estimated_completion = appt.scheduled_at + timedelta(hours=3)
        return

    staff = (
        db.query(User)
        .filter(User.role.in_([UserRole.staff, UserRole.admin]), User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .first()
    )
    assignee_id = staff.id if staff else admin_id

    owners = (
        db.query(User)
        .filter(User.role == UserRole.customer, User.owned_vehicles.any())
        .limit(8)
        .all()
    )
    if not owners:
        return

    bays = db.query(ServiceBay).filter(ServiceBay.is_active.is_(True)).all()
    if not bays:
        return

    slot_specs: list[tuple[int, AppointmentStatus, ServiceType, str, bool, bool]] = [
        (9, AppointmentStatus.confirmed, ServiceType.periodic, "5,000 km periodic service", False, False),
        (10, AppointmentStatus.confirmed, ServiceType.inspection, "Pre-trip safety inspection", False, False),
        (11, AppointmentStatus.in_progress, ServiceType.repair, "Brake pad replacement", True, False),
        (12, AppointmentStatus.in_progress, ServiceType.periodic, "Oil change and filter", True, False),
        (13, AppointmentStatus.awaiting_approval, ServiceType.repair, "Suspension noise diagnosis", True, True),
        (14, AppointmentStatus.confirmed, ServiceType.recall, "Fuel pump recall check", False, False),
        (15, AppointmentStatus.requested, ServiceType.repair, "AC not cooling properly", False, False),
        (16, AppointmentStatus.completed, ServiceType.periodic, "10,000 km service completed", True, False),
    ]

    stage_labels = [
        "Vehicle received",
        "Inspection",
        "Service performed",
        "Quality check",
        "Ready for collection",
    ]

    for i, (hour, appt_status, service_type, detail, with_job, with_extra_work) in enumerate(slot_specs):
        if i >= len(owners):
            break
        customer = owners[i]
        vehicle = customer.owned_vehicles[0]
        branch = branch_rows[i % len(branch_rows)]
        branch_bays = [b for b in bays if b.branch_id == branch.id]
        bay = branch_bays[i % len(branch_bays)] if branch_bays else bays[i % len(bays)]
        scheduled_at = today_start + timedelta(hours=hour)
        eta = scheduled_at + timedelta(hours=3)

        appt = ServiceAppointment(
            user_id=customer.id,
            owned_vehicle_id=vehicle.id,
            branch_id=branch.id,
            bay_id=bay.id,
            service_type=service_type,
            scheduled_at=scheduled_at,
            status=appt_status,
            issue_description=f"{_DEMO_SERVICE_MARKER} {detail}",
            estimated_completion=eta,
            mileage_at_booking=vehicle.mileage,
            assigned_technician_id=assignee_id,
            technician_notes="Demo board entry for service operations UI." if with_job else None,
        )
        db.add(appt)
        db.flush()

        if not with_job:
            continue

        job_status = (
            ServiceJobStatus.awaiting_approval
            if appt_status == AppointmentStatus.awaiting_approval
            else ServiceJobStatus.completed
            if appt_status == AppointmentStatus.completed
            else ServiceJobStatus.in_progress
        )
        job = ServiceJob(
            appointment_id=appt.id,
            bay_id=bay.id,
            status=job_status,
            started_at=scheduled_at - timedelta(minutes=30),
            estimated_completion=eta,
            completed_at=scheduled_at + timedelta(hours=2) if appt_status == AppointmentStatus.completed else None,
        )
        db.add(job)
        db.flush()

        for order, label in enumerate(stage_labels):
            completed = (
                appt_status == AppointmentStatus.completed
                or (appt_status == AppointmentStatus.in_progress and order < 2)
                or (appt_status == AppointmentStatus.awaiting_approval and order < 3)
            )
            db.add(
                ServiceJobStage(
                    job_id=job.id,
                    label=label,
                    sort_order=order,
                    completed=completed,
                    completed_at=scheduled_at if completed else None,
                )
            )

        if with_extra_work:
            db.add(
                AdditionalWorkRequest(
                    job_id=job.id,
                    description="Replace worn lower control arm bushings",
                    cost=Decimal("85000"),
                    status=AdditionalWorkStatus.pending_approval,
                )
            )


def _seed_operational_data(db: Session, admin_id: str | None, customers: list[User], branch_rows: list[Branch]) -> None:
    now = datetime.now(timezone.utc)
    staff = (
        db.query(User)
        .filter(User.role.in_([UserRole.staff, UserRole.admin]))
        .order_by(User.created_at.asc())
        .all()
    )
    assignee_id = staff[0].id if staff else admin_id

    ticket_specs = [
        ("TKT-1001", TicketCategory.service, "Brake squeal on Camry", TicketStatus.open, TicketPriority.high, SlaStatus.at_risk),
        ("TKT-1002", TicketCategory.sales, "Financing quote follow-up", TicketStatus.in_progress, TicketPriority.medium, SlaStatus.ok),
        ("TKT-1003", TicketCategory.warranty, "AC compressor claim", TicketStatus.assigned, TicketPriority.high, SlaStatus.at_risk),
        ("TKT-1004", TicketCategory.general, "App login issue", TicketStatus.waiting_customer, TicketPriority.low, SlaStatus.ok),
        ("TKT-1005", TicketCategory.billing, "Duplicate service invoice", TicketStatus.open, TicketPriority.medium, SlaStatus.ok),
        ("TKT-1006", TicketCategory.service, "Delayed appointment", TicketStatus.in_progress, TicketPriority.urgent, SlaStatus.at_risk),
        ("TKT-1007", TicketCategory.warranty, "Extended warranty enquiry", TicketStatus.open, TicketPriority.low, SlaStatus.ok),
        ("TKT-1008", TicketCategory.sales, "Test drive reschedule", TicketStatus.assigned, TicketPriority.medium, SlaStatus.ok),
    ]

    for i, (number, category, subject, status, priority, sla) in enumerate(ticket_specs):
        if db.query(SupportTicket).filter(SupportTicket.ticket_number == number).one_or_none():
            continue
        customer = customers[i % len(customers)] if customers else None
        if not customer:
            continue
        db.add(
            SupportTicket(
                ticket_number=number,
                user_id=customer.id,
                category=category,
                subject=subject,
                status=status,
                priority=priority,
                assigned_to_id=assignee_id,
                first_response_due=now + timedelta(hours=4),
                resolution_due=now + timedelta(days=2),
                sla_status=sla,
            )
        )

    claim_specs = [
        (ClaimStatus.submitted, "Engine mount vibration"),
        (ClaimStatus.under_review, "Infotainment screen flicker"),
        (ClaimStatus.escalated, "Hybrid battery warning light"),
        (ClaimStatus.submitted, "Paint defect — rear panel"),
        (ClaimStatus.under_review, "Suspension noise at low speed"),
    ]

    owners_with_vehicles = (
        db.query(User)
        .filter(User.role == UserRole.customer, User.owned_vehicles.any())
        .limit(5)
        .all()
    )
    for i, (claim_status, description) in enumerate(claim_specs):
        if i >= len(owners_with_vehicles):
            break
        customer = owners_with_vehicles[i]
        vehicle = customer.owned_vehicles[0]
        existing = (
            db.query(WarrantyClaim)
            .filter(WarrantyClaim.user_id == customer.id, WarrantyClaim.description == description)
            .one_or_none()
        )
        if existing:
            continue
        db.add(
            WarrantyClaim(
                user_id=customer.id,
                owned_vehicle_id=vehicle.id,
                claim_type="Mechanical",
                description=description,
                status=claim_status,
                assigned_to_id=assignee_id,
            )
        )


def _seed_sla_configs(db: Session) -> None:
    if db.query(SlaConfig).count() > 0:
        return
    defaults = [
        (TicketCategory.sales, 4, 48),
        (TicketCategory.service, 2, 24),
        (TicketCategory.warranty, 8, 72),
        (TicketCategory.billing, 6, 48),
        (TicketCategory.general, 12, 72),
    ]
    for category, response_hours, resolution_hours in defaults:
        db.add(
            SlaConfig(
                category=category,
                response_hours=response_hours,
                resolution_hours=resolution_hours,
                is_active=True,
            )
        )


def _seed_warranty_extras(db: Session, admin_id: str | None) -> None:
    now = datetime.now(timezone.utc)

    owners = (
        db.query(User)
        .filter(User.role == UserRole.customer, User.owned_vehicles.any())
        .limit(8)
        .all()
    )
    for i, customer in enumerate(owners):
        vehicle = customer.owned_vehicles[0]
        cert_number = f"ELZ-WTY-{i + 1:04d}"
        if db.query(WarrantyCertificate).filter(WarrantyCertificate.certificate_number == cert_number).one_or_none():
            continue
        db.add(
            WarrantyCertificate(
                owned_vehicle_id=vehicle.id,
                user_id=customer.id,
                certificate_number=cert_number,
                type=WarrantyCertificateType.standard if i % 2 == 0 else WarrantyCertificateType.extended,
                coverage_start=now - timedelta(days=180),
                coverage_end=now + timedelta(days=545),
                status=WarrantyCertificateStatus.active,
                coverage_details=["Engine", "Transmission", "Electrical", "Air conditioning"],
                issued_by_id=admin_id,
            )
        )

    if db.query(RecallCampaign).count() == 0:
        recall = RecallCampaign(
            reference_code="REC-2026-0142",
            title="Fuel pump module inspection",
            description="Inspect and replace fuel pump module on affected Toyota RAV4 Hybrid models.",
            severity=RecallSeverity.high,
            affected_models=["RAV4"],
            affected_year_from=2022,
            affected_year_to=2025,
            is_active=True,
            created_by_id=admin_id,
        )
        db.add(recall)
        db.flush()

        for customer in owners[:4]:
            vehicle = customer.owned_vehicles[0]
            if db.query(RecallVehicle).filter(
                RecallVehicle.recall_id == recall.id,
                RecallVehicle.owned_vehicle_id == vehicle.id,
            ).one_or_none():
                continue
            db.add(
                RecallVehicle(
                    recall_id=recall.id,
                    owned_vehicle_id=vehicle.id,
                    user_id=customer.id,
                    notified_at=now - timedelta(days=3) if customer.id == owners[0].id else None,
                )
            )


def _seed_notification_engine(db: Session, admin_id: str | None) -> None:
    if db.query(NotificationRule).count() == 0:
        db.add(
            NotificationRule(
                name="Service due reminder",
                trigger_key="service_due_soon",
                channels=["in_app", "email", "push"],
                cadence="daily",
                is_active=True,
                config={
                    "days_before": 14,
                    "title": "Your Toyota is due for service",
                    "deep_link": "/service/book",
                },
                created_by_id=admin_id,
            )
        )
        db.add(
            NotificationRule(
                name="Promo — opted-in customers",
                trigger_key="marketing_opt_in",
                channels=["in_app", "email"],
                cadence="weekly",
                is_active=True,
                config={
                    "title": "Exclusive Elizade offers",
                    "body": "Browse seasonal promotions on Toyota models and service packages.",
                },
                created_by_id=admin_id,
            )
        )

    if db.query(BroadcastCampaign).count() == 0:
        reach = db.query(User).filter(User.role == UserRole.customer, User.owned_vehicles.any()).count()
        db.add(
            BroadcastCampaign(
                title="June service special",
                body="Book periodic service this month and get a complimentary vehicle health check.",
                segment_key="has_vehicle",
                channels=["in_app", "push"],
                status=BroadcastCampaignStatus.draft,
                reach_count=reach,
                created_by_id=admin_id,
            )
        )
        db.add(
            BroadcastCampaign(
                title="New Toyota arrivals",
                body="Explore freshly stocked Camry, RAV4, and Hilux models at all Elizade branches.",
                segment_key="marketing_opt_in",
                channels=["in_app", "email"],
                status=BroadcastCampaignStatus.draft,
                reach_count=db.query(User).filter(User.role == UserRole.customer).count(),
                created_by_id=admin_id,
            )
        )


def seed_demo_data(db: Session) -> None:
    try:
        _run_seed_demo_data(db)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _run_seed_demo_data(db: Session) -> None:
    admin = (
        db.query(User)
        .filter(User.role == UserRole.admin)
        .order_by(User.created_at.asc())
        .first()
    )
    admin_id = admin.id if admin else None

    branch_rows: list[Branch] = db.query(Branch).order_by(Branch.created_at.asc()).all()
    if not branch_rows:
        for data in _BRANCHES:
            branch = Branch(**data)
            db.add(branch)
            branch_rows.append(branch)
        db.flush()

    for payload in _generate_catalogue_vehicles(branch_rows, admin_id):
        _seed_vehicle(db, payload)

    _backfill_vehicle_images(db)

    customers = _seed_customers(db, admin_id)
    _seed_operational_data(db, admin_id, customers, branch_rows)
    staff = (
        db.query(User)
        .filter(User.role.in_([UserRole.staff, UserRole.admin]), User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .first()
    )
    _seed_leads(db, staff.id if staff else admin_id)
    _seed_service_ops(db, admin_id=admin_id, branch_rows=branch_rows)
    _seed_sla_configs(db)
    _seed_warranty_extras(db, admin_id)
    _seed_notification_engine(db, admin_id)
