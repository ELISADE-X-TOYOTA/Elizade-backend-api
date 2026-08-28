"""Which reminder stage a vehicle is in, and whether it is due to be sent.

Pure functions with the clock injected, because every bug in reminder
scheduling is an off-by-one at a boundary — the vehicle due in exactly 7 days,
the one that just tipped overdue, the one serviced this morning — and none of
those are reachable by hand on the day you happen to be testing.

The concept document specifies an escalation cadence of 30 / 7 / 1 / 0 days
before the due date. The rule engine previously understood a single
`days_before` window, so a customer either got one reminder or, once a daily
cron existed, got the same one every day until they acted.
"""

from __future__ import annotations

from datetime import datetime, timezone

#: Escalation steps, in days before the service is due. Descending, because
#: `stage_for` returns the FIRST step a vehicle has reached and a vehicle 3
#: days out has also passed the 30 and 7 marks.
DEFAULT_STAGES: tuple[int, ...] = (30, 7, 1, 0)

#: One follow-up after the date passes, then silence. An unbounded overdue
#: nudge is how a reminder becomes spam: the customer who is never going to
#: book does not need telling every day for the rest of the vehicle's life.
OVERDUE_STAGE = -7


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def days_until(due: datetime, now: datetime) -> int:
    """Whole days from `now` to `due`, rounded toward the due date.

    Calendar days, not 24-hour blocks: a service due at 09:00 tomorrow is "1
    day away" whether it is 08:00 or 23:00 today. Comparing raw timedeltas
    would call the same vehicle 1 day out in the morning and 0 in the evening,
    and fire two different stages on one date.
    """
    due_day = _as_utc(due).date()
    now_day = _as_utc(now).date()
    return (due_day - now_day).days


def stage_for(due: datetime, now: datetime, stages: tuple[int, ...] = DEFAULT_STAGES) -> int | None:
    """The cadence step this vehicle currently sits in, or None if too early.

    Returns the tightest step reached. A vehicle 3 days out is past both the
    30- and 7-day marks, and the useful message is the urgent one — sending
    the 30-day copy to someone with 3 days left would be actively misleading.
    """
    remaining = days_until(due, now)

    if remaining < 0:
        # Overdue: one nudge inside the follow-up window, then nothing.
        return OVERDUE_STAGE if remaining >= OVERDUE_STAGE else None

    reached = [s for s in stages if remaining <= s]
    # Not yet inside the widest window.
    if not reached:
        return None
    return min(reached)


def stage_label(stage: int) -> str:
    """Human phrasing for the stage, used in the reminder body."""
    if stage == 0:
        return "is due today"
    if stage < 0:
        return "is overdue"
    if stage == 1:
        return "is due tomorrow"
    return f"is due in {stage} days"


def parse_stages(raw: object) -> tuple[int, ...]:
    """Read a rule's configured stages, falling back to the default.

    Rule config is operator-edited JSON, so it is validated rather than
    trusted: a malformed `stages` value must not stop the whole sweep for
    every other rule.
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        return DEFAULT_STAGES
    cleaned: list[int] = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 365:
            cleaned.append(value)
    if not cleaned:
        return DEFAULT_STAGES
    return tuple(sorted(set(cleaned), reverse=True))
