from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.core.config import get_settings

settings = get_settings()

# Pool sizing is bounded by the MANAGED DATABASE, not by this process: the
# instance allows 25 connections in total, and psql sessions plus the startup
# migrations need some of those. One uvicorn worker means one pool, so 10 + 10
# leaves five spare. Raising these further just moves an outage from the pool
# to the server, where it is harder to see.
#
# Headroom is not a fix for a leak, though. Long-lived endpoints must not hold
# a session across an await — see the SSE stream and the ticket socket, both of
# which pinned a connection per client and exhausted this pool.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    # A connection idle for half an hour is likely to have been dropped by the
    # provider's proxy already; recycling beats discovering it mid-request.
    pool_recycle=1800,
    # Default is 30s. A request that cannot get a connection should fail while
    # the customer is still watching, not after they have given up — the long
    # wait is what made pool exhaustion look like a network fault to testers.
    pool_timeout=10,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
