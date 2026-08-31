"""Dry-run report of service history without structured line items.

    python -m app.jobs.report_unmapped_service_history

READ-ONLY. There is no write flag. Keyword matching is not implemented and
must not be added as a silent default — false positives would show as
completed work on the maintenance board.
"""

from __future__ import annotations

import json
import logging
import sys

from app.core.database import SessionLocal
from app.domains.registry import *  # noqa: F401,F403 — register all ORM models
from app.domains.service.backfill import report_unmapped_history

logger = logging.getLogger("elizade.jobs.service_history_backfill")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        from app.core.database import engine
        from app.core.migrations import run_startup_migrations

        run_startup_migrations(engine)
    except Exception:
        logger.exception("could not prepare the database schema")
        return 1

    try:
        db = SessionLocal()
    except Exception:
        logger.exception("could not open a database session")
        return 1

    try:
        report = report_unmapped_history(db)
    except Exception:
        logger.exception("unmapped history report failed")
        return 1
    finally:
        db.close()

    print(json.dumps(report, default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
