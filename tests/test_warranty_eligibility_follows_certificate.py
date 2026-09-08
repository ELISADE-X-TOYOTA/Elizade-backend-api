"""Refusing a claim while holding the certificate that grants it.

`check_eligibility` derived cover solely from `OwnedVehicle.purchase_date`,
which is null on 23 of the 25 owned vehicles in production — including the
vehicles behind 8 of the 10 ACTIVE warranty certificates. Those customers were
shown a certificate covering them until 2028 and then refused a claim with
"In-service date is not recorded for this vehicle", while the same function
was reading that certificate two lines lower to fill in `coverageEnd`.

The record existed. The eligibility check ignored it.

Second bug in the same line: `extended` certificates carry a longer window
than the basic 36 months, and re-deriving from the in-service date silently
cut them back to the basic term.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.customers.models import OwnedVehicle
from app.domains.shared.enums import WarrantyCertificateStatus
from app.domains.warranty import service as warranty_service
from app.domains.warranty.models import WarrantyCertificate
from app.domains.warranty.policy import (
    BASIC_WARRANTY_KM,
    is_within_certificate_cover,
)

WARRANTY = "/api/v1/warranty"


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def car_without_purchase_date(db_session, customer_user):
    """The production shape: a vehicle whose in-service date was never captured."""
    car = OwnedVehicle(
        user_id=customer_user.id,
        vin="JTDBT923000444222",
        make="Toyota",
        model="Corolla",
        trim="LE",
        color="Silver",
        year=2024,
        registration_number="ELZ-444",
        mileage=12_000,
        purchase_date=None,
    )
    db_session.add(car)
    db_session.commit()
    return car


def _certificate(db_session, customer_user, car, *, months_left=18, cert_type="standard"):
    cert = WarrantyCertificate(
        user_id=customer_user.id,
        owned_vehicle_id=car.id,
        certificate_number=f"ELZ-WTY-T{months_left}{cert_type[:3].upper()}",
        type=cert_type,
        status=WarrantyCertificateStatus.active,
        coverage_start=_now() - timedelta(days=180),
        coverage_end=_now() + timedelta(days=30 * months_left),
    )
    db_session.add(cert)
    db_session.commit()
    return cert


# ── The bug ──────────────────────────────────────────────────────────────


def test_an_active_certificate_makes_the_vehicle_eligible(
    db_session, customer_user, car_without_purchase_date
):
    """THE CORE OF IT.

    A customer holding a live certificate must be able to claim on it, whether
    or not the vehicle row also carries a purchase date.
    """
    _certificate(db_session, customer_user, car_without_purchase_date)

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["eligible"] is True, result["reason"]
    assert result["reason"] is None


def test_without_the_fix_the_reason_was_the_giveaway(
    db_session, customer_user, car_without_purchase_date
):
    """The old refusal claimed ignorance of something it was about to print."""
    _certificate(db_session, customer_user, car_without_purchase_date)

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["coverageEnd"] is not None, "the certificate's window was already known"
    assert result["eligible"] is True, (
        "eligibility must not claim the in-service date is unknown while "
        f"reporting cover until {result['coverageEnd']}"
    )


def test_the_in_service_date_falls_back_to_the_certificate(
    db_session, customer_user, car_without_purchase_date
):
    """`coverage_start` IS the in-service date used when cover was issued.

    Reporting null implies nothing is known, which was never true.
    """
    cert = _certificate(db_session, customer_user, car_without_purchase_date)

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["inServiceDate"] is not None
    assert result["inServiceDate"].startswith(cert.coverage_start.strftime("%Y-%m-%d"))


def test_extended_cover_is_not_cut_back_to_the_basic_term(
    db_session, customer_user, car_without_purchase_date
):
    """An extended certificate outlasts the basic 36 months.

    Re-deriving from the in-service date would expire it early — the customer
    paid for cover the system then refused to honour.
    """
    # 48 months out: beyond basic cover, inside an extended certificate.
    _certificate(db_session, customer_user, car_without_purchase_date, months_left=48, cert_type="extended")

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["eligible"] is True, result["reason"]


# ── Still refused when it should be ──────────────────────────────────────


def test_no_certificate_and_no_purchase_date_is_still_refused(
    db_session, customer_user, car_without_purchase_date
):
    """Nothing is being loosened: with no record at all, there is no cover."""
    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["eligible"] is False
    assert "in-service" in (result["reason"] or "").lower()


def test_mileage_still_caps_a_live_certificate(
    db_session, customer_user, car_without_purchase_date
):
    """A certificate grants time, not distance.

    The cap is a limit on the cover itself, so no certificate overrides it.
    """
    car_without_purchase_date.mileage = BASIC_WARRANTY_KM + 1
    db_session.commit()
    _certificate(db_session, customer_user, car_without_purchase_date)

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["eligible"] is False
    assert "mileage" in (result["reason"] or "").lower()


def test_a_lapsed_certificate_does_not_grant_cover(db_session, customer_user, car_without_purchase_date):
    cert = _certificate(db_session, customer_user, car_without_purchase_date)
    cert.coverage_end = _now() - timedelta(days=1)
    db_session.commit()

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["eligible"] is False
    assert "expired" in (result["reason"] or "").lower()


def test_a_purchase_date_still_works_on_its_own(db_session, customer_user, car_without_purchase_date):
    """The original path is untouched for vehicles that do carry the date."""
    car_without_purchase_date.purchase_date = _now() - timedelta(days=200)
    db_session.commit()

    result = warranty_service.check_eligibility(
        db_session, customer_user.id, car_without_purchase_date.id
    )

    assert result["eligible"] is True, result["reason"]


# ── The policy rule on its own ───────────────────────────────────────────


def test_policy_refuses_an_unknown_window():
    eligible, reason = is_within_certificate_cover(coverage_end=None, current_mileage=1000)
    assert eligible is False
    assert reason


def test_policy_accepts_a_live_window():
    eligible, reason = is_within_certificate_cover(
        coverage_end=_now() + timedelta(days=1), current_mileage=1000
    )
    assert eligible is True
    assert reason is None


def test_policy_is_exact_on_the_boundary():
    """A certificate is live right up to its end, and not a moment after."""
    end = _now()
    inside, _ = is_within_certificate_cover(
        coverage_end=end, current_mileage=0, as_of=end - timedelta(seconds=1)
    )
    outside, _ = is_within_certificate_cover(
        coverage_end=end, current_mileage=0, as_of=end + timedelta(seconds=1)
    )
    assert inside is True
    assert outside is False


def test_policy_handles_a_naive_datetime():
    """Rows written without a timezone must not raise on comparison."""
    naive = datetime.now() + timedelta(days=30)
    eligible, _ = is_within_certificate_cover(coverage_end=naive, current_mileage=0)
    assert eligible is True
