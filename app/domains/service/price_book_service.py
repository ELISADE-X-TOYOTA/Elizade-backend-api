"""Service Board digital price book — import, versioning, and read APIs."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

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
    PRICE_IMPORT_TEMPLATE_COLUMNS,
)
from app.domains.service.price_book_schemas import (
    BoardVehicleModelOut,
    PriceBookBoardOut,
    PriceBookDetailOut,
    PriceBookEntryOut,
    PriceBookVersionOut,
    PriceImportPreviewOut,
    PriceImportPublishOut,
    PriceImportRowErrorOut,
    PriceImportRowPreviewOut,
    PricePublishIn,
)
from app.domains.shared.enums import AuditAction, ServicePriceBookStatus
from app.domains.users.models import User

_IMPORT_COLUMN_MAP = {
    "vehiclemodel": "vehicleModel",
    "vehicle_model": "vehicleModel",
    "serviceitemcode": "serviceItemCode",
    "service_item_code": "serviceItemCode",
    "mileagebandkm": "mileageBandKm",
    "mileage_band_km": "mileageBandKm",
    "price": "price",
}


def ensure_board_reference_data(db: Session) -> None:
    """Seed canonical board model names when the table is empty. No prices."""
    if db.query(ServiceBoardVehicleModel.id).limit(1).first() is not None:
        return
    for index, name in enumerate(BOARD_VEHICLE_MODELS):
        db.add(ServiceBoardVehicleModel(name=name, sort_order=index, is_active=True))
    db.commit()


def list_board_models(db: Session) -> list[BoardVehicleModelOut]:
    ensure_board_reference_data(db)
    rows = (
        db.query(ServiceBoardVehicleModel)
        .filter(ServiceBoardVehicleModel.is_active.is_(True))
        .order_by(ServiceBoardVehicleModel.sort_order.asc(), ServiceBoardVehicleModel.name.asc())
        .all()
    )
    return [BoardVehicleModelOut.from_model(row) for row in rows]


def list_mileage_bands() -> list[int]:
    return list(BOARD_MILEAGE_BANDS_KM)


def import_template_csv(db: Session) -> str:
    ensure_board_reference_data(db)
    item = (
        db.query(ServiceItem)
        .filter(ServiceItem.is_active.is_(True))
        .order_by(ServiceItem.sort_order.asc(), ServiceItem.code.asc())
        .first()
    )
    model = (
        db.query(ServiceBoardVehicleModel)
        .filter(ServiceBoardVehicleModel.is_active.is_(True))
        .order_by(ServiceBoardVehicleModel.sort_order.asc())
        .first()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(PRICE_IMPORT_TEMPLATE_COLUMNS)
    writer.writerow(
        [
            model.name if model else "Corolla",
            item.code if item else "engine-oil-filter",
            "10000",
            "",
        ]
    )
    return buffer.getvalue()


def _parse_import_rows(file: UploadFile) -> list[dict[str, str]]:
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a .csv file")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV has no header row")
    parsed: list[dict[str, str]] = []
    for raw_row in reader:
        if raw_row is None or all(v is None or str(v).strip() == "" for v in raw_row.values()):
            continue
        normalized: dict[str, str] = {}
        for header, value in raw_row.items():
            if header is None:
                continue
            key = _IMPORT_COLUMN_MAP.get(str(header).strip().lower())
            if not key or value is None:
                continue
            text_value = str(value).strip()
            if text_value:
                normalized[key] = text_value
        parsed.append(normalized)
    return parsed


def _active_model_map(db: Session) -> dict[str, ServiceBoardVehicleModel]:
    ensure_board_reference_data(db)
    rows = db.query(ServiceBoardVehicleModel).filter(ServiceBoardVehicleModel.is_active.is_(True)).all()
    return {row.name.casefold(): row for row in rows}


def _active_item_map(db: Session) -> dict[str, ServiceItem]:
    rows = db.query(ServiceItem).filter(ServiceItem.is_active.is_(True)).all()
    return {row.code.casefold(): row for row in rows}


def _cell_key(vehicle_model: str, service_item_code: str, mileage_band_km: int) -> tuple[str, str, int]:
    return (vehicle_model.casefold(), service_item_code.casefold(), mileage_band_km)


def _validate_import_rows(db: Session, rows: list[dict[str, str]]) -> PriceImportPreviewOut:
    models = _active_model_map(db)
    items = _active_item_map(db)
    allowed_bands = set(BOARD_MILEAGE_BANDS_KM)

    preview_rows: list[PriceImportRowPreviewOut] = []
    errors: list[PriceImportRowErrorOut] = []
    seen: set[tuple[str, str, int]] = set()
    duplicate_in_file = 0

    current_published = _get_published_version(db)
    current_version_number = current_published.version_number if current_published else None

    for index, raw in enumerate(rows):
        line_number = index + 2
        row_errors: list[str] = []

        vehicle_name = raw.get("vehicleModel", "").strip()
        item_code = raw.get("serviceItemCode", "").strip()
        band_text = raw.get("mileageBandKm", "").strip()
        price_text = raw.get("price", "").strip()

        if not vehicle_name:
            row_errors.append("vehicleModel is required")
        elif vehicle_name.casefold() not in models:
            row_errors.append(f"Unknown vehicle model '{vehicle_name}'")

        if not item_code:
            row_errors.append("serviceItemCode is required")
        elif item_code.casefold() not in items:
            row_errors.append(f"Unknown service item code '{item_code}'")

        mileage_band_km = 0
        if band_text:
            try:
                mileage_band_km = int(band_text.replace(",", ""))
            except ValueError:
                row_errors.append("mileageBandKm must be an integer")
            else:
                if mileage_band_km not in allowed_bands and mileage_band_km != 0:
                    row_errors.append(
                        f"mileageBandKm must be one of {', '.join(str(b) for b in BOARD_MILEAGE_BANDS_KM)} or empty"
                    )

        price: Decimal | None = None
        if not price_text:
            row_errors.append("price is required")
        else:
            try:
                price = Decimal(price_text.replace(",", ""))
            except InvalidOperation:
                row_errors.append("price must be a number")
            else:
                if price < 0:
                    row_errors.append("price must not be negative")

        if row_errors:
            errors.append(PriceImportRowErrorOut(row=line_number, errors=row_errors))
            continue

        key = _cell_key(vehicle_name, item_code, mileage_band_km)
        if key in seen:
            duplicate_in_file += 1
            errors.append(
                PriceImportRowErrorOut(
                    row=line_number,
                    errors=["Duplicate cell in file (same model, item, and mileage band)"],
                )
            )
            continue
        seen.add(key)

        preview_rows.append(
            PriceImportRowPreviewOut(
                row=line_number,
                vehicleModel=vehicle_name,
                serviceItemCode=item_code,
                mileageBandKm=mileage_band_km,
                price=price,  # type: ignore[arg-type]
                action="create",
            )
        )

    return PriceImportPreviewOut(
        total=len(rows),
        valid=len(preview_rows),
        failed=len(errors),
        duplicateCellsInFile=duplicate_in_file,
        rows=preview_rows,
        errors=errors,
        replacesPublishedVersion=current_published is not None,
        currentPublishedVersion=current_version_number,
    )


def preview_price_import(db: Session, file: UploadFile) -> PriceImportPreviewOut:
    rows = _parse_import_rows(file)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data rows found in file")
    return _validate_import_rows(db, rows)


def _next_version_number(db: Session) -> int:
    current = db.query(func.max(ServicePriceBookVersion.version_number)).scalar()
    return (current or 0) + 1


def _get_published_version(db: Session) -> ServicePriceBookVersion | None:
    return (
        db.query(ServicePriceBookVersion)
        .filter(ServicePriceBookVersion.status == ServicePriceBookStatus.published)
        .order_by(ServicePriceBookVersion.version_number.desc())
        .first()
    )


def publish_price_import(
    db: Session,
    file: UploadFile,
    payload: PricePublishIn,
    *,
    actor: User,
) -> PriceImportPublishOut:
    rows = _parse_import_rows(file)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data rows found in file")
    preview = _validate_import_rows(db, rows)
    if preview.failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Import validation failed", "errors": [e.model_dump() for e in preview.errors]},
        )

    models = _active_model_map(db)
    items = _active_item_map(db)
    now = datetime.now(timezone.utc)
    effective_from = payload.effective_from or now
    if effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=timezone.utc)

    previous = _get_published_version(db)
    archived_id: str | None = None
    if previous is not None:
        previous.status = ServicePriceBookStatus.archived
        archived_id = previous.id

    version = ServicePriceBookVersion(
        version_number=_next_version_number(db),
        status=ServicePriceBookStatus.published,
        currency="NGN",
        price_inclusive=True,
        effective_from=effective_from,
        disclaimer=(payload.disclaimer or DEFAULT_PRICE_DISCLAIMER).strip(),
        published_at=now,
        published_by_id=actor.id,
        created_by_id=actor.id,
    )
    db.add(version)
    db.flush()

    for raw in rows:
        vehicle = models[raw["vehicleModel"].strip().casefold()]
        item = items[raw["serviceItemCode"].strip().casefold()]
        band_text = raw.get("mileageBandKm", "").strip()
        mileage_band_km = int(band_text.replace(",", "")) if band_text else 0
        price = Decimal(raw["price"].replace(",", ""))
        db.add(
            ServicePriceBookEntry(
                version_id=version.id,
                service_item_id=item.id,
                vehicle_model_id=vehicle.id,
                mileage_band_km=mileage_band_km,
                price=price,
            )
        )

    db.add(
        AuditLog(
            actor_id=actor.id,
            action=AuditAction.create,
            entity_type="service_price_book_version",
            entity_id=version.id,
            changes={
                "versionNumber": version.version_number,
                "entryCount": len(preview.rows),
                "archivedPreviousVersionId": archived_id,
            },
        )
    )
    db.commit()
    db.refresh(version)
    return PriceImportPublishOut(
        versionId=version.id,
        versionNumber=version.version_number,
        publishedAt=version.published_at.isoformat() if version.published_at else now.isoformat(),
        entryCount=len(preview.rows),
        archivedPreviousVersionId=archived_id,
    )


def list_versions(db: Session) -> list[PriceBookVersionOut]:
    rows = (
        db.query(ServicePriceBookVersion, func.count(ServicePriceBookEntry.id))
        .outerjoin(ServicePriceBookEntry, ServicePriceBookEntry.version_id == ServicePriceBookVersion.id)
        .group_by(ServicePriceBookVersion.id)
        .order_by(ServicePriceBookVersion.version_number.desc())
        .all()
    )
    return [PriceBookVersionOut.from_model(version, entry_count=count) for version, count in rows]


def get_version(db: Session, version_id: str) -> PriceBookDetailOut:
    version = (
        db.query(ServicePriceBookVersion)
        .options(
            joinedload(ServicePriceBookVersion.entries).joinedload(ServicePriceBookEntry.service_item),
            joinedload(ServicePriceBookVersion.entries).joinedload(ServicePriceBookEntry.vehicle_model),
        )
        .filter(ServicePriceBookVersion.id == version_id)
        .one_or_none()
    )
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price book version not found")
    entries = sorted(
        version.entries,
        key=lambda row: (
            row.vehicle_model.name if row.vehicle_model else "",
            row.service_item.sort_order if row.service_item else 0,
            row.mileage_band_km,
        ),
    )
    base = PriceBookVersionOut.from_model(version, entry_count=len(entries))
    return PriceBookDetailOut(**base.model_dump(), entries=[PriceBookEntryOut.from_model(e) for e in entries])


def get_published_board(db: Session) -> PriceBookBoardOut:
    version = _get_published_version(db)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No published price book yet")
    detail = get_version(db, version.id)
    models = list_board_models(db)
    return PriceBookBoardOut(
        version=PriceBookVersionOut.model_validate(detail.model_dump()),
        mileageBandsKm=list_mileage_bands(),
        vehicleModels=[m.name for m in models],
        entries=detail.entries,
    )
