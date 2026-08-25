"""Toyota Nigeria / Elizade warranty policy constants (elizade.net/warranty)."""

from calendar import monthrange
from datetime import datetime, timezone

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


def add_months(moment: datetime, months: int) -> datetime:
    """Advance by CALENDAR months, clamping to the end of a short month.

    31 Jan + 1 month is 28 Feb (29th in a leap year), not 3 March. Overflowing
    into the next month would push an expiry date past the term.
    """
    zero_based = moment.month - 1 + months
    year = moment.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(moment.day, monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def warranty_end_from_in_service(in_service: datetime) -> datetime:
    """End of basic cover — 36 calendar months from the in-service date.

    NOT `36 * 30` days. That is 1080 days against roughly 1096, so every
    vehicle lost its final ~16 days of cover and the app told those owners
    they were out of warranty while Toyota Nigeria's published policy still
    covered them. The policy is written in months, so the maths is too.
    """
    return add_months(in_service, BASIC_WARRANTY_MONTHS)


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
