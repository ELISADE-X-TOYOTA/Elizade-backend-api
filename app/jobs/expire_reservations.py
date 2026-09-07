"""Release vehicles whose reservation hold has lapsed.

    python -m app.jobs.expire_reservations [--dry-run]

WHY THIS EXISTS
===============
`create_reservation` sets `expires_at` seven days out and flips the vehicle to
`reserved`. Nothing ever read that column. No job, no cron, no sweep — the
expiry was recorded and then ignored, so every reservation was permanent.

The effect is not subtle. Testing alone put 12 of 30 vehicles into `reserved`,
which is 40% of the catalogue withdrawn from sale by people tapping a button to
see whether it worked. In production the same mechanism removes a car from
the showroom the moment one customer holds it and never puts it back, whether
or not they ever pay.

It also made the reserve button look broken: a second tap on a held vehicle is
refused with 409, so the flow appeared to fail for the very customer who had
just succeeded.

WHAT COUNTS AS LAPSED
=====================
Only `pending` — a hold nobody has paid for. `deposit_paid` and `confirmed`
represent money taken or a sale agreed, and releasing those would put a car
back on sale that somebody has a claim on. If those need lifecycle handling it
belongs with whoever handles refunds, not in a timeout sweep.

A vehicle is returned to `available` only when NO other active reservation
remains on it. Two holds on one car should not both have to lapse before it
comes back, and the first one to expire must not release a car the second
still holds.

EXIT CODES
  0  swept successfully (including "nothing to do")
  1  could not run at all — no database, bad configuration
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal

# Registers EVERY ORM model before any mapper is configured. Importing only
# Reservation and Vehicle is not enough: their relationships name classes from
# other modules, and SQLAlchemy resolves those lazily by name — so the first
# query raises `failed to locate a name ('User')` instead of running. `main.py`
# does the same thing for the same reason; a job entry point needs it too,
# because nothing else has imported the app.
from app.domains.registry import *  # noqa: F401,F403
from app.domains.inventory.models import Vehicle
from app.domains.sales.models import Reservation
from app.domains.shared.enums import AvailabilityStatus, ReservationStatus

logger = logging.getLogger("elizade.jobs.expire_reservations")

#: Holds that a timeout may release. See the module docstring: anything
#: representing money or an agreed sale is deliberately excluded.
_RELEASABLE = (ReservationStatus.pending,)

#: Still-live holds that keep a vehicle off the market.
_ACTIVE = (
    ReservationStatus.pending,
    ReservationStatus.deposit_paid,
    ReservationStatus.confirmed,
)


def expire_due(db: Session, *, now: datetime | None = None, dry_run: bool = False) -> tuple[int, int]:
    """Expire lapsed holds. Returns (reservations expired, vehicles released)."""
    moment = now or datetime.now(timezone.utc)

    due = (
        db.query(Reservation)
        .filter(Reservation.status.in_(_RELEASABLE), Reservation.expires_at <= moment)
        .all()
    )
    if not due:
        return (0, 0)

    released = 0
    for row in due:
        row.status = ReservationStatus.expired
        logger.info(
            "expiring reservation %s on vehicle %s (due %s)",
            row.id, row.vehicle_id, row.expires_at,
        )

    # Flush first so the status changes above are visible to the query below —
    # otherwise every vehicle still looks held by the reservation being expired
    # and nothing is ever released.
    db.flush()

    for vehicle_id in {r.vehicle_id for r in due}:
        still_held = (
            db.query(Reservation)
            .filter(Reservation.vehicle_id == vehicle_id, Reservation.status.in_(_ACTIVE))
            .first()
        )
        if still_held is not None:
            continue
        vehicle = db.get(Vehicle, vehicle_id)
        # `sold` is never walked back by a timeout: the car is gone.
        if vehicle is not None and vehicle.availability == AvailabilityStatus.reserved:
            vehicle.availability = AvailabilityStatus.available
            released += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return (len(due), released)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    dry_run = "--dry-run" in sys.argv

    try:
        db = SessionLocal()
    except Exception:  # noqa: BLE001
        logger.exception("could not open a database session")
        return 1

    try:
        expired, released = expire_due(db, dry_run=dry_run)
    except Exception:  # noqa: BLE001
        logger.exception("sweep failed")
        db.rollback()
        return 1
    finally:
        db.close()

    prefix = "[dry-run] would expire" if dry_run else "expired"
    logger.info("%s %s reservation(s); released %s vehicle(s)", prefix, expired, released)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
