from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import StaffPortalUser
from app.domains.warranty import service
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

router = APIRouter(prefix="/admin/warranty", tags=["admin-warranty"])


@router.get("/summary", response_model=WarrantySummaryOut)
def get_summary(_: StaffPortalUser, db: Session = Depends(get_db)) -> WarrantySummaryOut:
    return service.get_summary(db)


@router.get("/claims", response_model=PaginatedClaimsOut)
def list_claims(
    _: StaffPortalUser,
    status: str | None = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedClaimsOut:
    return service.list_claims(db, status=status, page=page, size=size)


@router.get("/claims/{claim_id}", response_model=WarrantyClaimListItemOut)
def get_claim(claim_id: str, _: StaffPortalUser, db: Session = Depends(get_db)) -> WarrantyClaimListItemOut:
    return service.get_claim(db, claim_id)


@router.patch("/claims/{claim_id}", response_model=WarrantyClaimListItemOut)
def update_claim(
    claim_id: str,
    payload: ClaimUpdateIn,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> WarrantyClaimListItemOut:
    return service.update_claim(db, claim_id, payload)


@router.get("/owned-vehicles", response_model=list[OwnedVehicleOptionOut])
def list_owned_vehicles(
    _: StaffPortalUser,
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[OwnedVehicleOptionOut]:
    return service.list_owned_vehicle_options(db, q=q)


@router.get("/certificates", response_model=list[WarrantyCertificateOut])
def list_certificates(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[WarrantyCertificateOut]:
    return service.list_certificates(db)


@router.post("/certificates", response_model=WarrantyCertificateOut, status_code=201)
def create_certificate(
    payload: CertificateCreateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> WarrantyCertificateOut:
    return service.create_certificate(db, payload, issued_by_id=current_user.id)


@router.get("/recalls", response_model=list[RecallCampaignOut])
def list_recalls(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[RecallCampaignOut]:
    return service.list_recalls(db)


@router.post("/recalls", response_model=RecallCampaignOut, status_code=201)
def create_recall(
    payload: RecallCreateIn,
    current_user: StaffPortalUser,
    db: Session = Depends(get_db),
) -> RecallCampaignOut:
    return service.create_recall(db, payload, created_by_id=current_user.id)


@router.post("/recalls/{recall_id}/notify", response_model=RecallNotifyOut)
def notify_recall(
    recall_id: str,
    _: StaffPortalUser,
    db: Session = Depends(get_db),
) -> RecallNotifyOut:
    return service.notify_recall(db, recall_id)
