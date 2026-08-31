"""Service Board maintenance status — intervals, vehicle evaluation, call lists."""

from __future__ import annotations

from datetime import datetime, timezone
from math import ceil

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.customers.models import OwnedVehicle
from app.domains.service.maintenance_schemas import (
    BoardSettingsOut,
    BoardSettingsUpdateIn,
    ItemMaintenanceStatusOut,
    MaintenanceVehicleSummaryOut,
    PaginatedMaintenanceSummaryOut,
    ServiceIntervalCreateIn,
    ServiceIntervalOut,
    ServiceIntervalUpdateIn,
    VehicleMaintenanceOut,
)
from app.domains.service.models import (
    ServiceBoardSettings,
    ServiceBoardVehicleModel,
    ServiceHistoryItem,
    ServiceHistoryLine,
    ServiceInterval,
    ServiceItem,
)
from app.domains.service.price_book_service import ensure_board_reference_data
from app.domains.service.schemas import _full_name, _vehicle_label
from app.domains.service.status import (
    IntervalConfig,
    LastServiceEvent,
    ThresholdConfig,
    evaluate_item_status,
    operation_qualifies,
)
from app.domains.shared.enums import ServiceIntervalKind, ServiceMaintenanceStatus, ServiceOperation
from app.domains.users.models import User


def _normalize_model_name(value: str) -> str:
    return value.strip().upper().replace("-", "").replace(" ", "")


def _resolve_board_model_id(db: Session, owned_model: str) -> str | None:
    ensure_board_reference_data(db)
    target = _normalize_model_name(owned_model)
    rows = db.query(ServiceBoardVehicleModel).filter(ServiceBoardVehicleModel.is_active.is_(True)).all()
    for row in rows:
        if _normalize_model_name(row.name) == target:
            return row.id
    return None


def get_or_create_settings(db: Session) -> ServiceBoardSettings:
    row = db.query(ServiceBoardSettings).order_by(ServiceBoardSettings.updated_at.desc()).first()
    if row is not None:
        return row
    row = ServiceBoardSettings()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_settings(db: Session) -> BoardSettingsOut:
    return BoardSettingsOut.from_model(get_or_create_settings(db))


def update_settings(db: Session, payload: BoardSettingsUpdateIn, *, actor: User) -> BoardSettingsOut:
    row = get_or_create_settings(db)
    if payload.due_soon_km is not None:
        row.due_soon_km = payload.due_soon_km
    if payload.due_soon_days is not None:
        row.due_soon_days = payload.due_soon_days
    if payload.mileage_stale_days is not None:
        row.mileage_stale_days = payload.mileage_stale_days
    row.updated_by_id = actor.id
    db.commit()
    db.refresh(row)
    return BoardSettingsOut.from_model(row)


def list_intervals(db: Session, *, service_item_id: str | None = None) -> list[ServiceIntervalOut]:
    q = (
        db.query(ServiceInterval)
        .options(joinedload(ServiceInterval.service_item), joinedload(ServiceInterval.vehicle_model))
        .order_by(ServiceInterval.created_at.desc())
    )
    if service_item_id:
        q = q.filter(ServiceInterval.service_item_id == service_item_id)
    return [ServiceIntervalOut.from_model(row) for row in q.all()]


def _validate_interval_payload(kind: str, interval_km: int | None, interval_months: int | None) -> ServiceIntervalKind:
    try:
        parsed = ServiceIntervalKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown interval kind") from exc

    if parsed in (ServiceIntervalKind.condition, ServiceIntervalKind.repair_only):
        return parsed

    if interval_km is None and interval_months is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduled and inspection intervals require intervalKm and/or intervalMonths.",
        )
    return parsed


def create_interval(db: Session, payload: ServiceIntervalCreateIn) -> ServiceIntervalOut:
    item = db.get(ServiceItem, payload.service_item_id)
    if item is None or not item.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service item not found")

    if payload.vehicle_model_id:
        model = db.get(ServiceBoardVehicleModel, payload.vehicle_model_id)
        if model is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board vehicle model not found")
    else:
        existing = (
            db.query(ServiceInterval.id)
            .filter(
                ServiceInterval.service_item_id == payload.service_item_id,
                ServiceInterval.vehicle_model_id.is_(None),
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A global interval for this item already exists.",
            )

    kind = _validate_interval_payload(payload.kind, payload.interval_km, payload.interval_months)

    row = ServiceInterval(
        service_item_id=payload.service_item_id,
        vehicle_model_id=payload.vehicle_model_id,
        kind=kind,
        interval_km=payload.interval_km,
        interval_months=payload.interval_months,
        is_active=True,
    )
    db.add(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interval already exists for this item/model") from exc
    db.refresh(row)
    row = (
        db.query(ServiceInterval)
        .options(joinedload(ServiceInterval.service_item), joinedload(ServiceInterval.vehicle_model))
        .filter(ServiceInterval.id == row.id)
        .one()
    )
    return ServiceIntervalOut.from_model(row)


def update_interval(db: Session, interval_id: str, payload: ServiceIntervalUpdateIn) -> ServiceIntervalOut:
    row = (
        db.query(ServiceInterval)
        .options(joinedload(ServiceInterval.service_item), joinedload(ServiceInterval.vehicle_model))
        .filter(ServiceInterval.id == interval_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interval not found")

    kind = row.kind.value if payload.kind is None else payload.kind
    interval_km = row.interval_km if payload.interval_km is None else payload.interval_km
    interval_months = row.interval_months if payload.interval_months is None else payload.interval_months
    row.kind = _validate_interval_payload(kind, interval_km, interval_months)
    row.interval_km = interval_km
    row.interval_months = interval_months
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.commit()
    db.refresh(row)
    return ServiceIntervalOut.from_model(row)


def _pick_interval(
    intervals: list[ServiceInterval],
    *,
    service_item_id: str,
    board_model_id: str | None,
) -> ServiceInterval | None:
    matches = [i for i in intervals if i.is_active and i.service_item_id == service_item_id]
    if not matches:
        return None
    if board_model_id:
        specific = next((i for i in matches if i.vehicle_model_id == board_model_id), None)
        if specific:
            return specific
    return next((i for i in matches if i.vehicle_model_id is None), None)


def _load_interval_map(db: Session) -> list[ServiceInterval]:
    return (
        db.query(ServiceInterval)
        .filter(ServiceInterval.is_active.is_(True))
        .all()
    )


def _latest_qualifying_events(
    lines: list[ServiceHistoryLine],
    *,
    kind: ServiceIntervalKind,
) -> dict[str, LastServiceEvent]:
    best: dict[str, LastServiceEvent] = {}
    for line in lines:
        parent = line.history_item
        if parent is None:
            continue
        if not operation_qualifies(kind, line.operation):
            continue
        event = LastServiceEvent(
            performed_at=parent.performed_at,
            mileage=parent.mileage,
            operation=line.operation,
        )
        current = best.get(line.service_item_id)
        if current is None or event.performed_at > current.performed_at:
            best[line.service_item_id] = event
    return best


def _vehicle_lines(db: Session, owned_vehicle_id: str) -> list[ServiceHistoryLine]:
    return (
        db.query(ServiceHistoryLine)
        .join(ServiceHistoryItem)
        .options(joinedload(ServiceHistoryLine.history_item))
        .filter(ServiceHistoryItem.owned_vehicle_id == owned_vehicle_id)
        .all()
    )


def evaluate_vehicle(
    db: Session,
    vehicle: OwnedVehicle,
    *,
    as_of: datetime | None = None,
) -> VehicleMaintenanceOut:
    as_of = as_of or datetime.now(timezone.utc)
    settings = get_or_create_settings(db)
    thresholds = ThresholdConfig(
        due_soon_km=settings.due_soon_km,
        due_soon_days=settings.due_soon_days,
        mileage_stale_days=settings.mileage_stale_days,
    )

    customer = vehicle.owner
    board_model_id = _resolve_board_model_id(db, vehicle.model)
    intervals = _load_interval_map(db)
    items = db.query(ServiceItem).filter(ServiceItem.is_active.is_(True)).order_by(ServiceItem.sort_order).all()
    lines = _vehicle_lines(db, vehicle.id)

    item_rows: list[ItemMaintenanceStatusOut] = []
    for item in items:
        interval_row = _pick_interval(intervals, service_item_id=item.id, board_model_id=board_model_id)
        interval_cfg = (
            IntervalConfig(
                kind=interval_row.kind,
                interval_km=interval_row.interval_km,
                interval_months=interval_row.interval_months,
            )
            if interval_row
            else None
        )

        last_event = None
        if interval_row is not None:
            events = _latest_qualifying_events(lines, kind=interval_row.kind)
            last_event = events.get(item.id)

        result = evaluate_item_status(
            interval=interval_cfg,
            last_event=last_event,
            current_mileage=vehicle.mileage,
            mileage_recorded_at=vehicle.updated_at,
            as_of=as_of,
            thresholds=thresholds,
        )

        last_op = last_event.operation.value if last_event else None
        item_rows.append(
            ItemMaintenanceStatusOut(
                serviceItemId=item.id,
                serviceItemCode=item.code,
                serviceItemName=item.name,
                serviceItemGroup=item.group.value,
                status=result.status.value,
                reason=result.reason,
                dueAtKm=result.due_at_km,
                dueAt=result.due_at.isoformat() if result.due_at else None,
                mileageStale=result.mileage_stale,
                lastPerformedAt=last_event.performed_at.isoformat() if last_event else None,
                lastMileage=last_event.mileage if last_event else None,
                lastOperation=last_op,
            )
        )

    return VehicleMaintenanceOut(
        ownedVehicleId=vehicle.id,
        customerId=customer.id,
        customerName=_full_name(customer),
        customerPhone=customer.phone_display,
        customerEmail=customer.email or "",
        vehicleLabel=_vehicle_label(vehicle),
        model=vehicle.model,
        currentMileage=vehicle.mileage,
        items=item_rows,
    )


def _summary_from_detail(detail: VehicleMaintenanceOut) -> MaintenanceVehicleSummaryOut:
    due_soon = sum(1 for i in detail.items if i.status == ServiceMaintenanceStatus.due_soon.value)
    overdue = sum(1 for i in detail.items if i.status == ServiceMaintenanceStatus.overdue.value)
    not_on_record = sum(1 for i in detail.items if i.status == ServiceMaintenanceStatus.not_on_record.value)

    worst = ServiceMaintenanceStatus.current.value
    severity = {
        ServiceMaintenanceStatus.current.value: 1,
        ServiceMaintenanceStatus.no_interval.value: 0,
        ServiceMaintenanceStatus.not_on_record.value: 0,
        ServiceMaintenanceStatus.due_soon.value: 2,
        ServiceMaintenanceStatus.overdue.value: 3,
    }
    top_reason = None
    for item in detail.items:
        if severity.get(item.status, 0) >= severity.get(worst, 0) and item.status in (
            ServiceMaintenanceStatus.due_soon.value,
            ServiceMaintenanceStatus.overdue.value,
        ):
            worst = item.status
            top_reason = item.reason

    return MaintenanceVehicleSummaryOut(
        ownedVehicleId=detail.ownedVehicleId,
        customerId=detail.customerId,
        customerName=detail.customerName,
        customerPhone=detail.customerPhone,
        customerEmail=detail.customerEmail,
        vehicleLabel=detail.vehicleLabel,
        model=detail.model,
        currentMileage=detail.currentMileage,
        worstStatus=worst,
        dueSoonCount=due_soon,
        overdueCount=overdue,
        notOnRecordCount=not_on_record,
        topReason=top_reason,
    )


def _list_vehicle_summaries(
    db: Session,
    *,
    include_vehicle,
    model: str | None,
    page: int,
    size: int,
) -> PaginatedMaintenanceSummaryOut:
    q = db.query(OwnedVehicle).options(selectinload(OwnedVehicle.owner))
    if model:
        q = q.filter(func.lower(OwnedVehicle.model) == model.strip().lower())

    vehicles = q.order_by(OwnedVehicle.updated_at.desc()).all()
    summaries: list[MaintenanceVehicleSummaryOut] = []
    for vehicle in vehicles:
        detail = evaluate_vehicle(db, vehicle)
        if include_vehicle(detail):
            summaries.append(_summary_from_detail(detail))

    total = len(summaries)
    pages = max(1, ceil(total / size)) if total else 1
    start = (page - 1) * size
    end = start + size
    return PaginatedMaintenanceSummaryOut(
        items=summaries[start:end],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def list_due_soon(db: Session, *, model: str | None = None, page: int = 1, size: int = 20) -> PaginatedMaintenanceSummaryOut:
    return _list_vehicle_summaries(
        db,
        include_vehicle=lambda detail: any(
            i.status == ServiceMaintenanceStatus.due_soon.value for i in detail.items
        ),
        model=model,
        page=page,
        size=size,
    )


def list_overdue(db: Session, *, model: str | None = None, page: int = 1, size: int = 20) -> PaginatedMaintenanceSummaryOut:
    return _list_vehicle_summaries(
        db,
        include_vehicle=lambda detail: any(
            i.status == ServiceMaintenanceStatus.overdue.value for i in detail.items
        ),
        model=model,
        page=page,
        size=size,
    )


def list_call_list(db: Session, *, model: str | None = None, page: int = 1, size: int = 20) -> PaginatedMaintenanceSummaryOut:
    return _list_vehicle_summaries(
        db,
        include_vehicle=lambda detail: any(
            i.status in (ServiceMaintenanceStatus.due_soon.value, ServiceMaintenanceStatus.overdue.value)
            for i in detail.items
        ),
        model=model,
        page=page,
        size=size,
    )


def get_vehicle_maintenance(db: Session, owned_vehicle_id: str) -> VehicleMaintenanceOut:
    vehicle = (
        db.query(OwnedVehicle)
        .options(selectinload(OwnedVehicle.owner))
        .filter(OwnedVehicle.id == owned_vehicle_id)
        .first()
    )
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return evaluate_vehicle(db, vehicle)
