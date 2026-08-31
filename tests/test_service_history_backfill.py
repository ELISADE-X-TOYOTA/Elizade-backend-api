"""Dry-run unmapped history report never writes."""

from datetime import datetime, timezone

from app.domains.service.backfill import report_unmapped_history
from app.domains.service.models import ServiceHistoryItem, ServiceHistoryLine
from app.domains.shared.enums import ServiceHistoryLineSource, ServiceItemGroup, ServiceOperation
from app.domains.service.models import ServiceItem


def test_report_counts_unmapped_and_writes_nothing(db_session, owned_vehicle_factory, branch, staff_user):
    vehicle = owned_vehicle_factory()
    unmapped = ServiceHistoryItem(
        owned_vehicle_id=vehicle.id,
        user_id=vehicle.user_id,
        branch_id=branch.id,
        service_type="periodic",
        performed_at=datetime.now(timezone.utc),
        mileage=10000,
        description="Oil change and inspection",
        cost=0,
    )
    mapped = ServiceHistoryItem(
        owned_vehicle_id=vehicle.id,
        user_id=vehicle.user_id,
        branch_id=branch.id,
        service_type="periodic",
        performed_at=datetime.now(timezone.utc),
        mileage=15000,
        description="Full service",
        cost=0,
    )
    item = ServiceItem(code="engine-oil-filter", name="Engine oil and filter", group=ServiceItemGroup.periodic)
    db_session.add_all([unmapped, mapped, item])
    db_session.flush()
    db_session.add(
        ServiceHistoryLine(
            history_item_id=mapped.id,
            service_item_id=item.id,
            operation=ServiceOperation.serviced,
            source=ServiceHistoryLineSource.manual_entry,
        )
    )
    db_session.commit()

    before_lines = db_session.query(ServiceHistoryLine).count()
    report = report_unmapped_history(db_session)

    assert report["totalHistoryRecords"] == 2
    assert report["mappedRecords"] == 1
    assert report["unmappedRecords"] == 1
    assert report["writesPerformed"] == 0
    assert report["keywordMatching"] is False
    assert report["unmappedSample"][0]["id"] == unmapped.id
    assert db_session.query(ServiceHistoryLine).count() == before_lines


def test_catalogue_startup_migration_is_idempotent(engine):
    from sqlalchemy import inspect

    from app.core.migrations import _create_service_catalogue_tables

    _create_service_catalogue_tables(engine)
    _create_service_catalogue_tables(engine)
    inspector = inspect(engine)
    assert inspector.has_table("service_items")
    assert inspector.has_table("service_history_lines")
    indexes = {idx["name"] for idx in inspector.get_indexes("service_history_lines")}
    assert "ix_service_history_lines_history_item_id" in indexes
    assert "ix_service_history_lines_service_item_id" in indexes
