from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.sales import service
from app.domains.sales.schemas import (
    QuotationOut,
    QuotationRequestIn,
    ReservationCreateIn,
    ReservationOut,
    TestDriveCreateIn,
    TestDriveOut,
    TradeInCreateIn,
    TradeInOut,
)
from app.domains.ownership.schemas import DocumentUploadOut
from app.domains.ownership import service as ownership_service

router = APIRouter(prefix="/sales", tags=["customer-sales"])


@router.get("/test-drives", response_model=list[TestDriveOut])
def list_my_test_drives(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[TestDriveOut]:
    return service.list_my_test_drives(db, current_user.id)


@router.post("/test-drives", response_model=TestDriveOut, status_code=status.HTTP_201_CREATED)
def book_test_drive(
    payload: TestDriveCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> TestDriveOut:
    return service.create_test_drive(db, current_user, payload)


@router.get("/quotations", response_model=list[QuotationOut])
def list_my_quotations(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[QuotationOut]:
    return service.list_my_quotations(db, current_user.id)


@router.post("/quotations", response_model=QuotationOut, status_code=status.HTTP_201_CREATED)
def request_quotation(
    payload: QuotationRequestIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> QuotationOut:
    return service.request_quotation(db, current_user, payload)


@router.get("/reservations", response_model=list[ReservationOut])
def list_my_reservations(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[ReservationOut]:
    return service.list_my_reservations(db, current_user.id)


@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> ReservationOut:
    return service.create_reservation(db, current_user, payload)


@router.get("/trade-ins", response_model=list[TradeInOut])
def list_my_trade_ins(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[TradeInOut]:
    return service.list_my_trade_ins(db, current_user.id)


@router.post("/trade-ins/photos/upload", response_model=DocumentUploadOut)
def upload_trade_in_photo(
    current_user: CustomerUser,
    file: UploadFile = File(...),
) -> DocumentUploadOut:
    return ownership_service.upload_document(file)


@router.post("/trade-ins", response_model=TradeInOut, status_code=status.HTTP_201_CREATED)
def submit_trade_in(
    payload: TradeInCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> TradeInOut:
    return service.submit_trade_in(db, current_user, payload)
