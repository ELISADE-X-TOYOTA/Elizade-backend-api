from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.auth import service
from app.domains.auth.schemas import AuthTokenOut, OtpRequestIn, OtpRequestOut, OtpVerifyIn
from app.domains.users.schemas import UserProfileOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestOut)
def otp_request(payload: OtpRequestIn, db: Session = Depends(get_db)) -> OtpRequestOut:
    return service.request_otp(db, payload)


@router.post("/otp/verify", response_model=AuthTokenOut)
def otp_verify(payload: OtpVerifyIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    return service.verify_otp(db, payload)


@router.get("/me", response_model=UserProfileOut)
def me(current_user: CurrentUser) -> UserProfileOut:
    return service.get_me(current_user)
