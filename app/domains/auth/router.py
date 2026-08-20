from fastapi import APIRouter, Depends
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.auth import service
from app.domains.auth.schemas import (
    AuthTokenOut,
    EmailAvailabilityOut,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
)
from app.domains.users.schemas import UserProfileOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestOut)
def otp_request(payload: OtpRequestIn, db: Session = Depends(get_db)) -> OtpRequestOut:
    return service.request_otp(db, payload)


@router.post("/otp/verify", response_model=AuthTokenOut)
def otp_verify(payload: OtpVerifyIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    return service.verify_otp(db, payload)


@router.get("/email-available", response_model=EmailAvailabilityOut)
def email_available(email: EmailStr, db: Session = Depends(get_db)) -> EmailAvailabilityOut:
    """Read-only pre-check so the signup form can validate as the user types.

    Deliberately side-effect free — unlike `/otp/request`, calling this does not
    dispatch a code, so it is safe to poll on input.
    """
    available, reason = service.check_email_available(db, str(email))
    return EmailAvailabilityOut(email=email, available=available, reason=reason)


@router.get("/me", response_model=UserProfileOut)
def me(current_user: CurrentUser) -> UserProfileOut:
    return service.get_me(current_user)
