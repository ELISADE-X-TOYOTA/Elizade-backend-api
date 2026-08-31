"""Unmapped service-history report.

Historical rows are free-text. Mapping them to catalogue items by keyword
would silently invent service events, so this module never writes.

Run:

    python -m app.jobs.report_unmapped_service_history

Staff attach lines through the API (`PUT /admin/service/history/{id}/lines`)
when the match is known. Uncertain rows stay unmapped and will later appear
as NOT_ON_RECORD.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.service.models import ServiceHistoryItem, ServiceHistoryLine

SAMPLE_LIMIT = 20


def report_unmapped_history(db: Session, *, sample_limit: int = SAMPLE_LIMIT) -> dict:
    """Count parent history rows that have zero structured lines. Read-only."""
    total = db.query(func.count(ServiceHistoryItem.id)).scalar() or 0
    mapped = (
        db.query(func.count(func.distinct(ServiceHistoryLine.history_item_id))).scalar() or 0
    )
    unmapped = total - mapped

    sample_rows = (
        db.query(ServiceHistoryItem)
        .outerjoin(ServiceHistoryLine, ServiceHistoryLine.history_item_id == ServiceHistoryItem.id)
        .filter(ServiceHistoryLine.id.is_(None))
        .order_by(ServiceHistoryItem.performed_at.desc())
        .limit(sample_limit)
        .all()
    )

    return {
        "totalHistoryRecords": total,
        "mappedRecords": mapped,
        "unmappedRecords": unmapped,
        "writesPerformed": 0,
        "keywordMatching": False,
        "note": (
            "Unmapped records are left untouched. Do not bulk-create lines from "
            "free-text descriptions. Attach lines per record when the work done "
            "is known from a reliable source."
        ),
        "unmappedSample": [
            {
                "id": row.id,
                "ownedVehicleId": row.owned_vehicle_id,
                "serviceType": row.service_type,
                "performedAt": row.performed_at.isoformat() if row.performed_at else None,
                "mileage": row.mileage,
                "description": row.description,
            }
            for row in sample_rows
        ],
    }
