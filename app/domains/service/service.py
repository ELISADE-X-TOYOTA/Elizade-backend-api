from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import exists, func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.audit.models import AuditLog
from app.domains.branches.models import Branch
from app.domains.customers.models import OwnedVehicle
from app.domains.ownership import service as ownership_service
from app.domains.ownership.schemas import DocumentUploadOut
from app.domains.service.models import (
    AdditionalWorkRequest,
    ServiceAppointment,
    ServiceBay,
    ServiceHistoryItem,
    ServiceHistoryLine,
    ServiceInvoice,
    ServiceInvoiceLineItem,
    ServiceItem,
    ServiceJob,
    ServiceJobStage,
)
from app.domains.notifications import catalog
from app.domains.notifications.notify import safe_notify
from app.domains.service.schemas import (
    AdditionalWorkCreateIn,
    AdditionalWorkStatusUpdateIn,
    AppointmentBoardItemOut,
    AppointmentDetailOut,
    AppointmentStatusActionIn,
    AppointmentUpdateIn,
    CustomerAdditionalWorkDecisionIn,
    CustomerAppointmentCreateIn,
    CustomerAppointmentListItemOut,
    CustomerAppointmentRescheduleIn,
    CustomerServiceTrackOut,
    JobDetailOut,
    PaginatedHistoryOut,
    ServiceBayCreateIn,
    ServiceBayOut,
    ServiceBayUpdateIn,
    ServiceHistoryCreateIn,
    ServiceHistoryItemOut,
    ServiceHistoryLineIn,
    ServiceHistoryLinesReplaceIn,
    ServiceItemCreateIn,
    ServiceItemOut,
    ServiceItemUpdateIn,
    ServiceStatsOut,
    StageUpdateIn,
)
from app.domains.shared.enums import (
    AdditionalWorkStatus,
    AppointmentStatus,
    AuditAction,
    BranchType,
    ServiceHistoryLineSource,
    ServiceItemGroup,
    ServiceJobStatus,
    ServiceOperation,
    ServiceType,
)
from app.domains.shared.documents import normalize_document_urls
from app.domains.users.models import User, UserRole

# Default stage checklists seeded onto a job when an appointment is started.
STAGE_TEMPLATES: dict[ServiceType, list[str]] = {
    ServiceType.periodic: [
        "Vehicle received",
        "Inspection",
        "Oil & filter change",
        "Multi-point check",
        "Quality check",
        "Ready for collection",
    ],
    ServiceType.repair: [
        "Vehicle received",
        "Diagnosis",
        "Repair",
        "Testing",
        "Quality check",
        "Ready for collection",
    ],
    ServiceType.inspection: [
        "Vehicle received",
        "Inspection",
        "Report prepared",
        "Ready for collection",
    ],
    ServiceType.recall: [
        "Vehicle received",
        "Recall service performed",
        "Verification",
        "Ready for collection",
    ],
}
DEFAULT_STAGES = ["Vehicle received", "Service performed", "Quality check", "Ready for collection"]


def _today_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


# --------------------------------------------------------------------------- #
# Stats                                                                       #
# --------------------------------------------------------------------------- #

def get_stats(db: Session) -> ServiceStatsOut:
    start, end = _today_bounds()

    def count(*conditions) -> int:
        return (
            db.query(func.count(ServiceAppointment.id))
            .filter(
                ServiceAppointment.scheduled_at >= start,
                ServiceAppointment.scheduled_at < end,
                *conditions,
            )
            .scalar()
            or 0
        )

    return ServiceStatsOut(
        todaysAppointments=count(),
        inProgress=count(ServiceAppointment.status == AppointmentStatus.in_progress),
        awaitingApproval=count(ServiceAppointment.status == AppointmentStatus.awaiting_approval),
        completed=count(ServiceAppointment.status == AppointmentStatus.completed),
    )


# --------------------------------------------------------------------------- #
# Bays                                                                        #
# --------------------------------------------------------------------------- #

def list_bays(db: Session, *, branch_id: str | None = None) -> list[ServiceBayOut]:
    query = db.query(ServiceBay).options(joinedload(ServiceBay.branch)).order_by(ServiceBay.name.asc())
    if branch_id:
        query = query.filter(ServiceBay.branch_id == branch_id)
    return [ServiceBayOut.from_model(bay) for bay in query.all()]


def create_bay(db: Session, payload: ServiceBayCreateIn) -> ServiceBayOut:
    if db.get(Branch, payload.branch_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch not found")
    bay = ServiceBay(branch_id=payload.branch_id, name=payload.name.strip(), is_active=True)
    db.add(bay)
    db.commit()
    db.refresh(bay)
    return ServiceBayOut.from_model(bay)


def update_bay(db: Session, bay_id: str, payload: ServiceBayUpdateIn) -> ServiceBayOut:
    bay = db.get(ServiceBay, bay_id)
    if not bay:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service bay not found")
    if payload.name is not None:
        bay.name = payload.name.strip()
    if payload.is_active is not None:
        bay.is_active = payload.is_active
    db.commit()
    db.refresh(bay)
    return ServiceBayOut.from_model(bay)


# --------------------------------------------------------------------------- #
# Service-item catalogue                                                      #
# --------------------------------------------------------------------------- #

def _parse_item_group(value: str) -> ServiceItemGroup:
    try:
        return ServiceItemGroup(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(g.value for g in ServiceItemGroup)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid group. Allowed: {allowed}",
        ) from exc


def list_items(
    db: Session, *, group: str | None = None, is_active: bool | None = None
) -> list[ServiceItemOut]:
    query = db.query(ServiceItem).order_by(ServiceItem.sort_order.asc(), ServiceItem.name.asc())
    if group:
        query = query.filter(ServiceItem.group == _parse_item_group(group))
    if is_active is not None:
        query = query.filter(ServiceItem.is_active.is_(is_active))
    return [ServiceItemOut.from_model(row) for row in query.all()]


def create_item(db: Session, payload: ServiceItemCreateIn, *, actor_id: str) -> ServiceItemOut:
    existing = db.query(ServiceItem).filter(ServiceItem.code == payload.code).one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service item with that code already exists")
    item = ServiceItem(
        code=payload.code,
        name=payload.name.strip(),
        group=_parse_item_group(payload.group),
        description=payload.description.strip() if payload.description else None,
        sort_order=payload.sort_order,
        is_active=True,
    )
    db.add(item)
    db.flush()
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=AuditAction.create,
            entity_type="service_item",
            entity_id=item.id,
            changes={"code": item.code, "name": item.name, "group": item.group.value},
        )
    )
    db.commit()
    db.refresh(item)
    return ServiceItemOut.from_model(item)


def update_item(db: Session, item_id: str, payload: ServiceItemUpdateIn, *, actor_id: str) -> ServiceItemOut:
    item = db.get(ServiceItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service item not found")
    data = payload.model_dump(exclude_unset=True)
    changes: dict = {}
    if "name" in data and data["name"] is not None:
        item.name = data["name"].strip()
        changes["name"] = item.name
    if "group" in data and data["group"] is not None:
        item.group = _parse_item_group(data["group"])
        changes["group"] = item.group.value
    if "description" in data:
        item.description = data["description"].strip() if data["description"] else None
        changes["description"] = item.description
    if "sort_order" in data and data["sort_order"] is not None:
        item.sort_order = data["sort_order"]
        changes["sortOrder"] = item.sort_order
    if "is_active" in data and data["is_active"] is not None:
        item.is_active = data["is_active"]
        changes["isActive"] = item.is_active
    if changes:
        db.add(
            AuditLog(
                actor_id=actor_id,
                action=AuditAction.update,
                entity_type="service_item",
                entity_id=item.id,
                changes=changes,
            )
        )
    db.commit()
    db.refresh(item)
    return ServiceItemOut.from_model(item)


# --------------------------------------------------------------------------- #
# Appointments                                                                #
# --------------------------------------------------------------------------- #

_APPOINTMENT_LOADS = (
    joinedload(ServiceAppointment.customer),
    joinedload(ServiceAppointment.assigned_technician),
    joinedload(ServiceAppointment.owned_vehicle),
    joinedload(ServiceAppointment.branch),
    joinedload(ServiceAppointment.bay),
    joinedload(ServiceAppointment.job),
)


def _vehicle_label(vehicle) -> str:
    """How a customer refers to their own car: "2022 Toyota Hilux"."""
    if vehicle is None:
        return "your vehicle"
    return " ".join(str(p) for p in (vehicle.year, vehicle.make, vehicle.model) if p)


def _get_appointment(db: Session, appointment_id: str) -> ServiceAppointment:
    appt = (
        db.query(ServiceAppointment)
        .options(*_APPOINTMENT_LOADS)
        .filter(ServiceAppointment.id == appointment_id)
        .one_or_none()
    )
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


def list_appointments(
    db: Session,
    *,
    date: str | None = None,
    branch_id: str | None = None,
    status_filter: str | None = None,
    bay_id: str | None = None,
) -> list[AppointmentBoardItemOut]:
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date (expected YYYY-MM-DD)")
        start = day
    else:
        start, _ = _today_bounds()
    end = start + timedelta(days=1)

    query = (
        db.query(ServiceAppointment)
        .options(*_APPOINTMENT_LOADS)
        .filter(ServiceAppointment.scheduled_at >= start, ServiceAppointment.scheduled_at < end)
        .order_by(ServiceAppointment.scheduled_at.asc())
    )
    if branch_id:
        query = query.filter(ServiceAppointment.branch_id == branch_id)
    if bay_id:
        query = query.filter(ServiceAppointment.bay_id == bay_id)
    if status_filter and status_filter.strip().lower() != "all":
        try:
            wanted = AppointmentStatus(status_filter.strip().lower())
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter")
        query = query.filter(ServiceAppointment.status == wanted)

    return [AppointmentBoardItemOut.from_model(a) for a in query.all()]


def get_appointment(db: Session, appointment_id: str) -> AppointmentDetailOut:
    return AppointmentDetailOut.from_model(_get_appointment(db, appointment_id))


def update_appointment(db: Session, appointment_id: str, payload: AppointmentUpdateIn) -> AppointmentDetailOut:
    appt = _get_appointment(db, appointment_id)
    data = payload.model_dump(exclude_unset=True)

    if "scheduled_at" in data and data["scheduled_at"] is not None:
        appt.scheduled_at = data["scheduled_at"]

    if "bay_id" in data:
        value = data["bay_id"]
        if value in (None, ""):
            appt.bay_id = None
        else:
            bay = db.get(ServiceBay, value)
            if not bay:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bay not found")
            if not bay.is_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bay is inactive")
            if bay.branch_id != appt.branch_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bay belongs to a different branch")
            appt.bay_id = bay.id
        if appt.job:
            appt.job.bay_id = appt.bay_id

    if "assigned_technician_id" in data:
        value = data["assigned_technician_id"]
        if value in (None, ""):
            appt.assigned_technician_id = None
        else:
            tech = db.get(User, value)
            if not tech or tech.role not in (UserRole.staff, UserRole.admin):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid technician")
            if not tech.is_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Technician account is deactivated")
            appt.assigned_technician_id = tech.id

    if "estimated_completion" in data:
        appt.estimated_completion = data["estimated_completion"]
        if appt.job:
            appt.job.estimated_completion = data["estimated_completion"]

    db.commit()
    return get_appointment(db, appointment_id)


# Allowed source statuses for each status action.
_STATUS_TRANSITIONS = {
    "confirm": (AppointmentStatus.requested,),
    "start": (AppointmentStatus.confirmed,),
    "complete": (AppointmentStatus.in_progress, AppointmentStatus.awaiting_approval),
    "cancel": (
        AppointmentStatus.requested,
        AppointmentStatus.confirmed,
        AppointmentStatus.in_progress,
        AppointmentStatus.awaiting_approval,
    ),
}


def change_appointment_status(
    db: Session,
    appointment_id: str,
    payload: AppointmentStatusActionIn,
    *,
    actor: User | None = None,
) -> AppointmentDetailOut:
    appt = _get_appointment(db, appointment_id)
    action = payload.action.strip().lower()
    if action not in _STATUS_TRANSITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Allowed: confirm, start, complete, cancel",
        )
    if appt.status not in _STATUS_TRANSITIONS[action]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot {action} an appointment with status '{appt.status.value}'",
        )
    if action != "complete" and (payload.lines or payload.mileage is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lines and mileage can only be supplied when completing a service",
        )

    now = datetime.now(timezone.utc)
    if action == "confirm":
        appt.status = AppointmentStatus.confirmed
    elif action == "start":
        appt.status = AppointmentStatus.in_progress
        _start_job(db, appt, now)
    elif action == "complete":
        appt.status = AppointmentStatus.completed
        _complete_job(
            db,
            appt,
            now,
            lines=payload.lines,
            mileage=payload.mileage,
            actor_id=actor.id if actor else None,
        )
    elif action == "cancel":
        appt.status = AppointmentStatus.cancelled
        if appt.job and appt.job.status not in (ServiceJobStatus.completed, ServiceJobStatus.cancelled):
            appt.job.status = ServiceJobStatus.cancelled

    db.commit()

    # After the commit — the status change stands whether or not the customer
    # can be reached.
    if action == "confirm":
        safe_notify(
            db,
            user=appt.customer,
            event=catalog.SERVICE_APPOINTMENT_CONFIRMED,
            context={
                "service_type": appt.service_type.value.replace("_", " ").title(),
                "vehicle_label": _vehicle_label(appt.owned_vehicle),
                "when": appt.scheduled_at.strftime("%d %b at %H:%M"),
                "branch": appt.branch.name if appt.branch else "your branch",
            },
        )
    elif action == "complete":
        safe_notify(
            db,
            user=appt.customer,
            event=catalog.VEHICLE_READY_FOR_COLLECTION,
            context={
                "vehicle_label": _vehicle_label(appt.owned_vehicle),
                "branch": appt.branch.name if appt.branch else "your branch",
                "appointment_id": appt.id,
            },
        )

    return get_appointment(db, appointment_id)


def _start_job(db: Session, appt: ServiceAppointment, now: datetime) -> None:
    if appt.job is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A job already exists for this appointment")

    job = ServiceJob(
        appointment_id=appt.id,
        bay_id=appt.bay_id,
        status=ServiceJobStatus.in_progress,
        started_at=now,
        estimated_completion=appt.estimated_completion,
    )
    db.add(job)
    db.flush()

    labels = STAGE_TEMPLATES.get(appt.service_type, DEFAULT_STAGES)
    for index, label in enumerate(labels):
        db.add(ServiceJobStage(job_id=job.id, label=label, sort_order=index, completed=False))


def _complete_job(
    db: Session,
    appt: ServiceAppointment,
    now: datetime,
    *,
    lines: list[ServiceHistoryLineIn] | None = None,
    mileage: int | None = None,
    actor_id: str | None = None,
) -> None:
    job = appt.job
    invoice_total = Decimal("0")

    if job is not None:
        job.status = ServiceJobStatus.completed
        job.completed_at = now

        if job.invoice is None:
            approved = [w for w in job.additional_work if w.status == AdditionalWorkStatus.approved]
            subtotal = sum((w.cost for w in approved), Decimal("0"))
            invoice = ServiceInvoice(job_id=job.id, subtotal=subtotal, tax=Decimal("0"), total=subtotal)
            db.add(invoice)
            db.flush()
            for index, work in enumerate(approved):
                db.add(
                    ServiceInvoiceLineItem(
                        invoice_id=invoice.id,
                        description=work.description,
                        amount=work.cost,
                        sort_order=index,
                    )
                )
            invoice_total = subtotal

    recorded_mileage = appt.mileage_at_booking if mileage is None else mileage
    _raise_vehicle_mileage(appt.owned_vehicle, recorded_mileage)

    history = ServiceHistoryItem(
        owned_vehicle_id=appt.owned_vehicle_id,
        user_id=appt.user_id,
        appointment_id=appt.id,
        branch_id=appt.branch_id,
        service_type=appt.service_type.value,
        performed_at=now,
        mileage=recorded_mileage,
        description=appt.issue_description,
        cost=invoice_total,
    )
    db.add(history)
    db.flush()
    _add_history_lines(
        db,
        history_id=history.id,
        payloads=lines or [],
        source=ServiceHistoryLineSource.job_completion,
        actor_id=actor_id,
    )


# --------------------------------------------------------------------------- #
# Jobs                                                                        #
# --------------------------------------------------------------------------- #

def _get_job(db: Session, job_id: str) -> ServiceJob:
    job = (
        db.query(ServiceJob)
        .options(
            joinedload(ServiceJob.appointment).joinedload(ServiceAppointment.customer),
            joinedload(ServiceJob.appointment).joinedload(ServiceAppointment.owned_vehicle),
            joinedload(ServiceJob.bay),
            selectinload(ServiceJob.stages),
            selectinload(ServiceJob.additional_work),
            joinedload(ServiceJob.invoice).selectinload(ServiceInvoice.line_items),
        )
        .filter(ServiceJob.id == job_id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def get_job(db: Session, job_id: str) -> JobDetailOut:
    return JobDetailOut.from_model(_get_job(db, job_id))


def update_job_stage(db: Session, job_id: str, stage_id: str, payload: StageUpdateIn) -> JobDetailOut:
    job = _get_job(db, job_id)
    stage = next((s for s in job.stages if s.id == stage_id), None)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    stage.completed = payload.completed
    stage.completed_at = datetime.now(timezone.utc) if payload.completed else None
    db.commit()
    return get_job(db, job_id)


def add_additional_work(db: Session, job_id: str, payload: AdditionalWorkCreateIn) -> JobDetailOut:
    job = _get_job(db, job_id)
    if job.status not in (ServiceJobStatus.in_progress, ServiceJobStatus.awaiting_approval):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Additional work can only be added to a job that is in progress",
        )

    db.add(
        AdditionalWorkRequest(
            job_id=job.id,
            description=payload.description.strip(),
            cost=payload.cost,
            status=AdditionalWorkStatus.pending_approval,
        )
    )
    # Pause the job for customer approval and reflect that on the appointment.
    job.status = ServiceJobStatus.awaiting_approval
    if job.appointment and job.appointment.status == AppointmentStatus.in_progress:
        job.appointment.status = AppointmentStatus.awaiting_approval

    db.commit()

    appt = job.appointment
    if appt is not None:
        safe_notify(
            db,
            user=appt.customer,
            event=catalog.EXTRA_WORK_NEEDS_APPROVAL,
            context={
                "vehicle_label": _vehicle_label(appt.owned_vehicle),
                "description": payload.description,
                "amount": f"NGN {payload.cost:,.0f}",
                "appointment_id": appt.id,
            },
        )
    return get_job(db, job_id)


def update_additional_work(
    db: Session, job_id: str, work_id: str, payload: AdditionalWorkStatusUpdateIn
) -> JobDetailOut:
    job = _get_job(db, job_id)
    work = next((w for w in job.additional_work if w.id == work_id), None)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Additional work not found")

    try:
        new_status = AdditionalWorkStatus(payload.status.strip().lower())
    except ValueError:
        allowed = ", ".join(s.value for s in AdditionalWorkStatus)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Allowed: {allowed}")

    return _set_additional_work_status(db, job, work, new_status)


def _set_additional_work_status(
    db: Session, job: ServiceJob, work: AdditionalWorkRequest, new_status: AdditionalWorkStatus
) -> JobDetailOut:
    work.status = new_status
    if new_status in (AdditionalWorkStatus.approved, AdditionalWorkStatus.rejected) and not work.customer_responded_at:
        work.customer_responded_at = datetime.now(timezone.utc)

    still_pending = any(w.status == AdditionalWorkStatus.pending_approval for w in job.additional_work)
    if not still_pending and job.status == ServiceJobStatus.awaiting_approval:
        job.status = ServiceJobStatus.in_progress
        if job.appointment and job.appointment.status == AppointmentStatus.awaiting_approval:
            job.appointment.status = AppointmentStatus.in_progress

    db.commit()
    return get_job(db, job.id)


# --------------------------------------------------------------------------- #
# Customer portal                                                             #
# --------------------------------------------------------------------------- #

_CUSTOMER_APPOINTMENT_LOADS = (
    joinedload(ServiceAppointment.owned_vehicle),
    joinedload(ServiceAppointment.branch),
    joinedload(ServiceAppointment.job).selectinload(ServiceJob.additional_work),
)

_CUSTOMER_APPOINTMENT_CHANGEABLE_STATUSES = (
    AppointmentStatus.requested,
    AppointmentStatus.confirmed,
)


def _future_datetime(value: datetime) -> datetime:
    """Return an aware UTC datetime and reject slots that have already passed."""
    scheduled = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    scheduled = scheduled.astimezone(timezone.utc)
    if scheduled <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scheduled time must be in the future")
    return scheduled


def _ensure_vehicle_slot_available(
    db: Session, *, vehicle_id: str, scheduled_at: datetime, exclude_id: str | None = None
) -> None:
    """A vehicle cannot have two active appointments in the same time slot."""
    query = db.query(ServiceAppointment.id).filter(
        ServiceAppointment.owned_vehicle_id == vehicle_id,
        ServiceAppointment.scheduled_at == scheduled_at,
        ServiceAppointment.status != AppointmentStatus.cancelled,
    )
    if exclude_id:
        query = query.filter(ServiceAppointment.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This vehicle already has an appointment at that time",
        )


def _get_customer_appointment(db: Session, customer_id: str, appointment_id: str) -> ServiceAppointment:
    appt = (
        db.query(ServiceAppointment)
        .options(*_CUSTOMER_APPOINTMENT_LOADS)
        .filter(ServiceAppointment.id == appointment_id, ServiceAppointment.user_id == customer_id)
        .one_or_none()
    )
    if not appt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


def list_customer_appointments(db: Session, customer_id: str) -> list[CustomerAppointmentListItemOut]:
    rows = (
        db.query(ServiceAppointment)
        .options(*_CUSTOMER_APPOINTMENT_LOADS)
        .filter(ServiceAppointment.user_id == customer_id)
        .order_by(ServiceAppointment.scheduled_at.desc())
        .limit(50)
        .all()
    )
    return [CustomerAppointmentListItemOut.from_model(a) for a in rows]


def create_customer_appointment(
    db: Session, user: User, payload: CustomerAppointmentCreateIn
) -> CustomerAppointmentListItemOut:
    attachment_urls = normalize_document_urls(payload.attachment_urls)
    vehicle = (
        db.query(OwnedVehicle)
        .filter(OwnedVehicle.id == payload.owned_vehicle_id, OwnedVehicle.user_id == user.id)
        .one_or_none()
    )
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    branch = db.get(Branch, payload.branch_id)
    if not branch or not branch.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch not found")
    if branch.type == BranchType.showroom:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a service centre branch")

    try:
        service_type = ServiceType(payload.service_type.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid service type") from exc

    scheduled = _future_datetime(payload.scheduled_at)
    _ensure_vehicle_slot_available(db, vehicle_id=vehicle.id, scheduled_at=scheduled)

    appt = ServiceAppointment(
        user_id=user.id,
        owned_vehicle_id=vehicle.id,
        branch_id=branch.id,
        service_type=service_type,
        scheduled_at=scheduled,
        status=AppointmentStatus.requested,
        issue_description=payload.issue_description.strip(),
        attachment_urls=attachment_urls,
        mileage_at_booking=payload.mileage_at_booking,
    )
    db.add(appt)
    db.commit()
    loaded = (
        db.query(ServiceAppointment)
        .options(*_CUSTOMER_APPOINTMENT_LOADS)
        .filter(ServiceAppointment.id == appt.id)
        .one()
    )
    return CustomerAppointmentListItemOut.from_model(loaded)


def reschedule_customer_appointment(
    db: Session, customer_id: str, appointment_id: str, payload: CustomerAppointmentRescheduleIn
) -> CustomerAppointmentListItemOut:
    appt = _get_customer_appointment(db, customer_id, appointment_id)
    if appt.status not in _CUSTOMER_APPOINTMENT_CHANGEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reschedule an appointment with status '{appt.status.value}'",
        )

    scheduled = _future_datetime(payload.scheduled_at)
    _ensure_vehicle_slot_available(
        db,
        vehicle_id=appt.owned_vehicle_id,
        scheduled_at=scheduled,
        exclude_id=appt.id,
    )
    appt.scheduled_at = scheduled
    db.commit()
    return CustomerAppointmentListItemOut.from_model(_get_customer_appointment(db, customer_id, appointment_id))


def cancel_customer_appointment(
    db: Session, customer_id: str, appointment_id: str
) -> CustomerAppointmentListItemOut:
    appt = _get_customer_appointment(db, customer_id, appointment_id)
    if appt.status not in _CUSTOMER_APPOINTMENT_CHANGEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel an appointment with status '{appt.status.value}'",
        )

    appt.status = AppointmentStatus.cancelled
    if appt.job and appt.job.status not in (ServiceJobStatus.completed, ServiceJobStatus.cancelled):
        appt.job.status = ServiceJobStatus.cancelled
    db.commit()
    return CustomerAppointmentListItemOut.from_model(_get_customer_appointment(db, customer_id, appointment_id))


def upload_customer_appointment_attachment(file: UploadFile) -> DocumentUploadOut:
    """Upload appointment evidence through the shared document storage backend."""
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    file.file.seek(0)
    return ownership_service.upload_document(file)


def list_customer_history(
    db: Session,
    customer_id: str,
    *,
    owned_vehicle_id: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedHistoryOut:
    if owned_vehicle_id:
        owned = (
            db.query(OwnedVehicle)
            .filter(OwnedVehicle.id == owned_vehicle_id, OwnedVehicle.user_id == customer_id)
            .one_or_none()
        )
        if not owned:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    result = list_history(db, customer_id=customer_id, owned_vehicle_id=owned_vehicle_id, page=page, size=size)
    # Staff line notes/amounts stay off the customer contract.
    for item in result.items:
        item.lines = []
    return result


def get_customer_service_track(db: Session, customer_id: str, appointment_id: str) -> CustomerServiceTrackOut:
    appt = _get_customer_appointment(db, customer_id, appointment_id)
    job_out = get_job(db, appt.job.id) if appt.job else None
    return CustomerServiceTrackOut(appointment=get_appointment(db, appointment_id), job=job_out)


def customer_respond_additional_work(
    db: Session,
    customer_id: str,
    job_id: str,
    work_id: str,
    payload: CustomerAdditionalWorkDecisionIn,
) -> JobDetailOut:
    job = _get_job(db, job_id)
    if not job.appointment or job.appointment.user_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    work = next((w for w in job.additional_work if w.id == work_id), None)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Additional work not found")
    if work.status != AdditionalWorkStatus.pending_approval:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This additional work request has already been responded to",
        )

    decision = payload.decision.strip().lower()
    if decision == "approve":
        new_status = AdditionalWorkStatus.approved
    elif decision == "reject":
        new_status = AdditionalWorkStatus.rejected
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decision. Allowed: approve, reject")

    return _set_additional_work_status(db, job, work, new_status)


# --------------------------------------------------------------------------- #
# Service history                                                             #
# --------------------------------------------------------------------------- #

def _parse_operation(value: str) -> ServiceOperation:
    try:
        return ServiceOperation(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(op.value for op in ServiceOperation)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid operation. Allowed: {allowed}",
        ) from exc


def _raise_vehicle_mileage(vehicle: OwnedVehicle | None, mileage: int) -> None:
    """Raise the latest-known odometer. Never decrease it from a service write."""
    if vehicle is None:
        return
    if mileage > vehicle.mileage:
        vehicle.mileage = mileage


def _add_history_lines(
    db: Session,
    *,
    history_id: str,
    payloads: list[ServiceHistoryLineIn],
    source: ServiceHistoryLineSource,
    actor_id: str | None,
) -> None:
    if not payloads:
        return
    item_ids = [row.service_item_id for row in payloads]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate service items in the same record",
        )

    rows = db.query(ServiceItem).filter(ServiceItem.id.in_(item_ids)).all()
    found = {row.id: row for row in rows}
    missing = [item_id for item_id in item_ids if item_id not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service item not found")
    inactive = [item_id for item_id, row in found.items() if not row.is_active]
    if inactive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service item is inactive")

    for payload in payloads:
        notes = payload.notes.strip() if payload.notes else None
        db.add(
            ServiceHistoryLine(
                history_item_id=history_id,
                service_item_id=payload.service_item_id,
                operation=_parse_operation(payload.operation),
                quantity=payload.quantity,
                amount=payload.amount,
                notes=notes or None,
                source=source,
                is_backfilled=False,
                backfill_confidence=None,
                created_by_id=actor_id,
            )
        )


_HISTORY_LOADS = (
    joinedload(ServiceHistoryItem.owned_vehicle),
    joinedload(ServiceHistoryItem.customer),
    joinedload(ServiceHistoryItem.branch),
    selectinload(ServiceHistoryItem.lines).joinedload(ServiceHistoryLine.service_item),
)


def _history_item_query(db: Session):
    return db.query(ServiceHistoryItem).options(*_HISTORY_LOADS)


def _get_history_item(db: Session, history_id: str) -> ServiceHistoryItem:
    item = _history_item_query(db).filter(ServiceHistoryItem.id == history_id).one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History record not found")
    return item


def list_history(
    db: Session,
    *,
    customer_id: str | None = None,
    owned_vehicle_id: str | None = None,
    unmapped_only: bool = False,
    page: int = 1,
    size: int = 20,
) -> PaginatedHistoryOut:
    query = _history_item_query(db).order_by(ServiceHistoryItem.performed_at.desc())
    if customer_id:
        query = query.filter(ServiceHistoryItem.user_id == customer_id)
    if owned_vehicle_id:
        query = query.filter(ServiceHistoryItem.owned_vehicle_id == owned_vehicle_id)
    if unmapped_only:
        query = query.filter(~exists().where(ServiceHistoryLine.history_item_id == ServiceHistoryItem.id))

    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    pages = max(1, ceil(total / size)) if total else 1

    return PaginatedHistoryOut(
        items=[ServiceHistoryItemOut.from_model(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def get_history(db: Session, history_id: str) -> ServiceHistoryItemOut:
    return ServiceHistoryItemOut.from_model(_get_history_item(db, history_id))


def create_history(
    db: Session, payload: ServiceHistoryCreateIn, *, actor: User | None = None
) -> ServiceHistoryItemOut:
    vehicle = db.get(OwnedVehicle, payload.owned_vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vehicle not found")
    if db.get(Branch, payload.branch_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch not found")

    _raise_vehicle_mileage(vehicle, payload.mileage)

    item = ServiceHistoryItem(
        owned_vehicle_id=vehicle.id,
        user_id=vehicle.user_id,
        appointment_id=None,
        branch_id=payload.branch_id,
        service_type=payload.service_type.strip(),
        performed_at=payload.performed_at,
        mileage=payload.mileage,
        description=payload.description.strip(),
        cost=payload.cost,
    )
    db.add(item)
    db.flush()
    _add_history_lines(
        db,
        history_id=item.id,
        payloads=payload.lines,
        source=ServiceHistoryLineSource.manual_entry,
        actor_id=actor.id if actor else None,
    )
    db.commit()
    return get_history(db, item.id)


def replace_history_lines(
    db: Session,
    history_id: str,
    payload: ServiceHistoryLinesReplaceIn,
    *,
    actor: User,
) -> ServiceHistoryItemOut:
    item = _get_history_item(db, history_id)
    if payload.mileage is not None:
        item.mileage = payload.mileage
        _raise_vehicle_mileage(item.owned_vehicle, payload.mileage)

    for line in list(item.lines):
        db.delete(line)
    db.flush()

    _add_history_lines(
        db,
        history_id=item.id,
        payloads=payload.lines,
        source=ServiceHistoryLineSource.manual_entry,
        actor_id=actor.id,
    )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action=AuditAction.update,
            entity_type="service_history_item",
            entity_id=item.id,
            changes={"lineCount": len(payload.lines), "mileage": item.mileage},
        )
    )
    db.commit()
    return get_history(db, item.id)


def delete_history(db: Session, history_id: str) -> None:
    item = db.get(ServiceHistoryItem, history_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History record not found")
    db.delete(item)
    db.commit()
