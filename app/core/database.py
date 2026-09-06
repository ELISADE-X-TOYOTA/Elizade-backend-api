from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.core.config import get_settings

settings = get_settings()

# ── Pool sizing ──────────────────────────────────────────────────────────
#
# The binding constraint is the MANAGED DATABASE, not this process: the
# instance allows 25 connections in total, and psql sessions plus the startup
# migrations need some of those.
#
# THE ARITHMETIC THAT BLOCKS HORIZONTAL SCALING:
#
#     total connections = pool_size+max_overflow  x  workers  x  replicas
#
# so the hardcoded 10+10 was fine for one worker on one replica and silently
# impossible for two — 40 wanted against a cap of 25. A second replica would
# not have failed at deploy time; it would have half-worked, and then thrown
# the same pool-timeout 500s that just caused an outage.
#
# Making it derived rather than constant means scaling out is a config change
# instead of a redesign. When these numbers stop dividing usefully (roughly
# 4+ workers), the answer is PgBouncer in transaction mode, which is what lets
# many app processes share a small server-side connection count.
#
# Headroom is not a fix for a leak, though. Long-lived endpoints must not hold
# a session across an await — see the SSE stream and the ticket socket, both of
# which pinned a connection per client and exhausted this pool.
_DB_CONNECTION_BUDGET = settings.db_connection_budget
_FANOUT = max(1, settings.web_concurrency * settings.replica_count)

# Floor of 2: below that a single slow request blocks the whole worker.
_per_process = max(2, _DB_CONNECTION_BUDGET // _FANOUT)
# Overflow is transient burst capacity, so it is charged at half the steady
# size — the budget above is what must never be exceeded when everything peaks
# at once.
_pool_size = max(1, _per_process // 2)
_max_overflow = _per_process - _pool_size

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
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
