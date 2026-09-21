from app.core.config import DEFAULT_FROM_EMAIL, Settings, get_settings


def test_meristem_from_address_is_rewritten_to_elizade(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@meristemng.com")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == DEFAULT_FROM_EMAIL
    get_settings.cache_clear()


def test_elizade_from_address_is_left_alone(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@elizade.net")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "info@elizade.net"
    get_settings.cache_clear()
