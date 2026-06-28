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
    AppointmentStatus,
    AvailabilityStatus,
    BranchType,
    BroadcastCampaignStatus,
    ClaimStatus,
    RecallSeverity,
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

_WIKI = "https://upload.wikimedia.org/wikipedia/commons/thumb"

# Verified Toyota catalogue photos (Wikimedia Commons — always actual vehicles).
_MODEL_IMAGES: dict[str, list[str]] = {
    "Corolla": [
        f"{_WIKI}/9/9f/2018_Toyota_Corolla_%28E210%29_Ascent_sedan_%282018-08-27%29_01.jpg/1280px-2018_Toyota_Corolla_%28E210%29_Ascent_sedan_%282018-08-27%29_01.jpg",
        f"{_WIKI}/4/4f/2020_Toyota_Corolla_Hybrid_%28ZE141R%29_Ascent_sport_hatchback_%282020-07-17%29.jpg/1280px-2020_Toyota_Corolla_Hybrid_%28ZE141R%29_Ascent_sport_hatchback_%282020-07-17%29.jpg",
    ],
    "Camry": [
        f"{_WIKI}/6/68/2018_Toyota_Camry_%28ASV70R%29_Ascent_sedan_%282018-08-27%29_01.jpg/1280px-2018_Toyota_Camry_%28ASV70R%29_Ascent_sedan_%282018-08-27%29_01.jpg",
        f"{_WIKI}/7/7e/2021_Toyota_Camry_%28ASV70R%29_Ascent_Hybrid_sedan_%282021-03-22%29.jpg/1280px-2021_Toyota_Camry_%28ASV70R%29_Ascent_Hybrid_sedan_%282021-03-22%29.jpg",
    ],
    "RAV4": [
        f"{_WIKI}/5/5f/2019_Toyota_RAV4_%28AXAH52R%29_GX_%28hybrid%29_wagon_%2818-03-2019%29.jpg/1280px-2019_Toyota_RAV4_%28AXAH52R%29_GX_%28hybrid%29_wagon_%2818-03-2019%29.jpg",
        f"{_WIKI}/8/8d/2020_Toyota_RAV4_%28AXAH54R%29_Cruiser_%28hybrid%29_wagon_%282020-07-06%29.jpg/1280px-2020_Toyota_RAV4_%28AXAH54R%29_Cruiser_%28hybrid%29_wagon_%282020-07-06%29.jpg",
    ],
    "Highlander": [
        f"{_WIKI}/8/82/2020_Toyota_Highlander_%28MXU80R%29_GXL_wagon_%282020-08-31%29.jpg/1280px-2020_Toyota_Highlander_%28MXU80R%29_GXL_wagon_%282020-08-31%29.jpg",
        f"{_WIKI}/0/0a/2021_Toyota_Kluger_%28AXUH78R%29_GXL_%28hybrid%29_wagon_%282021-08-18%29.jpg/1280px-2021_Toyota_Kluger_%28AXUH78R%29_GXL_%28hybrid%29_wagon_%282021-08-18%29.jpg",
    ],
    "Hilux": [
        f"{_WIKI}/1/16/2016_Toyota_Hilux_%28GN126R%29_SR5_4-door_utility_%282016-01-06%29.jpg/1280px-2016_Toyota_Hilux_%28GN126R%29_SR5_4-door_utility_%282016-01-06%29.jpg",
        f"{_WIKI}/4/4a/2019_Toyota_Hilux_%28GUN126R%29_SR5_4-door_utility_%282019-08-08%29.jpg/1280px-2019_Toyota_Hilux_%28GUN126R%29_SR5_4-door_utility_%282019-08-08%29.jpg",
    ],
    "Land Cruiser": [
        f"{_WIKI}/9/9c/2022_Toyota_Land_Cruiser_%28J300%29_ZX_%28cropped%29.jpg/1280px-2022_Toyota_Land_Cruiser_%28J300%29_ZX_%28cropped%29.jpg",
        f"{_WIKI}/6/6a/2016_Toyota_Land_Cruiser_%28VDJ200R%29_VX_wagon_%282016-01-06%29.jpg/1280px-2016_Toyota_Land_Cruiser_%28VDJ200R%29_VX_wagon_%282016-01-06%29.jpg",
    ],
    "Prius": [
        f"{_WIKI}/3/3e/2016_Toyota_Prius_%28ZVW60R%29_i-Tech_liftback_%282016-10-12%29_01.jpg/1280px-2016_Toyota_Prius_%28ZVW60R%29_i-Tech_liftback_%282016-10-12%29_01.jpg",
        f"{_WIKI}/f/f2/2017_Toyota_Prius_%28ZVW60R%29_i-Tech_liftback_%282017-11-16%29.jpg/1280px-2017_Toyota_Prius_%28ZVW60R%29_i-Tech_liftback_%282017-11-16%29.jpg",
    ],
    "Yaris": [
        f"{_WIKI}/b/b3/2020_Toyota_Yaris_%28MXPH10R%29_ZR_hatchback_%282020-12-19%29.jpg/1280px-2020_Toyota_Yaris_%28MXPH10R%29_ZR_hatchback_%282020-12-19%29.jpg",
        f"{_WIKI}/8/8e/2017_Toyota_Yaris_%28XP130%29_Ascent_hatchback_%282017-11-16%29.jpg/1280px-2017_Toyota_Yaris_%28XP130%29_Ascent_hatchback_%282017-11-16%29.jpg",
    ],
    "Sienna": [
        f"{_WIKI}/5/5a/2021_Toyota_Sienna_%28XL40%29_XLE_%28cropped%29.jpg/1280px-2021_Toyota_Sienna_%28XL40%29_XLE_%28cropped%29.jpg",
        f"{_WIKI}/4/4d/2015_Toyota_Sienna_%28US%29.jpg/1280px-2015_Toyota_Sienna_%28US%29.jpg",
    ],
    "Fortuner": [
        f"{_WIKI}/6/6e/2016_Toyota_Fortuner_%28New_Zealand%29.jpg/1280px-2016_Toyota_Fortuner_%28New_Zealand%29.jpg",
        f"{_WIKI}/8/8b/2018_Toyota_Fortuner_%28AN160%29_VXR_wagon_%282018-08-31%29.jpg/1280px-2018_Toyota_Fortuner_%28AN160%29_VXR_wagon_%282018-08-31%29.jpg",
    ],
}

_DEFAULT_IMAGES = _MODEL_IMAGES["Corolla"]
_DEMO_IMAGE = _DEFAULT_IMAGES[0]

_UNRELIABLE_IMAGE_HOSTS = ("unsplash.com", "picsum.photos")

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
    pool = _MODEL_IMAGES.get(model, _DEFAULT_IMAGES)
    if not pool:
        return [_DEMO_IMAGE]
    offset = sum(ord(c) for c in seed_key) % len(pool)
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


def _seed_operational_data(db: Session, admin_id: str | None, customers: list[User], branch_rows: list[Branch]) -> None:
    if db.query(SupportTicket).count() >= 8:
        return

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

    if db.query(WarrantyClaim).count() >= 4:
        return

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

    try:
        from app.domains.service.models import ServiceAppointment, ServiceBay

        if db.query(ServiceBay).count() == 0:
            for branch in branch_rows:
                for bay_num in range(1, 5):
                    db.add(ServiceBay(branch_id=branch.id, name=f"Bay {bay_num}", is_active=True))
            db.flush()

        if db.query(ServiceAppointment).count() >= 6:
            return

        bays = db.query(ServiceBay).filter(ServiceBay.is_active.is_(True)).all()
        start = now.replace(hour=8, minute=0, second=0, microsecond=0)
        owners = owners_with_vehicles[:6]

        for i, customer in enumerate(owners):
            vehicle = customer.owned_vehicles[0]
            branch = branch_rows[i % len(branch_rows)]
            bay = bays[i % len(bays)] if bays else None
            slot = start + timedelta(hours=i * 2)
            db.add(
                ServiceAppointment(
                    user_id=customer.id,
                    owned_vehicle_id=vehicle.id,
                    branch_id=branch.id,
                    bay_id=bay.id if bay else None,
                    service_type=ServiceType.periodic if i % 2 == 0 else ServiceType.repair,
                    scheduled_at=slot,
                    status=(
                        AppointmentStatus.confirmed
                        if i % 3
                        else AppointmentStatus.in_progress
                    ),
                    issue_description="Periodic maintenance" if i % 2 == 0 else "Customer reported unusual noise",
                    mileage_at_booking=vehicle.mileage,
                    assigned_technician_id=assignee_id,
                )
            )
    except Exception:
        pass


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
    _seed_sla_configs(db)
    _seed_warranty_extras(db, admin_id)
    _seed_notification_engine(db, admin_id)
