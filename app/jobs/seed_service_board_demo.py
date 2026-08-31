"""Seed demo service-board catalogue and published prices for local dashboard preview.

    python -m app.jobs.seed_service_board_demo
    python -m app.jobs.seed_service_board_demo --replace
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.core.database import SessionLocal
from app.core.seed import seed_admin_user
from app.domains.registry import *  # noqa: F401,F403 — register all ORM models
from app.domains.service.board_demo_seed import seed_service_board_demo

logger = logging.getLogger("elizade.jobs.seed_service_board_demo")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Seed demo Service Board prices for dashboard preview.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Archive the current published book and publish a fresh demo version.",
    )
    args = parser.parse_args()

    try:
        from app.core.database import engine
        from app.core.migrations import run_startup_migrations

        run_startup_migrations(engine)
    except Exception:
        logger.exception("could not prepare the database schema")
        return 1

    db = SessionLocal()
    try:
        seed_admin_user(db)
        result = seed_service_board_demo(db, replace_published=args.replace)
    except Exception:
        logger.exception("service board demo seed failed")
        return 1
    finally:
        db.close()

    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        logger.info("Skipped — use --replace to republish demo prices.")
    else:
        logger.info(
            "Published demo price book v%s (%s cells, %s items, %s models).",
            result["versionNumber"],
            result["entryCount"],
            result["itemCount"],
            result["modelCount"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
