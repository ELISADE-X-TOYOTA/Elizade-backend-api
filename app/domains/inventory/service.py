import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import ceil

from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.domains.branches.models import Branch
from app.domains.inventory.models import Vehicle, VehicleImage
from app.domains.inventory.schemas import (
    BulkImportResultOut,
    BulkImportRowErrorOut,
    VehicleAdminDetailOut,
    VehicleAdminListItemOut,
    VehicleAdminListOut,
    VehicleCreateIn,
    VehicleDetailOut,
    VehicleImageOut,
    VehicleListItemOut,
    VehicleListOut,
    VehicleStatusUpdateIn,
    VehicleUpdateIn,
)
from app.domains.inventory.storage import storage
from app.domains.shared.enums import AvailabilityStatus
from app.domains.users.models import User

# Statuses a public visitor is allowed to see / filter by.
PUBLIC_AVAILABILITY = (AvailabilityStatus.available, AvailabilityStatus.reserved)

# Allowed `sort` values mapped to ORM order_by clauses.
SORT_OPTIONS = {
    "createdAt": Vehicle.created_at.asc(),
    "-createdAt": Vehicle.created_at.desc(),
    "price": Vehicle.price.asc(),
    "-price": Vehicle.price.desc(),
    "year": Vehicle.year.asc(),
    "-year": Vehicle.year.desc(),
}
COMPARE_LIMIT = 2
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per image


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _primary_image_url(vehicle: Vehicle) -> str | None:
    if not vehicle.images:
        return None
    for image in vehicle.images:  # images are ordered by sort_order via the relationship
        if image.is_primary:
            return image.url
    return vehicle.images[0].url


def _to_decimal(value: float | None, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field}")


def _resolve_sort(sort: str):
    if sort not in SORT_OPTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort. Allowed: {', '.join(SORT_OPTIONS)}",
        )
    return SORT_OPTIONS[sort]


def _to_image_out(image: VehicleImage) -> VehicleImageOut:
    return VehicleImageOut(
        id=image.id,
        url=image.url,
        altText=image.alt_text,
        sortOrder=image.sort_order,
        isPrimary=image.is_primary,
    )


def _to_list_item(vehicle: Vehicle) -> VehicleListItemOut:
    return VehicleListItemOut(
        id=vehicle.id,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        year=vehicle.year,
        color=vehicle.color,
        colorHex=vehicle.color_hex,
        price=vehicle.price,
        promotionalPrice=vehicle.promotional_price,
        isPromotional=vehicle.is_promotional,
        promotionLabel=vehicle.promotion_label,
        fuelType=vehicle.fuel_type,
        transmission=vehicle.transmission,
        availability=vehicle.availability.value,
        branchId=vehicle.branch_id,
        primaryImageUrl=_primary_image_url(vehicle),
        createdAt=_iso(vehicle.created_at),
    )


def _to_detail(vehicle: Vehicle) -> VehicleDetailOut:
    branch = vehicle.branch
    return VehicleDetailOut(
        id=vehicle.id,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        year=vehicle.year,
        color=vehicle.color,
        colorHex=vehicle.color_hex,
        price=vehicle.price,
        promotionalPrice=vehicle.promotional_price,
        isPromotional=vehicle.is_promotional,
        promotionLabel=vehicle.promotion_label,
        fuelType=vehicle.fuel_type,
        transmission=vehicle.transmission,
        engine=vehicle.engine,
        mileage=vehicle.mileage,
        availability=vehicle.availability.value,
        branchId=vehicle.branch_id,
        branchName=branch.name if branch else "",
        branchCity=branch.city if branch else "",
        branchState=branch.state if branch else "",
        specs=vehicle.specs or {},
        images=[_to_image_out(img) for img in vehicle.images],
        createdAt=_iso(vehicle.created_at),
        updatedAt=_iso(vehicle.updated_at),
    )


def _public_base_query(db: Session):
    """Vehicles visible to the public: not soft-deleted and published."""
    return db.query(Vehicle).filter(
        Vehicle.deleted_at.is_(None),
        Vehicle.is_published.is_(True),
    )


def list_vehicles(
    db: Session,
    *,
    branch_id: str | None = None,
    make: str | None = None,
    model: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    fuel_type: str | None = None,
    transmission: str | None = None,
    availability: str | None = None,
    page: int = 1,
    limit: int = 20,
    sort: str = "-createdAt",
) -> VehicleListOut:
    order_clause = _resolve_sort(sort)

    query = _public_base_query(db)

    if availability is not None:
        try:
            wanted = AvailabilityStatus(availability)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid availability")
        if wanted not in PUBLIC_AVAILABILITY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="availability filter must be 'available' or 'reserved'",
            )
        query = query.filter(Vehicle.availability == wanted)
    else:
        query = query.filter(Vehicle.availability.in_(PUBLIC_AVAILABILITY))

    if branch_id:
        query = query.filter(Vehicle.branch_id == branch_id)
    if make:
        query = query.filter(Vehicle.make.ilike(f"%{make}%"))
    if model:
        query = query.filter(Vehicle.model.ilike(f"%{model}%"))
    if fuel_type:
        query = query.filter(Vehicle.fuel_type.ilike(f"%{fuel_type}%"))
    if transmission:
        query = query.filter(Vehicle.transmission.ilike(f"%{transmission}%"))

    min_dec = _to_decimal(min_price, "minPrice")
    max_dec = _to_decimal(max_price, "maxPrice")
    if min_dec is not None:
        query = query.filter(Vehicle.price >= min_dec)
    if max_dec is not None:
        query = query.filter(Vehicle.price <= max_dec)

    total = query.count()
    rows = (
        query.options(selectinload(Vehicle.images))
        .order_by(order_clause)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return VehicleListOut(
        items=[_to_list_item(v) for v in rows],
        page=page,
        limit=limit,
        total=total,
        totalPages=ceil(total / limit) if total else 0,
    )


def get_vehicle(db: Session, vehicle_id: str) -> VehicleDetailOut:
    vehicle = (
        _public_base_query(db)
        .options(selectinload(Vehicle.images), selectinload(Vehicle.branch))
        .filter(Vehicle.id == vehicle_id)
        .one_or_none()
    )
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return _to_detail(vehicle)


def compare_vehicles(db: Session, ids: str) -> list[VehicleDetailOut]:
    id_list = [piece.strip() for piece in ids.split(",") if piece.strip()]
    if len(id_list) != COMPARE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provide exactly {COMPARE_LIMIT} vehicle ids to compare",
        )
    if len(set(id_list)) != len(id_list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot compare a vehicle with itself")

    rows = (
        _public_base_query(db)
        .options(selectinload(Vehicle.images), selectinload(Vehicle.branch))
        .filter(Vehicle.id.in_(id_list))
        .all()
    )
    found = {v.id: v for v in rows}
    missing = [vid for vid in id_list if vid not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more vehicles not found")

    # Preserve the order the caller requested.
    return [_to_detail(found[vid]) for vid in id_list]


# --------------------------------------------------------------------------- #
# Admin (staff portal) operations                                             #
# --------------------------------------------------------------------------- #

def _to_admin_list_item(vehicle: Vehicle) -> VehicleAdminListItemOut:
    branch = vehicle.branch
    return VehicleAdminListItemOut(
        id=vehicle.id,
        vin=vehicle.vin,
        stockNumber=vehicle.stock_number,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        year=vehicle.year,
        color=vehicle.color,
        price=vehicle.price,
        promotionalPrice=vehicle.promotional_price,
        isPromotional=vehicle.is_promotional,
        availability=vehicle.availability.value,
        branchId=vehicle.branch_id,
        branchName=branch.name if branch else "",
        isPublished=vehicle.is_published,
        primaryImageUrl=_primary_image_url(vehicle),
        createdAt=_iso(vehicle.created_at),
        updatedAt=_iso(vehicle.updated_at),
    )


def _to_admin_detail(vehicle: Vehicle) -> VehicleAdminDetailOut:
    branch = vehicle.branch
    return VehicleAdminDetailOut(
        id=vehicle.id,
        vin=vehicle.vin,
        stockNumber=vehicle.stock_number,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        year=vehicle.year,
        color=vehicle.color,
        colorHex=vehicle.color_hex,
        price=vehicle.price,
        promotionalPrice=vehicle.promotional_price,
        isPromotional=vehicle.is_promotional,
        promotionLabel=vehicle.promotion_label,
        fuelType=vehicle.fuel_type,
        transmission=vehicle.transmission,
        engine=vehicle.engine,
        mileage=vehicle.mileage,
        availability=vehicle.availability.value,
        branchId=vehicle.branch_id,
        branchName=branch.name if branch else "",
        branchCity=branch.city if branch else "",
        branchState=branch.state if branch else "",
        specs=vehicle.specs or {},
        images=[_to_image_out(img) for img in vehicle.images],
        isPublished=vehicle.is_published,
        publishedAt=_iso(vehicle.published_at),
        createdById=vehicle.created_by_id,
        createdAt=_iso(vehicle.created_at),
        updatedAt=_iso(vehicle.updated_at),
        deletedAt=_iso(vehicle.deleted_at),
    )


def _parse_availability(value: str) -> AvailabilityStatus:
    try:
        return AvailabilityStatus(value)
    except ValueError:
        allowed = ", ".join(a.value for a in AvailabilityStatus)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid availability. Allowed: {allowed}",
        )


def _require_branch(db: Session, branch_id: str) -> None:
    if db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch not found")


def _assert_vin_unique(db: Session, vin: str, *, exclude_id: str | None = None) -> None:
    query = db.query(Vehicle.id).filter(Vehicle.vin == vin)
    if exclude_id:
        query = query.filter(Vehicle.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="VIN already exists")


def _assert_stock_unique(db: Session, stock_number: str, *, exclude_id: str | None = None) -> None:
    query = db.query(Vehicle.id).filter(Vehicle.stock_number == stock_number)
    if exclude_id:
        query = query.filter(Vehicle.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stock number already exists")


def _get_admin_vehicle(db: Session, vehicle_id: str, *, include_deleted: bool = False) -> Vehicle:
    query = db.query(Vehicle).options(
        selectinload(Vehicle.images), selectinload(Vehicle.branch)
    ).filter(Vehicle.id == vehicle_id)
    if not include_deleted:
        query = query.filter(Vehicle.deleted_at.is_(None))
    vehicle = query.one_or_none()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return vehicle


def admin_list_vehicles(
    db: Session,
    *,
    branch_id: str | None = None,
    make: str | None = None,
    model: str | None = None,
    availability: str | None = None,
    is_published: bool | None = None,
    include_deleted: bool = False,
    page: int = 1,
    limit: int = 20,
    sort: str = "-createdAt",
) -> VehicleAdminListOut:
    order_clause = _resolve_sort(sort)

    query = db.query(Vehicle)
    if not include_deleted:
        query = query.filter(Vehicle.deleted_at.is_(None))
    if availability is not None:
        query = query.filter(Vehicle.availability == _parse_availability(availability))
    if is_published is not None:
        query = query.filter(Vehicle.is_published.is_(is_published))
    if branch_id:
        query = query.filter(Vehicle.branch_id == branch_id)
    if make:
        query = query.filter(Vehicle.make.ilike(f"%{make}%"))
    if model:
        query = query.filter(Vehicle.model.ilike(f"%{model}%"))

    total = query.count()
    rows = (
        query.options(selectinload(Vehicle.images), selectinload(Vehicle.branch))
        .order_by(order_clause)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return VehicleAdminListOut(
        items=[_to_admin_list_item(v) for v in rows],
        page=page,
        limit=limit,
        total=total,
        totalPages=ceil(total / limit) if total else 0,
    )


def admin_get_vehicle(db: Session, vehicle_id: str) -> VehicleAdminDetailOut:
    return _to_admin_detail(_get_admin_vehicle(db, vehicle_id))


def _persist_new_vehicle(db: Session, payload: VehicleCreateIn, current_user: User) -> Vehicle:
    """Validate and add a new vehicle to the session (flush only — no commit).

    Shared by the single-create endpoint and the bulk importer.
    """
    _require_branch(db, payload.branch_id)
    availability = _parse_availability(payload.availability)
    if payload.vin:
        _assert_vin_unique(db, payload.vin)
    if payload.stock_number:
        _assert_stock_unique(db, payload.stock_number)

    published_at = payload.published_at
    if payload.is_published and published_at is None:
        published_at = datetime.now(timezone.utc)

    vehicle = Vehicle(
        vin=payload.vin,
        stock_number=payload.stock_number,
        make=payload.make,
        model=payload.model,
        trim=payload.trim,
        year=payload.year,
        color=payload.color,
        color_hex=payload.color_hex,
        price=payload.price,
        promotional_price=payload.promotional_price,
        is_promotional=payload.is_promotional,
        promotion_label=payload.promotion_label,
        fuel_type=payload.fuel_type,
        transmission=payload.transmission,
        engine=payload.engine,
        mileage=payload.mileage,
        availability=availability,
        branch_id=payload.branch_id,
        specs=payload.specs or {},
        is_published=payload.is_published,
        published_at=published_at,
        created_by_id=current_user.id,
    )
    db.add(vehicle)
    db.flush()
    return vehicle


def create_vehicle(db: Session, payload: VehicleCreateIn, current_user: User) -> VehicleAdminDetailOut:
    vehicle = _persist_new_vehicle(db, payload, current_user)
    db.commit()
    db.refresh(vehicle)
    return _to_admin_detail(vehicle)


def update_vehicle(db: Session, vehicle_id: str, payload: VehicleUpdateIn) -> VehicleAdminDetailOut:
    vehicle = _get_admin_vehicle(db, vehicle_id)
    data = payload.model_dump(exclude_unset=True)

    if "branch_id" in data and data["branch_id"]:
        _require_branch(db, data["branch_id"])
    if data.get("vin"):
        _assert_vin_unique(db, data["vin"], exclude_id=vehicle.id)
    if data.get("stock_number"):
        _assert_stock_unique(db, data["stock_number"], exclude_id=vehicle.id)

    for field, value in data.items():
        setattr(vehicle, field, value)

    # Stamp a publish time when a listing is published and none is set.
    if data.get("is_published") is True and vehicle.published_at is None:
        vehicle.published_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(vehicle)
    return _to_admin_detail(vehicle)


def update_vehicle_status(
    db: Session, vehicle_id: str, payload: VehicleStatusUpdateIn
) -> VehicleAdminDetailOut:
    vehicle = _get_admin_vehicle(db, vehicle_id)
    vehicle.availability = _parse_availability(payload.availability)
    db.commit()
    db.refresh(vehicle)
    return _to_admin_detail(vehicle)


def soft_delete_vehicle(db: Session, vehicle_id: str) -> None:
    vehicle = _get_admin_vehicle(db, vehicle_id)
    vehicle.deleted_at = datetime.now(timezone.utc)
    db.commit()


# --------------------------------------------------------------------------- #
# Image operations                                                            #
# --------------------------------------------------------------------------- #

def add_vehicle_images(
    db: Session, vehicle_id: str, uploads: list[UploadFile]
) -> VehicleAdminDetailOut:
    vehicle = _get_admin_vehicle(db, vehicle_id)
    if not uploads:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    # Read and validate everything up front so a bad file doesn't leave a partial save.
    prepared: list[tuple[bytes, str | None, str | None]] = []
    for upload in uploads:
        content_type = upload.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed")
        content = upload.file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)}MB limit",
            )
        prepared.append((content, upload.filename, content_type))

    next_sort = max((img.sort_order for img in vehicle.images), default=-1) + 1
    has_primary = any(img.is_primary for img in vehicle.images)

    for offset, (content, filename, content_type) in enumerate(prepared):
        url = storage.save(content=content, filename=filename, content_type=content_type)
        image = VehicleImage(
            vehicle_id=vehicle.id,
            url=url,
            sort_order=next_sort + offset,
            # First image ever uploaded for this vehicle becomes the primary.
            is_primary=(not has_primary and offset == 0),
        )
        db.add(image)

    db.commit()
    db.refresh(vehicle)
    return _to_admin_detail(vehicle)


def delete_vehicle_image(db: Session, vehicle_id: str, image_id: str) -> None:
    vehicle = _get_admin_vehicle(db, vehicle_id)
    image = (
        db.query(VehicleImage)
        .filter(VehicleImage.id == image_id, VehicleImage.vehicle_id == vehicle.id)
        .one_or_none()
    )
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    was_primary = image.is_primary
    url = image.url
    db.delete(image)
    db.flush()

    # If the primary was removed, promote the next image (by sort order).
    if was_primary:
        replacement = (
            db.query(VehicleImage)
            .filter(VehicleImage.vehicle_id == vehicle.id)
            .order_by(VehicleImage.sort_order.asc())
            .first()
        )
        if replacement:
            replacement.is_primary = True

    db.commit()
    storage.delete(url)


# --------------------------------------------------------------------------- #
# Bulk import (CSV / XLSX)                                                     #
# --------------------------------------------------------------------------- #

# Accepted column headers (lower-cased) mapped to the create-payload field/alias.
_BULK_COLUMN_MAP = {
    "vin": "vin",
    "stocknumber": "stockNumber",
    "stock_number": "stockNumber",
    "make": "make",
    "model": "model",
    "trim": "trim",
    "year": "year",
    "color": "color",
    "colorhex": "colorHex",
    "color_hex": "colorHex",
    "price": "price",
    "promotionalprice": "promotionalPrice",
    "promotional_price": "promotionalPrice",
    "ispromotional": "isPromotional",
    "is_promotional": "isPromotional",
    "promotionlabel": "promotionLabel",
    "promotion_label": "promotionLabel",
    "fueltype": "fuelType",
    "fuel_type": "fuelType",
    "transmission": "transmission",
    "engine": "engine",
    "mileage": "mileage",
    "availability": "availability",
    "branchid": "branchId",
    "branch_id": "branchId",
    "ispublished": "isPublished",
    "is_published": "isPublished",
}


def _parse_bulk_rows(file: UploadFile) -> list[dict]:
    """Read a CSV or XLSX upload into a list of {header: value} dicts."""
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    is_xlsx = filename.endswith(".xlsx") or "spreadsheetml" in content_type
    # A .csv file labelled text/plain is still accepted (extension wins); a bare
    # text/plain upload without a .csv name is not.
    is_csv = filename.endswith(".csv") or content_type in ("text/csv", "application/csv")

    if is_xlsx:
        return _parse_xlsx(raw)
    if is_csv:
        return _parse_csv(raw)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported file type. Upload a .csv or .xlsx file.",
    )


def _parse_csv(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8-sig")  # tolerate a BOM from Excel-exported CSVs
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV has no header row")
    return [dict(row) for row in reader]


def _parse_xlsx(raw: bytes) -> list[dict]:
    import openpyxl  # lazy import — only needed for Excel uploads

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read the Excel file")
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spreadsheet is empty")
    headers = [str(h).strip() if h is not None else "" for h in header]

    parsed: list[dict] = []
    for values in rows:
        if values is None or all(v is None or str(v).strip() == "" for v in values):
            continue  # skip fully blank rows
        parsed.append({headers[i]: values[i] for i in range(min(len(headers), len(values)))})
    return parsed


def _row_to_create_payload(raw: dict) -> VehicleCreateIn:
    """Map a raw spreadsheet row to a validated VehicleCreateIn (pydantic coerces types)."""
    kwargs: dict = {}
    for header, value in raw.items():
        if header is None:
            continue
        field = _BULK_COLUMN_MAP.get(str(header).strip().lower())
        if not field or value is None:
            continue
        text = str(value).strip()
        if text == "":
            continue
        kwargs[field] = text
    return VehicleCreateIn(**kwargs)


def _format_validation_error(exc: ValidationError) -> list[str]:
    messages = []
    for err in exc.errors():
        location = ".".join(str(p) for p in err["loc"]) or "row"
        messages.append(f"{location}: {err['msg']}")
    return messages


def bulk_import_vehicles(db: Session, file: UploadFile, current_user: User) -> BulkImportResultOut:
    rows = _parse_bulk_rows(file)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data rows found in file")

    created_ids: list[str] = []
    errors: list[BulkImportRowErrorOut] = []

    for index, raw in enumerate(rows):
        line_number = index + 2  # +1 for the header row, +1 to be 1-based

        try:
            payload = _row_to_create_payload(raw)
        except ValidationError as exc:
            errors.append(BulkImportRowErrorOut(row=line_number, errors=_format_validation_error(exc)))
            continue

        # Isolate each row in a savepoint so one bad row never aborts the batch.
        savepoint = db.begin_nested()
        try:
            vehicle = _persist_new_vehicle(db, payload, current_user)
        except HTTPException as exc:
            savepoint.rollback()
            errors.append(BulkImportRowErrorOut(row=line_number, errors=[str(exc.detail)]))
            continue
        except IntegrityError:
            savepoint.rollback()
            errors.append(BulkImportRowErrorOut(row=line_number, errors=["Duplicate or invalid value"]))
            continue

        savepoint.commit()
        created_ids.append(vehicle.id)

    db.commit()
    return BulkImportResultOut(
        total=len(rows),
        created=len(created_ids),
        failed=len(errors),
        createdIds=created_ids,
        errors=errors,
    )
