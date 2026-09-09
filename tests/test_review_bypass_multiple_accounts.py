"""The fixed-code bypass, extended from one account to a short list.

It existed for App Store and Play reviewers, who cannot receive an emailed
code. A QA tester on Outlook hit the same wall for a different reason — the
mail is accepted and then filed into Junk, because it is sent from a domain
that does not match the brand — so she needed the same door.

The list is the blast radius. Every address on it signs in with a code that
never expires, never rotates, and is SHARED between them, so the rules that
bound it matter more now than when there was one:

  * off entirely unless both settings are present
  * an explicit list, never a pattern or a domain rule
  * capped, because "just one more" is how a bounded exception stops being one
  * the account must exist and must be a customer, re-checked at every sign-in
"""

import pytest

from app.core.config import get_settings
from app.domains.auth import review_bypass
from app.domains.users.models import UserRole


@pytest.fixture
def configured(monkeypatch):
    """Two accounts sharing one code — a reviewer and a tester."""

    def _set(emails: str, code: str = "Uq39Hz"):
        monkeypatch.setenv("REVIEW_ACCOUNT_EMAIL", emails)
        monkeypatch.setenv("REVIEW_ACCOUNT_OTP", code)
        get_settings.cache_clear()
        return review_bypass

    yield _set
    get_settings.cache_clear()


# ── The list ─────────────────────────────────────────────────────────────


def test_several_addresses_are_accepted(configured):
    rb = configured("appreview@elizade.com,faith_ibitoye@outlook.com")

    assert rb.is_review_email("appreview@elizade.com")
    assert rb.is_review_email("faith_ibitoye@outlook.com")


def test_a_single_address_still_works(configured):
    """The original shape must keep working untouched."""
    rb = configured("appreview@elizade.com")

    assert rb.is_enabled()
    assert rb.is_review_email("appreview@elizade.com")
    assert not rb.is_review_email("faith_ibitoye@outlook.com")


def test_matching_ignores_case_and_padding(configured):
    rb = configured(" appreview@elizade.com , Faith_Ibitoye@Outlook.com ")

    assert rb.is_review_email("FAITH_IBITOYE@OUTLOOK.COM")
    assert rb.configured_emails() == ["appreview@elizade.com", "faith_ibitoye@outlook.com"]


def test_duplicates_collapse(configured):
    rb = configured("a@x.com,A@X.com,a@x.com")
    assert rb.configured_emails() == ["a@x.com"]


def test_nobody_else_gets_in(configured):
    """No pattern, no domain rule. A wildcard here is a front door."""
    rb = configured("appreview@elizade.com,faith_ibitoye@outlook.com")

    for stranger in [
        "attacker@elizade.com",
        "faith_ibitoye@outlook.com.evil.test",
        "@outlook.com",
        "faith_ibitoye@gmail.com",
        "",
    ]:
        assert not rb.is_review_email(stranger), stranger


# ── Still off by default, still bounded ──────────────────────────────────


def test_off_when_unconfigured(monkeypatch):
    monkeypatch.setenv("REVIEW_ACCOUNT_EMAIL", "")
    monkeypatch.setenv("REVIEW_ACCOUNT_OTP", "")
    get_settings.cache_clear()

    assert not review_bypass.is_enabled()
    assert not review_bypass.is_review_email("appreview@elizade.com")
    assert not review_bypass.code_matches("Uq39Hz")
    get_settings.cache_clear()


def test_a_list_without_a_code_is_refused(configured):
    rb = configured("a@x.com,b@y.com", code="")
    assert not rb.is_enabled()
    assert rb.validate_configuration(), "half-configured must be reported"


def test_the_list_is_capped(configured):
    too_many = ",".join(f"tester{n}@elizade.com" for n in range(review_bypass.MAX_BYPASS_ACCOUNTS + 1))
    rb = configured(too_many)

    problems = rb.validate_configuration()
    assert problems, "an unbounded list must be refused at startup"
    assert any("at most" in p for p in problems), problems


def test_exactly_the_cap_is_allowed(configured):
    ok = ",".join(f"tester{n}@elizade.com" for n in range(review_bypass.MAX_BYPASS_ACCOUNTS))
    assert configured(ok).validate_configuration() == []


def test_a_malformed_entry_is_refused(configured):
    problems = configured("appreview@elizade.com,not-an-email").validate_configuration()
    assert any("not an email" in p for p in problems), problems


def test_the_length_rule_still_applies(configured):
    """Length is still enforced — the OTP screen has exactly six boxes.

    The all-digit rule is NOT enforced any more: the bypass branch is rate
    limited now, so digits are a weaker choice rather than an unsafe one. See
    `test_bypass_throttle.py`.
    """
    assert any("characters" in p for p in configured("a@x.com", code="Uq39Hzz").validate_configuration())
    assert configured("a@x.com", code="334567").validate_configuration() == []


# ── The account guard, which the list does not weaken ────────────────────


def test_a_listed_address_still_needs_a_real_customer_account(
    configured, db_session, customer_user, admin_user
):
    """Being on the list is not enough — and never lets the code reach a
    privileged account, whoever is listed."""
    configured(f"{customer_user.email},{admin_user.email}")

    assert review_bypass.may_bypass(customer_user) is True
    assert review_bypass.may_bypass(admin_user) is False, (
        "a listed admin must still be refused; this credential is shared with "
        "third parties"
    )
    assert review_bypass.may_bypass(None) is False


def test_a_deactivated_account_cannot_use_it(configured, db_session, customer_user):
    configured(customer_user.email)
    customer_user.is_active = False
    db_session.commit()

    assert review_bypass.may_bypass(customer_user) is False


def test_the_role_is_rechecked_not_trusted_from_config(configured, db_session, customer_user):
    """Roles change in the admin portal long after the variable was set."""
    configured(customer_user.email)
    assert review_bypass.may_bypass(customer_user) is True

    customer_user.role = UserRole.staff
    db_session.commit()

    assert review_bypass.may_bypass(customer_user) is False
