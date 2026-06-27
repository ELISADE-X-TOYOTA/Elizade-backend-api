"""Seed branches, catalogue vehicles, and sample CRM customers for local demos."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.branches.models import Branch
from app.domains.customers.models import CustomerNote, OwnedVehicle
from app.domains.inventory.models import Vehicle, VehicleImage
from app.domains.shared.enums import AvailabilityStatus, BranchType
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

_DEMO_IMAGE = "https://images.unsplash.com/photo-1621007947382-b6763a8ec158?w=800&h=500&fit=crop"

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


def _vehicles_for_branch(branch_id: str, admin_id: str | None) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "vin": "JTDBT923405012345",
            "stock_number": "ELZ-COR-001",
            "model": "Corolla",
            "trim": "XLE",
            "year": 2025,
            "color": "Pearl White",
            "color_hex": "#f5f5f5",
            "price": Decimal("38500000"),
            "promotional_price": Decimal("36800000"),
            "is_promotional": True,
            "promotion_label": "Year-End Offer",
            "fuel_type": "Petrol",
            "transmission": "CVT",
            "engine": "1.8L 4-Cylinder",
            "availability": AvailabilityStatus.available,
            "branch_id": branch_id,
            "specs": dict(_VEHICLE_SPECS),
            "is_published": True,
            "published_at": now,
            "created_by_id": admin_id,
        },
        {
            "vin": "JTDBT923405012346",
            "stock_number": "ELZ-CAM-001",
            "model": "Camry",
            "trim": "XSE",
            "year": 2025,
            "color": "Midnight Black",
            "color_hex": "#1a1a1a",
            "price": Decimal("52000000"),
            "fuel_type": "Petrol",
            "transmission": "8-Speed Auto",
            "engine": "2.5L Turbo",
            "availability": AvailabilityStatus.available,
            "branch_id": branch_id,
            "specs": {**_VEHICLE_SPECS, "Infotainment": "12.3\" Digital Cockpit"},
            "is_published": True,
            "published_at": now,
            "created_by_id": admin_id,
        },
        {
            "vin": "JTDBT923405012347",
            "stock_number": "ELZ-RAV-001",
            "model": "RAV4",
            "trim": "Adventure",
            "year": 2025,
            "color": "Blueprint",
            "color_hex": "#2c4a6e",
            "price": Decimal("48500000"),
            "fuel_type": "Hybrid",
            "transmission": "CVT",
            "engine": "2.5L Hybrid",
            "availability": AvailabilityStatus.reserved,
            "branch_id": branch_id,
            "specs": {**_VEHICLE_SPECS, "Fuel Economy": "18.2 km/L"},
            "is_published": True,
            "published_at": now,
            "created_by_id": admin_id,
        },
    ]


_CUSTOMERS = [
    {
        "phone_normalized": "8012345678",
        "phone_display": "08012345678",
        "first_name": "Adaeze",
        "last_name": "Okonkwo",
        "email": "adaeze.okonkwo@example.com",
        "city": "Lagos",
        "state": "Lagos",
        "is_verified": True,
        "owned": {
            "vin": "JTDBT923405099901",
            "model": "Corolla",
            "trim": "XLE",
            "year": 2023,
            "color": "Super White",
            "registration_number": "LAG-123-AB",
        },
        "note": "Prefers weekend appointments. Interested in extended warranty.",
    },
    {
        "phone_normalized": "8023456789",
        "phone_display": "08023456789",
        "first_name": "Chidi",
        "last_name": "Eze",
        "email": "chidi.eze@example.com",
        "city": "Abuja",
        "state": "FCT",
        "is_verified": True,
        "owned": None,
        "note": "Browsing RAV4 Hybrid — follow up after test drive.",
    },
    {
        "phone_normalized": "8034567890",
        "phone_display": "08034567890",
        "first_name": "Fatima",
        "last_name": "Bello",
        "email": "fatima.bello@example.com",
        "city": "Lagos",
        "state": "Lagos",
        "is_verified": False,
        "owned": {
            "vin": "JTDBT923405099902",
            "model": "Camry",
            "trim": "XSE",
            "year": 2024,
            "color": "Graphite",
            "registration_number": "LAG-456-CD",
        },
        "note": None,
    },
]


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
    db.add(
        VehicleImage(
            vehicle_id=vehicle.id,
            url=_DEMO_IMAGE,
            alt_text=f"{vehicle.year} Toyota {vehicle.model}",
            sort_order=0,
            is_primary=True,
        )
    )


def _seed_customers(db: Session, admin_id: str | None) -> None:
    for cust in _CUSTOMERS:
        existing = (
            db.query(User)
            .filter(User.phone_normalized == cust["phone_normalized"])
            .one_or_none()
        )
        if existing:
            continue

        user = User(
            phone_normalized=cust["phone_normalized"],
            phone_display=cust["phone_display"],
            first_name=cust["first_name"],
            last_name=cust["last_name"],
            email=cust["email"],
            city=cust["city"],
            state=cust["state"],
            role=UserRole.customer,
            is_verified=cust["is_verified"],
            is_active=True,
            preferences=dict(DEFAULT_PREFERENCES),
        )
        db.add(user)
        db.flush()

        owned = cust.get("owned")
        if owned:
            db.add(
                OwnedVehicle(
                    user_id=user.id,
                    vin=owned["vin"],
                    model=owned["model"],
                    trim=owned["trim"],
                    year=owned["year"],
                    color=owned["color"],
                    registration_number=owned["registration_number"],
                    is_primary=True,
                    image_url=_DEMO_IMAGE,
                )
            )

        note_body = cust.get("note")
        if note_body and admin_id:
            db.add(
                CustomerNote(
                    customer_id=user.id,
                    author_id=admin_id,
                    body=note_body,
                )
            )


def seed_demo_data(db: Session) -> None:
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

    # Seed the full catalogue on the primary branch only (stock numbers are globally unique).
    primary_branch = branch_rows[0]
    for payload in _vehicles_for_branch(primary_branch.id, admin_id):
        _seed_vehicle(db, payload)

    _seed_customers(db, admin_id)

    db.commit()
