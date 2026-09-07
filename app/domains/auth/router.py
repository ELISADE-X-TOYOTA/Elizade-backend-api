from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.domains.auth import service
from app.domains.auth import refresh as refresh_service
from app.domains.auth.schemas import (
    AuthTokenOut,
    EmailAvailabilityOut,
    RefreshIn,
    RefreshOut,
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


@router.post("/refresh", response_model=RefreshOut)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)) -> RefreshOut:
    """Exchange a refresh token for a fresh access/refresh pair.

    Deliberately UNAUTHENTICATED: the whole point is to be callable when the
    access token is no longer accepted. The refresh token is the credential.

    Every failure is a flat 401 with the same body. Distinguishing "expired"
    from "revoked" from "never existed" would tell an attacker probing tokens
    which guesses were close.
    """
    try:
        access, new_refresh, _user_id = refresh_service.rotate(db, payload.refresh_token)
    except refresh_service.RefreshError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )
    return RefreshOut(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
def logout(payload: RefreshIn, db: Session = Depends(get_db)) -> None:
    """Revoke the caller's session family.

    Also unauthenticated, and it returns 204 whatever happens: a sign-out that
    reports "that token was not valid" leaks token validity to anyone who asks,
    and there is no useful action the client could take with the distinction.
    """
    refresh_service.revoke(db, payload.refresh_token)
