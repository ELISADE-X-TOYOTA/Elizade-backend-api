from app.core.config import DEFAULT_FROM_EMAIL, Settings, get_settings


def test_meristem_from_is_kept_unless_enforced(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@meristemng.com")
    monkeypatch.delenv("ENFORCE_ELIZADE_FROM_EMAIL", raising=False)
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "noreply@meristemng.com"
    get_settings.cache_clear()


def test_meristem_from_is_rewritten_when_enforced(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@meristemng.com")
    monkeypatch.setenv("ENFORCE_ELIZADE_FROM_EMAIL", "true")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == DEFAULT_FROM_EMAIL
    get_settings.cache_clear()


def test_elizade_from_address_is_left_alone(monkeypatch):
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@elizade.net")
    get_settings.cache_clear()
    assert Settings().smtp_from_email == "info@elizade.net"
    get_settings.cache_clear()
