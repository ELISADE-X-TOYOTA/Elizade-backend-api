import math
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.domains.customers.models import OwnedVehicle
from app.domains.inventory.models import Vehicle
from app.domains.ownership.models import VehicleOwnershipRequest
from app.domains.ownership.schemas import (
    DocumentUploadOut,
    OwnedVehicleOut,
    OwnershipRequestCreateIn,
    OwnershipRequestListItemOut,
    OwnershipRequestOut,
    OwnershipRequestUpdateIn,
    PaginatedOwnershipRequestsOut,
    VehiclePreviewOut,
    VinLookupOut,
    _normalize_vin,
)
from app.domains.ownership.storage import UnsupportedFileType, storage
from app.domains.shared.enums import AvailabilityStatus, OwnershipRequestStatus
from app.domains.users.models import User, UserRole
from app.domains.warranty import service as warranty_service

ACTIVE_REQUEST_STATUSES = (
    OwnershipRequestStatus.pending,
    OwnershipRequestStatus.pending_documents,
    OwnershipRequestStatus.under_review,
)
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")


def _validate_vin(vin: str) -> str:
    normalized = _normalize_vin(vin)
    if not VIN_PATTERN.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chassis/VIN number")
    return normalized


def _vehicle_preview(vehicle: Vehicle | None) -> VehiclePreviewOut | None:
    if not vehicle:
        return None
    primary = next((img for img in vehicle.images if img.is_primary), None)
    if primary is None and vehicle.images:
        primary = vehicle.images[0]
    return VehiclePreviewOut(
        inventoryVehicleId=vehicle.id,
        make=vehicle.make,
        model=vehicle.model,
        trim=vehicle.trim,
        year=vehicle.year,
        color=vehicle.color,
        availability=vehicle.availability.value if vehicle.availability else None,
    )


def _find_inventory_by_vin(db: Session, vin: str) -> Vehicle | None:
    return (
        db.query(Vehicle)
        .options(joinedload(Vehicle.images))
        .filter(Vehicle.vin == vin, Vehicle.deleted_at.is_(None))
        .one_or_none()
    )


def lookup_vin(db: Session, *, user_id: str, vin: str) -> VinLookupOut:
    normalized = _validate_vin(vin)

    existing_owned = db.query(OwnedVehicle).filter(OwnedVehicle.vin == normalized).one_or_none()
    if existing_owned:
        if existing_owned.user_id == user_id:
            return VinLookupOut(
                found=True,
                vin=normalized,
                canSubmit=False,
                reason="This vehicle is already in your garage",
                vehiclePreview=_vehicle_preview_from_owned(existing_owned),
            )
        return VinLookupOut(
            found=True,
            vin=normalized,
            canSubmit=False,
            reason="This vehicle is already linked to another account. Contact your branch for assistance.",
        )

    pending = (
        db.query(VehicleOwnershipRequest)
        .filter(
            VehicleOwnershipRequest.vin == normalized,
            VehicleOwnershipRequest.user_id == user_id,
            VehicleOwnershipRequest.status.in_(ACTIVE_REQUEST_STATUSES),
        )
        .one_or_none()
    )
    if pending:
        inv = db.get(Vehicle, pending.inventory_vehicle_id) if pending.inventory_vehicle_id else None
        return VinLookupOut(
            found=True,
            vin=normalized,
            canSubmit=False,
            reason="You already have a pending ownership request for this vehicle",
            vehiclePreview=_vehicle_preview(inv),
        )

    inventory = _find_inventory_by_vin(db, normalized)
    if inventory:
        return VinLookupOut(
            found=True,
            vin=normalized,
            canSubmit=True,
            reason=None,
            vehiclePreview=_vehicle_preview(inventory),
        )

    return VinLookupOut(
        found=False,
        vin=normalized,
        canSubmit=True,
        reason="Vehicle not found in our records. You can still submit a request with supporting documents.",
    )


def _vehicle_preview_from_owned(owned: OwnedVehicle) -> VehiclePreviewOut:
    return VehiclePreviewOut(
        inventoryVehicleId=owned.inventory_vehicle_id,
        make=owned.make,
        model=owned.model,
        trim=owned.trim,
        year=owned.year,
        color=owned.color,
        availability="owned",
    )


def submit_request(db: Session, user: User, payload: OwnershipRequestCreateIn) -> OwnershipRequestOut:
    if user.role != UserRole.customer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers only")

    normalized = _validate_vin(payload.vin)
    lookup = lookup_vin(db, user_id=user.id, vin=normalized)
    if not lookup.canSubmit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=lookup.reason or "Cannot submit request")

    inventory = _find_inventory_by_vin(db, normalized)
    row = VehicleOwnershipRequest(
        user_id=user.id,
        vin=normalized,
        registration_number=(payload.registration_number or "").strip() or None,
        inventory_vehicle_id=inventory.id if inventory else None,
        status=OwnershipRequestStatus.pending,
        document_urls=list(payload.document_urls or []),
        customer_notes=(payload.customer_notes or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return OwnershipRequestOut.from_model(row, preview=_vehicle_preview(inventory))


def list_my_requests(db: Session, user_id: str) -> list[OwnershipRequestOut]:
    rows = (
        db.query(VehicleOwnershipRequest)
        .filter(VehicleOwnershipRequest.user_id == user_id)
        .order_by(VehicleOwnershipRequest.created_at.desc())
        .all()
    )
    results: list[OwnershipRequestOut] = []
    for row in rows:
        inv = db.get(Vehicle, row.inventory_vehicle_id) if row.inventory_vehicle_id else None
        results.append(OwnershipRequestOut.from_model(row, preview=_vehicle_preview(inv)))
    return results


def list_my_vehicles(db: Session, user_id: str) -> list[OwnedVehicleOut]:
    rows = (
        db.query(OwnedVehicle)
        .filter(OwnedVehicle.user_id == user_id)
        .order_by(OwnedVehicle.is_primary.desc(), OwnedVehicle.created_at.desc())
        .all()
    )
    return [OwnedVehicleOut.from_model(r) for r in rows]


def upload_document(file: UploadFile) -> DocumentUploadOut:
    content = file.file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 10MB)")
    try:
        url = storage.save(content=content, filename=file.filename, content_type=file.content_type)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    return DocumentUploadOut(url=url)


def list_requests_admin(
    db: Session,
    *,
    status_filter: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedOwnershipRequestsOut:
    query = (
        db.query(VehicleOwnershipRequest)
        .options(joinedload(VehicleOwnershipRequest.customer))
        .order_by(VehicleOwnershipRequest.updated_at.desc())
    )
    if status_filter and status_filter.strip().lower() not in ("all", ""):
        raw = status_filter.strip().lower()
        if raw == "pending":
            query = query.filter(VehicleOwnershipRequest.status.in_(ACTIVE_REQUEST_STATUSES))
        else:
            try:
                query = query.filter(VehicleOwnershipRequest.status == OwnershipRequestStatus(raw))
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc

    total = query.count()
    offset = (page - 1) * size
    rows = query.offset(offset).limit(size).all()
    pages = max(1, math.ceil(total / size)) if total else 1

    items: list[OwnershipRequestListItemOut] = []
    for row in rows:
        inv = db.get(Vehicle, row.inventory_vehicle_id) if row.inventory_vehicle_id else None
        items.append(OwnershipRequestListItemOut.from_model(row, preview=_vehicle_preview(inv)))

    return PaginatedOwnershipRequestsOut(items=items, total=total, page=page, size=size, pages=pages)


def get_request_admin(db: Session, request_id: str) -> OwnershipRequestListItemOut:
    row = (
        db.query(VehicleOwnershipRequest)
        .options(joinedload(VehicleOwnershipRequest.customer))
        .filter(VehicleOwnershipRequest.id == request_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    inv = db.get(Vehicle, row.inventory_vehicle_id) if row.inventory_vehicle_id else None
    return OwnershipRequestListItemOut.from_model(row, preview=_vehicle_preview(inv))


def _create_owned_vehicle(
    db: Session,
    *,
    user_id: str,
    vin: str,
    registration_number: str,
    inventory: Vehicle | None,
) -> OwnedVehicle:
    now = datetime.now(timezone.utc)
    has_primary = (
        db.query(OwnedVehicle.id).filter(OwnedVehicle.user_id == user_id, OwnedVehicle.is_primary.is_(True)).first()
        is not None
    )

    if inventory:
        primary_img = next((img for img in inventory.images if img.is_primary), None)
        if primary_img is None and inventory.images:
            primary_img = inventory.images[0]
        owned = OwnedVehicle(
            user_id=user_id,
            inventory_vehicle_id=inventory.id,
            vin=vin,
            make=inventory.make,
            model=inventory.model,
            trim=inventory.trim,
            year=inventory.year,
            color=inventory.color,
            color_hex=inventory.color_hex,
            mileage=inventory.mileage or 0,
            registration_number=registration_number,
            purchase_date=now,
            image_url=primary_img.url if primary_img else None,
            is_primary=not has_primary,
        )
        if inventory.availability != AvailabilityStatus.sold:
            inventory.availability = AvailabilityStatus.sold
            inventory.is_published = False
    else:
        owned = OwnedVehicle(
            user_id=user_id,
            vin=vin,
            model="Toyota",
            trim="—",
            year=now.year,
            color="—",
            registration_number=registration_number,
            purchase_date=now,
            is_primary=not has_primary,
        )

    db.add(owned)
    db.flush()
    return owned


def update_request_admin(
    db: Session,
    request_id: str,
    payload: OwnershipRequestUpdateIn,
    *,
    reviewer_id: str,
) -> OwnershipRequestListItemOut:
    row = (
        db.query(VehicleOwnershipRequest)
        .options(joinedload(VehicleOwnershipRequest.customer))
        .filter(VehicleOwnershipRequest.id == request_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if payload.registration_number is not None:
        reg = payload.registration_number.strip()
        if reg:
            row.registration_number = reg

    if payload.admin_notes is not None:
        row.admin_notes = payload.admin_notes.strip() or None

    if payload.status is not None:
        try:
            new_status = OwnershipRequestStatus(payload.status.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc

        if new_status == OwnershipRequestStatus.approved:
            if row.status == OwnershipRequestStatus.approved:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request already approved")

            existing = db.query(OwnedVehicle).filter(OwnedVehicle.vin == row.vin).one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Vehicle is already linked to a customer account",
                )

            reg = (row.registration_number or "").strip() or f"PENDING-{row.vin[-6:]}"
            inventory = db.get(Vehicle, row.inventory_vehicle_id) if row.inventory_vehicle_id else None
            if inventory is None:
                inventory = _find_inventory_by_vin(db, row.vin)

            owned = _create_owned_vehicle(
                db,
                user_id=row.user_id,
                vin=row.vin,
                registration_number=reg,
                inventory=inventory,
            )
            row.owned_vehicle_id = owned.id
            row.inventory_vehicle_id = inventory.id if inventory else row.inventory_vehicle_id
            warranty_service.issue_standard_certificate(db, owned, issued_by_id=reviewer_id)

        row.status = new_status
        row.reviewed_by_id = reviewer_id
        row.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(row)
    inv = db.get(Vehicle, row.inventory_vehicle_id) if row.inventory_vehicle_id else None
    return OwnershipRequestListItemOut.from_model(row, preview=_vehicle_preview(inv))


def append_documents(db: Session, user_id: str, request_id: str, urls: list[str]) -> OwnershipRequestOut:
    row = (
        db.query(VehicleOwnershipRequest)
        .filter(VehicleOwnershipRequest.id == request_id, VehicleOwnershipRequest.user_id == user_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if row.status not in (OwnershipRequestStatus.pending, OwnershipRequestStatus.pending_documents):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot add documents to this request")

    merged = list(row.document_urls or [])
    for url in urls:
        if url and url not in merged:
            merged.append(url)
    row.document_urls = merged
    if row.status == OwnershipRequestStatus.pending_documents:
        row.status = OwnershipRequestStatus.pending
    db.commit()
    db.refresh(row)
    inv = db.get(Vehicle, row.inventory_vehicle_id) if row.inventory_vehicle_id else None
    return OwnershipRequestOut.from_model(row, preview=_vehicle_preview(inv))
