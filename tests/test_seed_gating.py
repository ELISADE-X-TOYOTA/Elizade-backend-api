"""`SEED_DEMO_DATA` gates demo content — and only demo content.

The admin account must survive the gate. It is the only way into the admin
portal, so a deployment that skips it is locked out of its own back office;
that is the failure this pins down.
"""

import pytest

from app.core import seed as seed_module
from app.core.config import get_settings
from app.domains.inventory.models import Vehicle
from app.domains.users.models import User, UserRole


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """`get_settings` is cached, so a monkeypatched env needs the cache cleared."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _counts(db):
    return (
        db.query(User).filter(User.role == UserRole.admin).count(),
        db.query(Vehicle).count(),
    )


def test_off_skips_demo_content(db_session, monkeypatch):
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    get_settings.cache_clear()

    seed_module.seed_all(db_session)

    admins, vehicles = _counts(db_session)
    assert admins >= 1, "the admin account must be created regardless of the flag"
    assert vehicles == 0, "demo vehicles should not appear when the flag is off"


def test_on_seeds_demo_content(db_session, monkeypatch):
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    get_settings.cache_clear()

    seed_module.seed_all(db_session)

    admins, vehicles = _counts(db_session)
    assert admins >= 1
    assert vehicles > 0, "demo vehicles should be seeded when the flag is on"


def test_default_is_off(monkeypatch):
    """Omitting the variable must not seed — a fresh production deploy is the
    case where nobody has set it."""
    monkeypatch.delenv("SEED_DEMO_DATA", raising=False)
    get_settings.cache_clear()
    assert get_settings().seed_demo_data is False


def test_admin_seed_is_idempotent(db_session, monkeypatch):
    """Boot happens repeatedly; it must not accumulate admins."""
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    get_settings.cache_clear()

    seed_module.seed_all(db_session)
    first = db_session.query(User).filter(User.role == UserRole.admin).count()
    seed_module.seed_all(db_session)
    second = db_session.query(User).filter(User.role == UserRole.admin).count()

    assert first == second == 1
