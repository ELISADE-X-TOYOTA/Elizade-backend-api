"""Public read-only Service Board — no authentication (showroom / kiosk display)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.service import price_book_service, service
from app.domains.service.price_book_schemas import BoardVehicleModelOut, PriceBookBoardOut
from app.domains.service.schemas import ServiceItemOut

router = APIRouter(prefix="/service-board", tags=["service-board-public"])


@router.get("/price-book", response_model=PriceBookBoardOut)
def get_public_price_board(db: Session = Depends(get_db)) -> PriceBookBoardOut:
    """Published price matrix only — no draft prices or admin metadata."""
    return price_book_service.get_published_board(db)


@router.get("/price-book/models", response_model=list[BoardVehicleModelOut])
def list_public_board_models(db: Session = Depends(get_db)) -> list[BoardVehicleModelOut]:
    return price_book_service.list_board_models(db)


@router.get("/price-book/mileage-bands", response_model=list[int])
def list_public_mileage_bands() -> list[int]:
    return price_book_service.list_mileage_bands()


@router.get("/items", response_model=list[ServiceItemOut])
def list_public_service_items(
    db: Session = Depends(get_db),
    group: str | None = Query(default=None),
) -> list[ServiceItemOut]:
    """Active catalogue items for display on the public board."""
    return service.list_items(db, group=group, is_active=True)
