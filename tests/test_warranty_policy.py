"""Basic-warranty term arithmetic.

Toyota Nigeria publishes the term as "36 months or 100,000 km, whichever comes
first" (elizade.net/warranty). It was previously computed as `36 * 30` days —
1080 against roughly 1096 — so every vehicle lost its last ~16 days of cover
and the app told those owners they were out of warranty while the published
policy still covered them.

These are pure date maths, so they need no database.
"""

from datetime import datetime, timezone

import pytest

from app.domains.warranty.policy import (
    BASIC_WARRANTY_KM,
    BASIC_WARRANTY_MONTHS,
    add_months,
    is_within_basic_warranty,
    warranty_end_from_in_service,
)

UTC = timezone.utc


def d(y: int, m: int, day: int) -> datetime:
    return datetime(y, m, day, tzinfo=UTC)


# ── The published term ───────────────────────────────────────────────────


def test_the_term_matches_the_published_policy():
    assert BASIC_WARRANTY_MONTHS == 36
    assert BASIC_WARRANTY_KM == 100_000


@pytest.mark.parametrize(
    "in_service,expected",
    [
        (d(2023, 1, 15), d(2026, 1, 15)),
        (d(2022, 3, 1), d(2025, 3, 1)),
        (d(2021, 12, 31), d(2024, 12, 31)),
        (d(2023, 6, 30), d(2026, 6, 30)),
    ],
)
def test_cover_ends_on_the_same_calendar_day_three_years_on(in_service, expected):
    assert warranty_end_from_in_service(in_service) == expected


def test_a_leap_day_clamps_to_the_end_of_february():
    """29 Feb 2024 + 36 months lands in 2027, which has no 29th."""
    assert warranty_end_from_in_service(d(2024, 2, 29)) == d(2027, 2, 28)


def test_month_end_never_overflows_into_the_next_month():
    """31 Jan + 1 month is 28 Feb, not 3 March — overflow would extend the term."""
    assert add_months(d(2023, 1, 31), 1) == d(2023, 2, 28)
    assert add_months(d(2024, 1, 31), 1) == d(2024, 2, 29)


def test_the_term_is_not_1080_days():
    """Guards the specific regression: 36 * 30 is not 36 months."""
    start = d(2023, 1, 15)
    assert (warranty_end_from_in_service(start) - start).days > 1090


# ── Eligibility: whichever comes first ───────────────────────────────────


def test_covered_on_the_final_day_of_the_term():
    """The 16-day shortfall showed up exactly here."""
    start = d(2023, 1, 15)
    eligible, reason = is_within_basic_warranty(
        in_service_date=start, current_mileage=20_000, as_of=d(2026, 1, 15)
    )
    assert eligible is True, reason


def test_not_covered_the_day_after_the_term_ends():
    eligible, reason = is_within_basic_warranty(
        in_service_date=d(2023, 1, 15), current_mileage=20_000, as_of=d(2026, 1, 16)
    )
    assert eligible is False
    assert reason


def test_mileage_ends_cover_even_inside_the_period():
    """"Whichever comes first" — a young vehicle can still be out on distance."""
    eligible, reason = is_within_basic_warranty(
        in_service_date=d(2025, 1, 1), current_mileage=120_000, as_of=d(2025, 6, 1)
    )
    assert eligible is False
    assert "100,000" in (reason or "")


def test_covered_exactly_at_the_mileage_limit():
    eligible, _ = is_within_basic_warranty(
        in_service_date=d(2025, 1, 1), current_mileage=BASIC_WARRANTY_KM, as_of=d(2025, 6, 1)
    )
    assert eligible is True


def test_missing_in_service_date_is_not_covered_and_says_why():
    eligible, reason = is_within_basic_warranty(in_service_date=None, current_mileage=0)
    assert eligible is False
    assert reason


def test_a_naive_in_service_date_is_treated_as_utc():
    """Seed and import data is not always timezone-aware; it must not crash."""
    eligible, _ = is_within_basic_warranty(
        in_service_date=datetime(2025, 1, 1), current_mileage=1_000, as_of=d(2025, 6, 1)
    )
    assert eligible is True
