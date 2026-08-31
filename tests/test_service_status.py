"""Pure maintenance status engine boundary tests (Phase 3)."""

from datetime import datetime, timezone

from app.domains.service.status import (
    IntervalConfig,
    LastServiceEvent,
    ThresholdConfig,
    evaluate_item_status,
    operation_qualifies,
)
from app.domains.shared.enums import ServiceIntervalKind, ServiceMaintenanceStatus, ServiceOperation

THRESHOLDS = ThresholdConfig(due_soon_km=500, due_soon_days=30, mileage_stale_days=180)
AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)
SCHEDULED = IntervalConfig(kind=ServiceIntervalKind.scheduled, interval_km=10_000, interval_months=12)
INSPECTION = IntervalConfig(kind=ServiceIntervalKind.inspection, interval_km=None, interval_months=6)


def test_no_history_is_not_on_record():
    result = evaluate_item_status(
        interval=SCHEDULED,
        last_event=None,
        current_mileage=50_000,
        mileage_recorded_at=AS_OF,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.not_on_record


def test_no_interval_configured():
    result = evaluate_item_status(
        interval=None,
        last_event=None,
        current_mileage=0,
        mileage_recorded_at=None,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.no_interval


def test_exact_km_threshold_is_due_soon_not_overdue():
    last = LastServiceEvent(
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mileage=40_000,
        operation=ServiceOperation.serviced,
    )
    result = evaluate_item_status(
        interval=SCHEDULED,
        last_event=last,
        current_mileage=49_500,
        mileage_recorded_at=AS_OF,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.due_soon


def test_one_km_over_interval_is_overdue():
    last = LastServiceEvent(
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mileage=40_000,
        operation=ServiceOperation.serviced,
    )
    result = evaluate_item_status(
        interval=SCHEDULED,
        last_event=last,
        current_mileage=50_001,
        mileage_recorded_at=AS_OF,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.overdue


def test_time_overdue_before_distance():
    last = LastServiceEvent(
        performed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        mileage=10_000,
        operation=ServiceOperation.serviced,
    )
    result = evaluate_item_status(
        interval=SCHEDULED,
        last_event=last,
        current_mileage=15_000,
        mileage_recorded_at=AS_OF,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.overdue
    assert "Time interval exceeded" in result.reason


def test_inspected_does_not_qualify_for_scheduled():
    assert not operation_qualifies(ServiceIntervalKind.scheduled, ServiceOperation.inspected)


def test_inspected_only_does_not_make_scheduled_current():
    last = LastServiceEvent(
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mileage=40_000,
        operation=ServiceOperation.inspected,
    )
    result = evaluate_item_status(
        interval=SCHEDULED,
        last_event=last,
        current_mileage=41_000,
        mileage_recorded_at=AS_OF,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.not_on_record


def test_inspection_interval_counts_inspected():
    last = LastServiceEvent(
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mileage=40_000,
        operation=ServiceOperation.inspected,
    )
    result = evaluate_item_status(
        interval=INSPECTION,
        last_event=last,
        current_mileage=41_000,
        mileage_recorded_at=AS_OF,
        as_of=datetime(2026, 2, 1, tzinfo=timezone.utc),
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.current


def test_decreasing_odometer_is_not_on_record():
    last = LastServiceEvent(
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mileage=40_000,
        operation=ServiceOperation.serviced,
    )
    result = evaluate_item_status(
        interval=SCHEDULED,
        last_event=last,
        current_mileage=39_000,
        mileage_recorded_at=AS_OF,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.not_on_record


def test_repair_only_has_no_interval_status():
    result = evaluate_item_status(
        interval=IntervalConfig(kind=ServiceIntervalKind.repair_only),
        last_event=None,
        current_mileage=0,
        mileage_recorded_at=None,
        as_of=AS_OF,
        thresholds=THRESHOLDS,
    )
    assert result.status == ServiceMaintenanceStatus.no_interval
