import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.domains.customers.models import OwnedVehicle
from app.domains.shared.enums import (
    ClaimStatus,
    RecallSeverity,
    WarrantyCertificateStatus,
    WarrantyCertificateType,
)
from app.domains.users.models import User, UserRole
from app.domains.warranty.models import RecallCampaign, RecallVehicle, WarrantyCertificate, WarrantyClaim
from app.domains.warranty.schemas import (
    CertificateCreateIn,
    ClaimUpdateIn,
    OwnedVehicleOptionOut,
    PaginatedClaimsOut,
    RecallCampaignOut,
    RecallCreateIn,
    RecallNotifyOut,
    WarrantyCertificateOut,
    WarrantyClaimListItemOut,
    WarrantySummaryOut,
)

TERMINAL_CLAIM_STATUSES = {ClaimStatus.approved, ClaimStatus.rejected, ClaimStatus.closed}
PENDING_CLAIM_STATUSES = (ClaimStatus.submitted, ClaimStatus.under_review, ClaimStatus.escalated)


def get_summary(db: Session) -> WarrantySummaryOut:
    pending = db.query(func.count(WarrantyClaim.id)).filter(WarrantyClaim.status.in_(PENDING_CLAIM_STATUSES)).scalar() or 0
    escalated = (
        db.query(func.count(WarrantyClaim.id)).filter(WarrantyClaim.status == ClaimStatus.escalated).scalar() or 0
    )
    active_certs = (
        db.query(func.count(WarrantyCertificate.id))
        .filter(WarrantyCertificate.status == WarrantyCertificateStatus.active)
        .scalar()
        or 0
    )
    active_recalls = db.query(func.count(RecallCampaign.id)).filter(RecallCampaign.is_active.is_(True)).scalar() or 0
    return WarrantySummaryOut(
        pendingClaims=pending,
        activeCertificates=active_certs,
        activeRecalls=active_recalls,
        escalatedClaims=escalated,
    )


def list_claims(
    db: Session,
    *,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedClaimsOut:
    query = (
        db.query(WarrantyClaim)
        .options(
            joinedload(WarrantyClaim.customer),
            joinedload(WarrantyClaim.owned_vehicle),
            joinedload(WarrantyClaim.assigned_to),
        )
        .order_by(WarrantyClaim.updated_at.desc())
    )

    if status and status.strip().lower() not in ("all", ""):
        raw = status.strip().lower()
        if raw == "pending":
            query = query.filter(WarrantyClaim.status.in_(PENDING_CLAIM_STATUSES))
        else:
            try:
                query = query.filter(WarrantyClaim.status == ClaimStatus(raw))
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter") from exc

    total = query.count()
    offset = (page - 1) * size
    rows = query.offset(offset).limit(size).all()
    pages = max(1, math.ceil(total / size)) if total else 1

    return PaginatedClaimsOut(
        items=[WarrantyClaimListItemOut.from_model(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def get_claim(db: Session, claim_id: str) -> WarrantyClaimListItemOut:
    claim = (
        db.query(WarrantyClaim)
        .options(
            joinedload(WarrantyClaim.customer),
            joinedload(WarrantyClaim.owned_vehicle),
            joinedload(WarrantyClaim.assigned_to),
        )
        .filter(WarrantyClaim.id == claim_id)
        .one_or_none()
    )
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return WarrantyClaimListItemOut.from_model(claim)


def update_claim(db: Session, claim_id: str, payload: ClaimUpdateIn) -> WarrantyClaimListItemOut:
    claim = (
        db.query(WarrantyClaim)
        .options(
            joinedload(WarrantyClaim.customer),
            joinedload(WarrantyClaim.owned_vehicle),
            joinedload(WarrantyClaim.assigned_to),
        )
        .filter(WarrantyClaim.id == claim_id)
        .one_or_none()
    )
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    if payload.status is not None:
        try:
            new_status = ClaimStatus(payload.status.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
        claim.status = new_status
        if new_status in TERMINAL_CLAIM_STATUSES and not claim.resolved_at:
            claim.resolved_at = datetime.now(timezone.utc)

    if payload.resolution_notes is not None:
        claim.resolution_notes = payload.resolution_notes.strip() or None

    if payload.assigned_to_id is not None:
        if payload.assigned_to_id == "":
            claim.assigned_to_id = None
        else:
            assignee = db.get(User, payload.assigned_to_id)
            if not assignee or assignee.role not in (UserRole.staff, UserRole.admin):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee")
            claim.assigned_to_id = assignee.id

    db.commit()
    db.refresh(claim)
    return WarrantyClaimListItemOut.from_model(claim)


def list_owned_vehicle_options(db: Session, *, q: str | None = None) -> list[OwnedVehicleOptionOut]:
    query = (
        db.query(OwnedVehicle)
        .options(joinedload(OwnedVehicle.owner))
        .join(User, OwnedVehicle.user_id == User.id)
        .filter(User.role == UserRole.customer)
        .order_by(OwnedVehicle.created_at.desc())
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            (OwnedVehicle.registration_number.ilike(term))
            | (OwnedVehicle.vin.ilike(term))
            | (OwnedVehicle.model.ilike(term))
            | (User.first_name.ilike(term))
            | (User.last_name.ilike(term))
        )
    rows = query.limit(50).all()
    return [OwnedVehicleOptionOut.from_model(r) for r in rows]


def create_certificate(db: Session, payload: CertificateCreateIn, *, issued_by_id: str | None) -> WarrantyCertificateOut:
    vehicle = (
        db.query(OwnedVehicle)
        .options(joinedload(OwnedVehicle.owner))
        .filter(OwnedVehicle.id == payload.owned_vehicle_id)
        .one_or_none()
    )
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    try:
        cert_type = WarrantyCertificateType(payload.type.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid certificate type") from exc

    now = datetime.now(timezone.utc)
    coverage_start = now
    coverage_end = now + timedelta(days=365 if cert_type == WarrantyCertificateType.standard else 730)
    if payload.coverage_start:
        coverage_start = datetime.fromisoformat(payload.coverage_start.replace("Z", "+00:00"))
    if payload.coverage_end:
        coverage_end = datetime.fromisoformat(payload.coverage_end.replace("Z", "+00:00"))

    cert_number = f"ELZ-WTY-{uuid.uuid4().hex[:8].upper()}"
    row = WarrantyCertificate(
        owned_vehicle_id=vehicle.id,
        user_id=vehicle.user_id,
        certificate_number=cert_number,
        type=cert_type,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        status=WarrantyCertificateStatus.active,
        coverage_details=payload.coverage_details or ["Engine", "Transmission", "Electrical"],
        issued_by_id=issued_by_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    loaded = (
        db.query(WarrantyCertificate)
        .options(
            joinedload(WarrantyCertificate.customer),
            joinedload(WarrantyCertificate.owned_vehicle),
        )
        .filter(WarrantyCertificate.id == row.id)
        .one()
    )
    return WarrantyCertificateOut.from_model(loaded)


def list_certificates(db: Session) -> list[WarrantyCertificateOut]:
    rows = (
        db.query(WarrantyCertificate)
        .options(
            joinedload(WarrantyCertificate.customer),
            joinedload(WarrantyCertificate.owned_vehicle),
        )
        .order_by(WarrantyCertificate.created_at.desc())
        .all()
    )
    return [WarrantyCertificateOut.from_model(r) for r in rows]


def list_recalls(db: Session) -> list[RecallCampaignOut]:
    rows = db.query(RecallCampaign).order_by(RecallCampaign.issued_at.desc()).all()
    results: list[RecallCampaignOut] = []
    for recall in rows:
        affected = (
            db.query(func.count(RecallVehicle.id)).filter(RecallVehicle.recall_id == recall.id).scalar() or 0
        )
        notified = (
            db.query(func.count(RecallVehicle.id))
            .filter(RecallVehicle.recall_id == recall.id, RecallVehicle.notified_at.isnot(None))
            .scalar()
            or 0
        )
        completed = (
            db.query(func.count(RecallVehicle.id))
            .filter(RecallVehicle.recall_id == recall.id, RecallVehicle.service_completed_at.isnot(None))
            .scalar()
            or 0
        )
        results.append(RecallCampaignOut.from_model(recall, affected=affected, notified=notified, completed=completed))
    return results


def _recall_out(db: Session, recall: RecallCampaign) -> RecallCampaignOut:
    affected = db.query(func.count(RecallVehicle.id)).filter(RecallVehicle.recall_id == recall.id).scalar() or 0
    notified = (
        db.query(func.count(RecallVehicle.id))
        .filter(RecallVehicle.recall_id == recall.id, RecallVehicle.notified_at.isnot(None))
        .scalar()
        or 0
    )
    completed = (
        db.query(func.count(RecallVehicle.id))
        .filter(RecallVehicle.recall_id == recall.id, RecallVehicle.service_completed_at.isnot(None))
        .scalar()
        or 0
    )
    return RecallCampaignOut.from_model(recall, affected=affected, notified=notified, completed=completed)


def create_recall(db: Session, payload: RecallCreateIn, *, created_by_id: str | None) -> RecallCampaignOut:
    existing = (
        db.query(RecallCampaign).filter(RecallCampaign.reference_code == payload.reference_code.strip()).one_or_none()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reference code already exists")

    try:
        severity = RecallSeverity(payload.severity.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid severity") from exc

    recall = RecallCampaign(
        reference_code=payload.reference_code.strip(),
        title=payload.title.strip(),
        description=payload.description.strip(),
        severity=severity,
        affected_models=[m.strip() for m in payload.affected_models if m.strip()],
        affected_year_from=payload.affected_year_from,
        affected_year_to=payload.affected_year_to,
        is_active=True,
        created_by_id=created_by_id,
    )
    db.add(recall)
    db.flush()

    vehicle_query = db.query(OwnedVehicle).join(User, OwnedVehicle.user_id == User.id).filter(
        User.role == UserRole.customer
    )
    if recall.affected_models:
        vehicle_query = vehicle_query.filter(OwnedVehicle.model.in_(recall.affected_models))
    if recall.affected_year_from is not None:
        vehicle_query = vehicle_query.filter(OwnedVehicle.year >= recall.affected_year_from)
    if recall.affected_year_to is not None:
        vehicle_query = vehicle_query.filter(OwnedVehicle.year <= recall.affected_year_to)

    for vehicle in vehicle_query.all():
        db.add(
            RecallVehicle(
                recall_id=recall.id,
                owned_vehicle_id=vehicle.id,
                user_id=vehicle.user_id,
            )
        )

    db.commit()
    db.refresh(recall)
    return _recall_out(db, recall)


def notify_recall(db: Session, recall_id: str) -> RecallNotifyOut:
    recall = db.get(RecallCampaign, recall_id)
    if not recall:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recall not found")

    now = datetime.now(timezone.utc)
    pending = (
        db.query(RecallVehicle)
        .filter(RecallVehicle.recall_id == recall.id, RecallVehicle.notified_at.is_(None))
        .all()
    )
    for row in pending:
        row.notified_at = now

    db.commit()
    return RecallNotifyOut(recall=_recall_out(db, recall), notifiedCount=len(pending))
