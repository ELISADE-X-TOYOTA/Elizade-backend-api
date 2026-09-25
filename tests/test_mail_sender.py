from app.core.config import Settings, get_settings


def test_default_from_address_is_elizade_info(monkeypatch):
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "elizade@elizade.net"
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
