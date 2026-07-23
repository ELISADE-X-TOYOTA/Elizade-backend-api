"""Toyota Nigeria / Elizade warranty policy constants (elizade.net/warranty)."""

from datetime import datetime, timedelta, timezone

# Basic coverage: 36 months OR 100,000 km — whichever comes first
BASIC_WARRANTY_MONTHS = 36
BASIC_WARRANTY_KM = 100_000

DEFAULT_COVERAGE_DETAILS = [
    "Engine and transmission (defective parts under normal use)",
    "Electrical components",
    "Towing to nearest authorized dealer when warranted part fails",
    "Valid only at Toyota Nigeria accredited dealers within Nigeria",
]

BATTERY_FREE_MONTHS = 24
BATTERY_PARTIAL_MONTHS = 36


def warranty_end_from_in_service(in_service: datetime) -> datetime:
    return in_service + timedelta(days=BASIC_WARRANTY_MONTHS * 30)


def is_within_basic_warranty(
    *,
    in_service_date: datetime | None,
    current_mileage: int,
    as_of: datetime | None = None,
) -> tuple[bool, str | None]:
    """Return (eligible, reason_if_not)."""
    if in_service_date is None:
        return False, "In-service date is not recorded for this vehicle"

    now = as_of or datetime.now(timezone.utc)
    if in_service_date.tzinfo is None:
        in_service_date = in_service_date.replace(tzinfo=timezone.utc)

    end = warranty_end_from_in_service(in_service_date)
    if now > end:
        return False, "Basic warranty period has expired (36 months from in-service date)"

    if current_mileage > BASIC_WARRANTY_KM:
        return False, f"Mileage exceeds warranty limit ({BASIC_WARRANTY_KM:,} km)"

    return True, None
