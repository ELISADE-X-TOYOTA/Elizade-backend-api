from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.customers.customer_schemas import WatchlistCreateIn, WatchlistItemOut, WatchlistUpdateIn
from app.domains.customers.models import WatchlistItem


def list_watchlist(db: Session, user_id: str) -> list[WatchlistItemOut]:
    rows = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user_id, WatchlistItem.is_active.is_(True))
        .order_by(WatchlistItem.created_at.desc())
        .all()
    )
    return [WatchlistItemOut.from_model(r) for r in rows]


def add_watchlist_item(db: Session, user_id: str, payload: WatchlistCreateIn) -> WatchlistItemOut:
    existing = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.user_id == user_id,
            WatchlistItem.model == payload.model.strip(),
            WatchlistItem.is_active.is_(True),
        )
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model already in watchlist")

    row = WatchlistItem(
        user_id=user_id,
        model=payload.model.strip(),
        trim=(payload.trim or "").strip() or None,
        color=(payload.color or "").strip() or None,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return WatchlistItemOut.from_model(row)


def update_watchlist_item(
    db: Session, user_id: str, item_id: str, payload: WatchlistUpdateIn
) -> WatchlistItemOut:
    row = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == user_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    if payload.trim is not None:
        row.trim = payload.trim.strip() or None
    if payload.color is not None:
        row.color = payload.color.strip() or None
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.commit()
    db.refresh(row)
    return WatchlistItemOut.from_model(row)


def remove_watchlist_item(db: Session, user_id: str, item_id: str) -> None:
    row = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == user_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")
    row.is_active = False
    db.commit()
