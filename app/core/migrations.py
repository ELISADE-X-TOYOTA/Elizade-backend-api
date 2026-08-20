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
    _ensure_jsonb_column(engine, "trade_in_requests", "photo_urls")
    _ensure_jsonb_column(engine, "warranty_claims", "attachment_urls")

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
