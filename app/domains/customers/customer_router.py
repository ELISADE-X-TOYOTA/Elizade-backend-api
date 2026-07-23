from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CustomerUser
from app.domains.customers import customer_service
from app.domains.customers.customer_schemas import WatchlistCreateIn, WatchlistItemOut, WatchlistUpdateIn

router = APIRouter(prefix="/watchlist", tags=["customer-watchlist"])


@router.get("", response_model=list[WatchlistItemOut])
def list_watchlist(
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> list[WatchlistItemOut]:
    return customer_service.list_watchlist(db, current_user.id)


@router.post("", response_model=WatchlistItemOut, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(
    payload: WatchlistCreateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> WatchlistItemOut:
    return customer_service.add_watchlist_item(db, current_user.id, payload)


@router.patch("/{item_id}", response_model=WatchlistItemOut)
def update_watchlist_item(
    item_id: str,
    payload: WatchlistUpdateIn,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> WatchlistItemOut:
    return customer_service.update_watchlist_item(db, current_user.id, item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watchlist_item(
    item_id: str,
    current_user: CustomerUser,
    db: Session = Depends(get_db),
) -> Response:
    customer_service.remove_watchlist_item(db, current_user.id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
