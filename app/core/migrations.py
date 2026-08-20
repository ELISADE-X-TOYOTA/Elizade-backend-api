"""Lightweight startup migrations for dev databases without Alembic."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _ensure_jsonb_column(engine: Engine, table: str, column: str) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table):
        return
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {column} JSONB NOT NULL DEFAULT '[]'::jsonb")
        )


def run_startup_migrations(engine: Engine) -> None:
    _add_users_other_name(engine)
    _migrate_otp_to_email(engine)
    _add_ticket_message_attachments(engine)


def _add_ticket_message_attachments(engine: Engine) -> None:
    """Media URLs attached to a support reply.

    Backfilled to '[]' and set NOT NULL so existing rows read as "no
    attachments" rather than NULL — the service treats the column as a list
    unconditionally, and a NULL would surface as a 500 on old messages.
    """
    inspector = inspect(engine)
    if not inspector.has_table("ticket_messages"):
        return
    columns = {col["name"] for col in inspector.get_columns("ticket_messages")}
    if "attachments" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE ticket_messages ADD COLUMN attachments JSONB"))
        conn.execute(text("UPDATE ticket_messages SET attachments = '[]'::jsonb WHERE attachments IS NULL"))
        conn.execute(text("ALTER TABLE ticket_messages ALTER COLUMN attachments SET DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE ticket_messages ALTER COLUMN attachments SET NOT NULL"))


def _add_users_other_name(engine: Engine) -> None:
    """Optional middle/other name captured during registration."""
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "other_name" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN other_name VARCHAR(100)"))


def _migrate_otp_to_email(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("otp_challenges"):
        return

    columns = {col["name"] for col in inspector.get_columns("otp_challenges")}
    if "email" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE otp_challenges ADD COLUMN email VARCHAR(255)"))
        if "phone_normalized" in columns:
            conn.execute(
                text(
                    "UPDATE otp_challenges SET email = phone_normalized || '@legacy.elizade.local' "
                    "WHERE email IS NULL"
                )
            )
            conn.execute(text("ALTER TABLE otp_challenges DROP COLUMN phone_normalized"))
        conn.execute(text("UPDATE otp_challenges SET email = 'legacy@elizade.local' WHERE email IS NULL"))
        conn.execute(text("ALTER TABLE otp_challenges ALTER COLUMN email SET NOT NULL"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_otp_challenges_email ON otp_challenges (email)"))
