from app.core.config import Settings, get_settings


def test_meristem_from_address_is_used_as_configured(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@meristemng.com")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "noreply@meristemng.com"
    get_settings.cache_clear()


def test_elizade_from_address_is_left_alone(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@elizade.net")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "info@elizade.net"
    get_settings.cache_clear()
