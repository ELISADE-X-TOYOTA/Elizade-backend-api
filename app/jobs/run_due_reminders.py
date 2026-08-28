"""Daily reminder sweep — the entry point a scheduler actually calls.

    python -m app.jobs.run_due_reminders

WHY A COMMAND AND NOT THE HTTP ENDPOINT: `POST /admin/notifications/rules/run-due`
exists and works, but it is guarded by `CurrentAdmin`. Pointing a cron at it
means minting a long-lived admin JWT and parking it in an environment variable
where every deploy log and shell session can see it — a standing
administrator credential whose only job is to trigger a task the container can
already perform itself. This runs in the same image, with the same database
URL, and needs no credential at all.

The HTTP endpoint stays for manual "run it now" from the admin portal.

EXIT CODES
  0  the sweep ran and every rule succeeded
  1  the sweep could not run at all — no database, bad configuration
  2  the sweep ran but at least one rule failed

2 EXISTS BECAUSE 0 WAS A LIE. `evaluate_due_rules` deliberately swallows
per-rule failures so one broken rule cannot stop the rest — which meant the
job exited 0 on a run where every rule errored and not a single notification
went out. A scheduled task that reports success while doing nothing is worse
than one that fails loudly: nothing pages anyone, and the silence looks
exactly like "no reminders were due".

A rule that raises still must not abort the others, so per-rule errors are
collected and logged: one misconfigured marketing rule should not stop every
service reminder in the country. It just no longer counts as success.
"""

from __future__ import annotations

import json
import logging
import sys

from app.core.database import SessionLocal

# EVERY model, before anything touches a mapper.
#
# `main.py` does this for the web process; a standalone job does not go through
# it, and importing only what this module names leaves SQLAlchemy's registry
# half-populated. The sweep then dies resolving `OwnedVehicle.appointments`
# because `ServiceAppointment` was never imported — a failure that appears
# only when the job runs on its own, which is the one way it ever runs.
from app.domains.registry import *  # noqa: F401,F403 — register all ORM models
from app.domains.notifications.service import evaluate_due_rules

logger = logging.getLogger("elizade.jobs.reminders")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # The job runs in the same image as the API but not necessarily after it.
    # Ensuring the schema here means a fresh environment can run the sweep
    # without first booting the web process — and it is how the missing
    # `reminder_dispatches` table announced itself: as a rule error on a run
    # that still exited 0.
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
        summary = evaluate_due_rules(db)
    except Exception:
        logger.exception("reminder sweep failed")
        return 1
    finally:
        db.close()

    # One structured line, so a log aggregator can chart notification volume
    # and alert on `errors` without parsing prose.
    logger.info("reminder sweep complete %s", json.dumps(summary, default=str))

    errors = summary.get("errors", [])
    for message in errors:
        logger.warning("rule error: %s", message)

    # Partial failure is still failure. See the module docstring.
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
