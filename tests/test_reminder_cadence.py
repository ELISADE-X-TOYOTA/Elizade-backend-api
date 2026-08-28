"""Reminder escalation timing.

No database: this is the arithmetic that decides whether a customer is told
their service is due once, four times, or every day forever. It deserves to be
checkable in a second.

The bug this guards against is real and was live: the due-soon query had no
lower bound and no sent-log, so every overdue vehicle matched on every run. A
daily cron pointed at that would have mailed the same owner every day
indefinitely.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.notifications.cadence import (
    DEFAULT_STAGES,
    OVERDUE_STAGE,
    days_until,
    parse_stages,
    stage_for,
    stage_label,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def due_in(days: float) -> datetime:
    return NOW + timedelta(days=days)


# ── Day counting ─────────────────────────────────────────────────────────


def test_counts_calendar_days_not_24_hour_blocks():
    """Otherwise one vehicle fires two different stages on the same date."""
    morning = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    evening = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)
    tomorrow_early = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)

    assert days_until(tomorrow_early, morning) == 1
    assert days_until(tomorrow_early, evening) == 1


def test_naive_datetimes_are_treated_as_utc():
    naive = datetime(2026, 9, 8, 12, 0)
    assert days_until(naive, NOW) == 7


# ── Stage selection ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "days,expected",
    [
        (60, None),   # too early to say anything
        (31, None),   # one day outside the widest window
        (30, 30),     # exactly on the first step
        (29, 30),     # inside the 30 band
        (8, 30),
        (7, 7),       # exactly on the second step
        (2, 7),
        (1, 1),
        (0, 0),       # due today
    ],
)
def test_stage_boundaries(days, expected):
    assert stage_for(due_in(days), NOW) == expected


def test_the_tightest_stage_wins():
    """A vehicle 3 days out has passed 30 and 7; the urgent copy is the useful one."""
    assert stage_for(due_in(3), NOW) == 7


# ── Overdue ──────────────────────────────────────────────────────────────


def test_one_overdue_nudge():
    assert stage_for(due_in(-1), NOW) == OVERDUE_STAGE
    assert stage_for(due_in(-7), NOW) == OVERDUE_STAGE


def test_overdue_reminders_stop():
    """THE bug this module exists for: an unbounded overdue window never ends."""
    assert stage_for(due_in(-8), NOW) is None
    assert stage_for(due_in(-365), NOW) is None
    assert stage_for(due_in(-3650), NOW) is None


# ── Operator-supplied config ─────────────────────────────────────────────


def test_default_stages_match_the_concept_document():
    assert DEFAULT_STAGES == (30, 7, 1, 0)


def test_custom_stages_are_honoured():
    assert stage_for(due_in(14), NOW, (14, 3)) == 14
    assert stage_for(due_in(2), NOW, (14, 3)) == 3
    assert stage_for(due_in(20), NOW, (14, 3)) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ([30, 7, 1, 0], (30, 7, 1, 0)),
        ([1, 7, 30], (30, 7, 1)),          # sorted descending
        ([7, 7, 7], (7,)),                 # de-duplicated
        (["30", "7"], (30, 7)),            # JSON often carries strings
        ([], DEFAULT_STAGES),              # empty falls back
        (None, DEFAULT_STAGES),
        ("nonsense", DEFAULT_STAGES),
        ([-5, 900], DEFAULT_STAGES),       # every value out of range
        ([30, "bad", 7], (30, 7)),         # partial garbage keeps the good ones
    ],
)
def test_parse_stages_is_defensive(raw, expected):
    """Rule config is operator-edited JSON. One bad rule must not stop the sweep."""
    assert parse_stages(raw) == expected


# ── Copy ─────────────────────────────────────────────────────────────────


def test_labels_read_naturally():
    assert stage_label(0) == "is due today"
    assert stage_label(1) == "is due tomorrow"
    assert stage_label(30) == "is due in 30 days"
    assert stage_label(OVERDUE_STAGE) == "is overdue"


def test_no_label_says_due_in_1_days():
    """The kind of wording that makes an app look unfinished."""
    assert "1 days" not in stage_label(1)


# ── The full escalation, as a customer experiences it ────────────────────


def test_a_vehicle_is_told_exactly_four_times():
    """Walk 45 days and count the distinct stages a single vehicle hits.

    This is the property that matters: four reminders plus one overdue nudge,
    not forty-five.
    """
    due = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    seen: list[int] = []

    for offset in range(45):
        today = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=offset)
        stage = stage_for(due, today)
        # Dedup is what the sent-log does in the real run; here we only care
        # that the number of DISTINCT stages is small and bounded.
        if stage is not None and stage not in seen:
            seen.append(stage)

    assert seen == [30, 7, 1, 0, OVERDUE_STAGE], seen
