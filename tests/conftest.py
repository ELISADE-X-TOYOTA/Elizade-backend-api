"""
Pytest harness for the Elizade Connect API.

Runs against a dedicated Postgres test database (the models use Postgres-only
JSONB/UUID types, so SQLite is not an option). The test DB is created
automatically if it does not exist. Each test runs inside a transaction that is
rolled back on teardown, so tests are isolated and the data never persists.
"""

import os
from decimal import Decimal

import psycopg2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.domains.branches.models import Branch
from app.domains.inventory.models import Vehicle, VehicleImage
from app.domains.registry import *  # noqa: F401,F403 — register every ORM model on Base.metadata
from app.domains.shared.enums import AvailabilityStatus, BranchType
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole
from app.main import app


def _test_database_url() -> str:
    """Derive the test DB URL: explicit env override, else `<db>_test`."""
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = make_url(get_settings().database_url)
    # NB: str(URL) masks the password as "***"; render_as_string keeps it intact.
    return base.set(database=f"{base.database}_test").render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()


def _ensure_test_database_exists() -> None:
    """Create the test database if it is missing (connects to the `postgres` db)."""
    url = make_url(TEST_DATABASE_URL)
    admin_dsn = dict(
        host=url.host or "localhost",
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        dbname="postgres",
    )
    conn = psycopg2.connect(**admin_dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        conn.close()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database_exists()
    eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    # Start from a clean schema so model changes (e.g. new columns) are always reflected.
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """A session bound to an outer transaction that is rolled back after each test.

    `join_transaction_mode="create_savepoint"` lets the service layer call
    `session.commit()` (it commits a savepoint) without ending the outer
    transaction, so isolation is preserved even though services commit.
    """
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    """TestClient with `get_db` overridden to the test session.

    Instantiated without a `with` block so the app lifespan (which would run
    create_all + admin seeding against the *production* database) never fires.
    """
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Domain fixtures                                                             #
# --------------------------------------------------------------------------- #

def _make_user(db_session, *, role: UserRole, phone: str, email: str, first: str, last: str) -> User:
    user = User(
        phone_normalized=phone,
        phone_display=f"0{phone}",
        first_name=first,
        last_name=last,
        email=email,
        role=role,
        department="Management" if role == UserRole.admin else ("Sales" if role == UserRole.staff else None),
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def branch(db_session) -> Branch:
    row = Branch(
        name="Elizade Lekki",
        type=BranchType.both,
        city="Lagos",
        state="Lagos",
        address="Lekki Phase 1, Lagos",
        phone="08000000000",
        is_active=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def admin_user(db_session) -> User:
    return _make_user(
        db_session, role=UserRole.admin, phone="8107891549",
        email="admin@elizade.test", first="Divine", last="Obinali",
    )


@pytest.fixture
def staff_user(db_session) -> User:
    return _make_user(
        db_session, role=UserRole.staff, phone="8100000002",
        email="staff@elizade.test", first="Sade", last="Adewale",
    )


@pytest.fixture
def customer_user(db_session) -> User:
    return _make_user(
        db_session, role=UserRole.customer, phone="8100000003",
        email="customer@elizade.test", first="Tunde", last="Bello",
    )


def _auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def admin_headers(admin_user) -> dict[str, str]:
    return _auth_header(admin_user)


@pytest.fixture
def staff_headers(staff_user) -> dict[str, str]:
    return _auth_header(staff_user)


@pytest.fixture
def customer_headers(customer_user) -> dict[str, str]:
    return _auth_header(customer_user)


@pytest.fixture
def vehicle_factory(db_session, branch):
    """Create persisted Vehicle rows with sensible defaults; override any field."""
    def _make(**overrides) -> Vehicle:
        defaults = dict(
            make="Toyota",
            model="Corolla",
            trim="LE",
            year=2024,
            color="White",
            color_hex="#FFFFFF",
            price=Decimal("25000000.00"),
            fuel_type="Petrol",
            transmission="Automatic",
            engine="1.8L 4-cylinder",
            availability=AvailabilityStatus.available,
            branch_id=branch.id,
            is_published=True,
            specs={},
        )
        defaults.update(overrides)
        vehicle = Vehicle(**defaults)
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)
        return vehicle

    return _make


@pytest.fixture
def image_factory(db_session):
    """Attach a persisted VehicleImage to a vehicle."""
    def _make(vehicle, **overrides) -> VehicleImage:
        defaults = dict(
            vehicle_id=vehicle.id,
            url="https://cdn.elizade.test/img.jpg",
            alt_text=None,
            sort_order=0,
            is_primary=False,
        )
        defaults.update(overrides)
        image = VehicleImage(**defaults)
        db_session.add(image)
        db_session.commit()
        db_session.refresh(image)
        return image

    return _make
