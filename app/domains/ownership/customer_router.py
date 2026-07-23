from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.ownership import service
from app.domains.ownership.schemas import (
    DocumentUploadOut,
    DocumentsAppendIn,
    OwnedVehicleOut,
    OwnershipRequestCreateIn,
    OwnershipRequestOut,
    VinLookupOut,
)

router = APIRouter(prefix="/ownership", tags=["customer-ownership"])


@router.get("/lookup", response_model=VinLookupOut)
def lookup_vin(
    current_user: CustomerUser,
    vin: str = Query(min_length=11, max_length=17),
    db: Session = Depends(get_db),
) -> VinLookupOut:
    return service.lookup_vin(db, user_id=current_user.id, vin=vin)


@router.get("/vehicles", response_model=list[OwnedVehicleOut])
def list_my_vehicles(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[OwnedVehicleOut]:
    return service.list_my_vehicles(db, current_user.id)


@router.get("/requests", response_model=list[OwnershipRequestOut])
def list_my_requests(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[OwnershipRequestOut]:
    return service.list_my_requests(db, current_user.id)


@router.post("/requests", response_model=OwnershipRequestOut, status_code=201)
def submit_request(
    payload: OwnershipRequestCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> OwnershipRequestOut:
    return service.submit_request(db, current_user, payload)


@router.post("/requests/{request_id}/documents", response_model=OwnershipRequestOut)
def add_documents(
    request_id: str,
    payload: DocumentsAppendIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> OwnershipRequestOut:
    return service.append_documents(db, current_user.id, request_id, payload.document_urls)


@router.post("/documents/upload", response_model=DocumentUploadOut)
def upload_document(
    current_user: CustomerUser,
    file: UploadFile = File(...),
) -> DocumentUploadOut:
    return service.upload_document(file)
