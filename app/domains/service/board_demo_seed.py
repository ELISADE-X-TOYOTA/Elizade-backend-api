"""Demo catalogue and published price book for local dashboard preview.

Not for production — sample items and illustrative NGN prices only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.audit.models import AuditLog
from app.domains.service.models import (
    ServiceBoardVehicleModel,
    ServiceItem,
    ServicePriceBookEntry,
    ServicePriceBookVersion,
)
from app.domains.service.price_book_constants import (
    BOARD_MILEAGE_BANDS_KM,
    BOARD_VEHICLE_MODELS,
    DEFAULT_PRICE_DISCLAIMER,
)
from app.domains.service.price_book_service import _get_published_version, _next_version_number, ensure_board_reference_data
from app.domains.shared.enums import AuditAction, ServiceItemGroup, ServicePriceBookStatus
from app.domains.users.models import User, UserRole

# (code, display name, group, sort_order, base_price_ngn at reference band / flat price)
#
# Sized to the showroom wall board — sixteen rows across its three sections — so
# the preview shows the layout at the density it will actually run at. Five rows
# do not fill nine mileage columns convincingly; sixteen reveal how the sections
# stack and where the board starts to need scrolling on a 1080p screen.
#
# THE NAMES ARE REPRESENTATIVE, NOT TRANSCRIBED. They are the common Toyota
# service menu, not a reading of Elizade's board, and the prices are generated
# by `_demo_price` rather than quoted. Elizade's board appears to abbreviate
# ("Brake Pad Repl", "Timing Belt Repl"); swap these for the real rows before
# anyone treats a screenshot of this as a price list.
DEMO_CATALOGUE: tuple[tuple[str, str, ServiceItemGroup, int, int], ...] = (
    ("engine-oil-filter", "Engine oil and filter", ServiceItemGroup.periodic, 1, 28_000),
    ("air-filter", "Air filter", ServiceItemGroup.periodic, 2, 12_000),
    ("fuel-filter", "Fuel filter", ServiceItemGroup.periodic, 3, 15_000),
    ("spark-plugs", "Spark plugs", ServiceItemGroup.periodic, 4, 35_000),
    ("cabin-filter", "Cabin air filter", ServiceItemGroup.periodic, 5, 10_000),
    ("coolant", "Coolant replacement", ServiceItemGroup.periodic, 6, 26_000),
    ("transmission-fluid", "Automatic transmission fluid", ServiceItemGroup.periodic, 7, 58_000),
    ("brake-pads-front", "Brake pads (front)", ServiceItemGroup.chassis, 10, 48_000),
    ("brake-pads-rear", "Brake pads (rear)", ServiceItemGroup.chassis, 11, 44_000),
    ("brake-fluid", "Brake fluid replacement", ServiceItemGroup.chassis, 12, 18_000),
    ("wheel-alignment", "Wheel alignment", ServiceItemGroup.chassis, 13, 22_000),
    ("shock-absorbers", "Shock absorber replacement", ServiceItemGroup.chassis, 14, 96_000),
    ("timing-belt", "Timing belt kit", ServiceItemGroup.engine, 20, 125_000),
    ("drive-belt", "Drive belt", ServiceItemGroup.engine, 21, 32_000),
    ("radiator", "Radiator replacement", ServiceItemGroup.engine, 22, 148_000),
    ("clutch-kit", "Clutch kit replacement", ServiceItemGroup.engine, 23, 210_000),
)


def _demo_price(base: int, *, model_index: int, mileage_band_km: int) -> Decimal:
    """Illustrative price — varies slightly by model and mileage band."""
    model_factor = 1.0 + model_index * 0.04
    if mileage_band_km == 0:
        band_factor = 1.0
    else:
        band_factor = 0.85 + (mileage_band_km / 100_000) * 0.35
    return Decimal(str(int(base * model_factor * band_factor)))


def _ensure_catalogue(db: Session) -> dict[str, ServiceItem]:
    items: dict[str, ServiceItem] = {}
    for code, name, group, sort_order, _base in DEMO_CATALOGUE:
        row = db.query(ServiceItem).filter(ServiceItem.code == code).one_or_none()
        if row is None:
            row = ServiceItem(code=code, name=name, group=group, sort_order=sort_order, is_active=True)
            db.add(row)
            db.flush()
        else:
            row.name = name
            row.group = group
            row.sort_order = sort_order
            row.is_active = True
        items[code] = row
    db.commit()
    return items


def _resolve_actor(db: Session) -> User:
    actor = db.query(User).filter(User.role == UserRole.admin, User.is_active.is_(True)).first()
    if actor is not None:
        return actor
    actor = db.query(User).filter(User.role == UserRole.staff, User.is_active.is_(True)).first()
    if actor is not None:
        return actor
    raise RuntimeError("No staff/admin user found — run the API once to seed the admin account.")


def seed_service_board_demo(db: Session, *, replace_published: bool = False) -> dict:
    """Seed catalogue items and publish a demo price book. Idempotent unless replace_published."""
    ensure_board_reference_data(db)
    existing = _get_published_version(db)
    if existing is not None and not replace_published:
        return {
            "skipped": True,
            "reason": "A published price book already exists.",
            "versionNumber": existing.version_number,
        }

    items = _ensure_catalogue(db)
    models = (
        db.query(ServiceBoardVehicleModel)
        .filter(ServiceBoardVehicleModel.is_active.is_(True))
        .order_by(ServiceBoardVehicleModel.sort_order.asc())
        .all()
    )
    if not models:
        for index, name in enumerate(BOARD_VEHICLE_MODELS):
            db.add(ServiceBoardVehicleModel(name=name, sort_order=index, is_active=True))
        db.commit()
        models = (
            db.query(ServiceBoardVehicleModel)
            .filter(ServiceBoardVehicleModel.is_active.is_(True))
            .order_by(ServiceBoardVehicleModel.sort_order.asc())
            .all()
        )

    actor = _resolve_actor(db)
    now = datetime.now(timezone.utc)
    archived_id: str | None = None
    if existing is not None:
        existing.status = ServicePriceBookStatus.archived
        archived_id = existing.id

    version = ServicePriceBookVersion(
        version_number=_next_version_number(db),
        status=ServicePriceBookStatus.published,
        currency="NGN",
        price_inclusive=True,
        effective_from=now,
        disclaimer=DEFAULT_PRICE_DISCLAIMER,
        published_at=now,
        published_by_id=actor.id,
        created_by_id=actor.id,
    )
    db.add(version)
    db.flush()

    entry_count = 0
    base_by_code = {code: base for code, _name, _group, _sort, base in DEMO_CATALOGUE}
    for model_index, model in enumerate(models):
        for code, _name, group, _sort, base in DEMO_CATALOGUE:
            item = items[code]
            if group == ServiceItemGroup.periodic:
                bands = BOARD_MILEAGE_BANDS_KM
            else:
                bands = (0,)
            for band in bands:
                db.add(
                    ServicePriceBookEntry(
                        version_id=version.id,
                        service_item_id=item.id,
                        vehicle_model_id=model.id,
                        mileage_band_km=band,
                        price=_demo_price(base, model_index=model_index, mileage_band_km=band),
                    )
                )
                entry_count += 1

    db.add(
        AuditLog(
            actor_id=actor.id,
            action=AuditAction.create,
            entity_type="service_price_book_version",
            entity_id=version.id,
            changes={
                "source": "seed_service_board_demo",
                "versionNumber": version.version_number,
                "entryCount": entry_count,
                "archivedPreviousVersionId": archived_id,
            },
        )
    )
    db.commit()

    return {
        "skipped": False,
        "versionNumber": version.version_number,
        "entryCount": entry_count,
        "itemCount": len(items),
        "modelCount": len(models),
    }
