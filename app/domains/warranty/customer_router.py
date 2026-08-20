from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.ownership import service as ownership_service
from app.domains.ownership.schemas import DocumentUploadOut
from app.domains.warranty import service
from app.domains.warranty.schemas import (
    ClaimCreateIn,
    CustomerRecallOut,
    WarrantyCertificateOut,
    WarrantyClaimListItemOut,
    WarrantyEligibilityOut,
)

router = APIRouter(prefix="/warranty", tags=["customer-warranty"])


@router.get("/certificates", response_model=list[WarrantyCertificateOut])
def list_my_certificates(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[WarrantyCertificateOut]:
    return service.list_customer_certificates(db, current_user.id)


@router.get("/claims", response_model=list[WarrantyClaimListItemOut])
def list_my_claims(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[WarrantyClaimListItemOut]:
    return service.list_customer_claims(db, current_user.id)


@router.get("/eligibility", response_model=WarrantyEligibilityOut)
def check_eligibility(
    current_user: CustomerUser,
    ownedVehicleId: str = Query(min_length=1),
    db: Session = Depends(get_db),
) -> WarrantyEligibilityOut:
    data = service.check_eligibility(db, current_user.id, ownedVehicleId)
    return WarrantyEligibilityOut(**data)


@router.post("/claims/attachments/upload", response_model=DocumentUploadOut)
def upload_claim_attachment(
    current_user: CustomerUser,
    file: UploadFile = File(...),
) -> DocumentUploadOut:
    return ownership_service.upload_document(file)


@router.post("/claims", response_model=WarrantyClaimListItemOut, status_code=201)
def submit_claim(
    payload: ClaimCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> WarrantyClaimListItemOut:
    return service.submit_customer_claim(db, current_user.id, payload)


@router.get("/recalls", response_model=list[CustomerRecallOut])
def list_my_recalls(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[CustomerRecallOut]:
    rows = service.list_customer_recalls(db, current_user.id)
    return [CustomerRecallOut(**r) for r in rows]
