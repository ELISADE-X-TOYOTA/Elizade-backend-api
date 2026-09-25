from app.core.config import Settings, get_settings


def test_default_from_address_is_elizade_info(monkeypatch):
    """One address, and it is the one Elizade publishes.

    The From address and `support_email` are now the same inbox, so a reply
    to an automated mail reaches a mailbox somebody reads — which is not true
    of a `noreply@`, and was not true of `elizade@` either.
    """
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    get_settings.cache_clear()
    # `_env_file=None` so a developer's own .env cannot answer for the
    # default. Without it this asserted whatever SMTP_FROM_EMAIL happened to
    # be in the local .env, and only passed where no .env existed.
    defaults = Settings(_env_file=None)
    assert defaults.smtp_from_email == "info@elizade.net"
    assert defaults.smtp_from_email == defaults.support_email
    get_settings.cache_clear()


def test_smtp_from_email_env_override(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@meristemng.com")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "noreply@meristemng.com"
    get_settings.cache_clear()


def test_elizade_from_address_is_left_alone(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "elizade@elizade.net")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "elizade@elizade.net"
    get_settings.cache_clear()
