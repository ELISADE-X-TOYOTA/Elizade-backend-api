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


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


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
    in_service_date = _as_utc(in_service_date)

    end = warranty_end_from_in_service(in_service_date)
    if now > end:
        return False, "Basic warranty period has expired (36 months from in-service date)"

    if current_mileage > BASIC_WARRANTY_KM:
        return False, f"Mileage exceeds warranty limit ({BASIC_WARRANTY_KM:,} km)"

    return True, None


def battery_free_end_from_in_service(in_service: datetime) -> datetime:
    return add_months(_as_utc(in_service), BATTERY_FREE_MONTHS)


def battery_partial_end_from_in_service(in_service: datetime) -> datetime:
    return add_months(_as_utc(in_service), BATTERY_PARTIAL_MONTHS)


def battery_warranty_status(
    *,
    in_service_date: datetime | None,
    as_of: datetime | None = None,
) -> tuple[str, bool, datetime | None, datetime | None]:
    """Return (status, eligible, free_end, partial_end).

    status is one of: unknown, free, partial, expired
    eligible is True during free or partial cover (within 36 months).
    """
    if in_service_date is None:
        return "unknown", False, None, None

    now = as_of or datetime.now(timezone.utc)
    in_service = _as_utc(in_service_date)
    free_end = battery_free_end_from_in_service(in_service)
    partial_end = battery_partial_end_from_in_service(in_service)

    if now > partial_end:
        return "expired", False, free_end, partial_end
    if now > free_end:
        return "partial", True, free_end, partial_end
    return "free", True, free_end, partial_end
