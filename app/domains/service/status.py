"""Pure maintenance-status evaluation for the Service Board (Phase 3).

Deterministic, side-effect free, clock injected via `as_of`. Interval values
come from admin configuration — this module never invents Toyota intervals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domains.shared.enums import ServiceIntervalKind, ServiceMaintenanceStatus, ServiceOperation
from app.domains.warranty.policy import add_months


@dataclass(frozen=True)
class LastServiceEvent:
    performed_at: datetime
    mileage: int
    operation: ServiceOperation


@dataclass(frozen=True)
class IntervalConfig:
    kind: ServiceIntervalKind
    interval_km: int | None = None
    interval_months: int | None = None


@dataclass(frozen=True)
class ThresholdConfig:
    due_soon_km: int
    due_soon_days: int
    mileage_stale_days: int


@dataclass(frozen=True)
class StatusResult:
    status: ServiceMaintenanceStatus
    reason: str
    due_at_km: int | None = None
    due_at: datetime | None = None
    mileage_stale: bool = False


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _severity(status: ServiceMaintenanceStatus) -> int:
    order = {
        ServiceMaintenanceStatus.not_on_record: 0,
        ServiceMaintenanceStatus.no_interval: 0,
        ServiceMaintenanceStatus.current: 1,
        ServiceMaintenanceStatus.due_soon: 2,
        ServiceMaintenanceStatus.overdue: 3,
    }
    return order[status]


def _worst(*statuses: ServiceMaintenanceStatus) -> ServiceMaintenanceStatus:
    return max(statuses, key=_severity)


def operation_qualifies(kind: ServiceIntervalKind, operation: ServiceOperation) -> bool:
    if kind == ServiceIntervalKind.inspection:
        return operation == ServiceOperation.inspected
    if kind in (ServiceIntervalKind.condition, ServiceIntervalKind.repair_only):
        return False
    # scheduled — an inspection alone does not prove the item was serviced.
    return operation in (ServiceOperation.serviced, ServiceOperation.repaired, ServiceOperation.replaced)


def evaluate_item_status(
    *,
    interval: IntervalConfig | None,
    last_event: LastServiceEvent | None,
    current_mileage: int,
    mileage_recorded_at: datetime | None,
    as_of: datetime,
    thresholds: ThresholdConfig,
) -> StatusResult:
    """Return status + human-readable reason for one catalogue item on one vehicle."""
    as_of = _as_utc(as_of)

    if interval is None:
        return StatusResult(
            status=ServiceMaintenanceStatus.no_interval,
            reason="No maintenance interval is configured for this item and model.",
        )

    if interval.kind in (ServiceIntervalKind.condition, ServiceIntervalKind.repair_only):
        return StatusResult(
            status=ServiceMaintenanceStatus.no_interval,
            reason=f"Item is {interval.kind.value}; no proactive due/overdue status applies.",
        )

    if interval.interval_km is None and interval.interval_months is None:
        return StatusResult(
            status=ServiceMaintenanceStatus.no_interval,
            reason="Interval record exists but neither distance nor time limit is set.",
        )

    if last_event is None:
        return StatusResult(
            status=ServiceMaintenanceStatus.not_on_record,
            reason="No qualifying service history line exists for this item.",
        )

    if not operation_qualifies(interval.kind, last_event.operation):
        return StatusResult(
            status=ServiceMaintenanceStatus.not_on_record,
            reason=(
                f"Latest recorded operation is {last_event.operation.value}, which does not "
                f"count as a completed {interval.kind.value} event for this item."
            ),
        )

    if current_mileage < last_event.mileage:
        return StatusResult(
            status=ServiceMaintenanceStatus.not_on_record,
            reason="Current odometer is below the mileage recorded at the last qualifying service.",
        )

    mileage_stale = False
    if mileage_recorded_at is not None:
        age_days = (as_of - _as_utc(mileage_recorded_at)).days
        if age_days > thresholds.mileage_stale_days:
            mileage_stale = True

    last_at = _as_utc(last_event.performed_at)
    km_status: ServiceMaintenanceStatus | None = None
    time_status: ServiceMaintenanceStatus | None = None
    due_at_km: int | None = None
    due_at: datetime | None = None
    reasons: list[str] = []

    if interval.interval_km is not None:
        due_at_km = last_event.mileage + interval.interval_km
        km_remaining = due_at_km - current_mileage
        if km_remaining <= 0:
            km_status = ServiceMaintenanceStatus.overdue
            reasons.append(f"Distance interval exceeded by {-km_remaining:,} km.")
        elif km_remaining <= thresholds.due_soon_km:
            km_status = ServiceMaintenanceStatus.due_soon
            reasons.append(f"Due in {km_remaining:,} km (within {thresholds.due_soon_km:,} km threshold).")
        else:
            km_status = ServiceMaintenanceStatus.current
            reasons.append(f"{km_remaining:,} km remaining on distance interval.")

    if interval.interval_months is not None:
        due_at = add_months(last_at, interval.interval_months)
        days_remaining = (due_at - as_of).days
        if days_remaining < 0:
            time_status = ServiceMaintenanceStatus.overdue
            reasons.append(f"Time interval exceeded by {-days_remaining} days.")
        elif days_remaining <= thresholds.due_soon_days:
            time_status = ServiceMaintenanceStatus.due_soon
            reasons.append(f"Due in {days_remaining} days (within {thresholds.due_soon_days}-day threshold).")
        else:
            time_status = ServiceMaintenanceStatus.current
            reasons.append(f"{days_remaining} days remaining on time interval.")

    tracks = [s for s in (km_status, time_status) if s is not None]
    if not tracks:
        return StatusResult(status=ServiceMaintenanceStatus.no_interval, reason="No applicable interval dimension.")

    final = _worst(*tracks)
    reason = " ".join(reasons)
    if mileage_stale:
        reason += f" Odometer reading may be stale (>{thresholds.mileage_stale_days} days old)."

    return StatusResult(
        status=final,
        reason=reason,
        due_at_km=due_at_km,
        due_at=due_at,
        mileage_stale=mileage_stale,
    )
