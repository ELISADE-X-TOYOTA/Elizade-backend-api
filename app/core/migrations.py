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
    _create_notification_tables(engine)
    _add_lead_customer_tracking(engine)
    _create_refresh_tokens(engine)
    _add_ticket_message_read_at(engine)
    _create_reminder_dispatches(engine)
    _create_service_catalogue_tables(engine)
    _create_service_price_book_tables(engine)
    _create_service_maintenance_tables(engine)


def _add_lead_customer_tracking(engine: Engine) -> None:
    """Customer-visible lead notes, plus the status-event history table.

    `is_customer_visible` is backfilled to FALSE, which is the point: every
    note that already exists was written as internal staff commentary, and
    switching customer lead tracking on must not publish it retroactively.
    """
    from app.domains.leads.models import LeadStatusEvent  # noqa: PLC0415 — avoids an import cycle

    LeadStatusEvent.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    if not inspector.has_table("lead_notes"):
        return
    columns = {col["name"] for col in inspector.get_columns("lead_notes")}
    if "is_customer_visible" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE lead_notes ADD COLUMN is_customer_visible BOOLEAN"))
        conn.execute(text("UPDATE lead_notes SET is_customer_visible = false WHERE is_customer_visible IS NULL"))
        conn.execute(text("ALTER TABLE lead_notes ALTER COLUMN is_customer_visible SET DEFAULT false"))
        conn.execute(text("ALTER TABLE lead_notes ALTER COLUMN is_customer_visible SET NOT NULL"))


def _create_notification_tables(engine: Engine) -> None:
    """Delivery log, device tokens and per-category preferences.

    `Base.metadata.create_all` already creates these on a fresh database; this
    exists so an EXISTING dev database picks them up without a manual step.
    Idempotent — `create_all` skips tables that are already there.
    """
    from app.domains.notifications.models import (  # noqa: PLC0415 — avoid an import cycle at module load
        DeviceToken,
        NotificationDelivery,
        NotificationPreference,
    )

    for model in (NotificationDelivery, DeviceToken, NotificationPreference):
        model.__table__.create(bind=engine, checkfirst=True)


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


def _create_refresh_tokens(engine: Engine) -> None:
    """Session refresh tokens.

    Created here rather than relying on create_all so an already-deployed
    database picks it up on the next boot without a manual step.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id),
                    token_hash VARCHAR(64) NOT NULL UNIQUE,
                    family_id UUID NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    revoked_at TIMESTAMPTZ,
                    replaced_by_id UUID,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        # Lookup is by hash on every refresh; family lookup only on revocation.
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family_id ON refresh_tokens(family_id)")
        )


def _add_ticket_message_read_at(engine: Engine) -> None:
    """Read receipts for ticket messages."""
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'ticket_messages' AND column_name = 'read_at'"
            )
        ).first()
        if exists:
            return
        conn.execute(text("ALTER TABLE ticket_messages ADD COLUMN read_at TIMESTAMPTZ"))


def _create_reminder_dispatches(engine: Engine) -> None:
    """The sent-log that makes a daily reminder sweep safe to run.

    Creating it EMPTY is deliberate and worth stating: there is no history to
    backfill, because no sweep has ever run. The first run after this deploys
    will therefore send each in-window vehicle its current stage once, which is
    the intended behaviour — those customers have never been reminded at all.
    """
    from app.domains.notifications.models import ReminderDispatch  # noqa: PLC0415

    ReminderDispatch.__table__.create(bind=engine, checkfirst=True)


def _create_service_catalogue_tables(engine: Engine) -> None:
    """Service-item catalogue and structured history lines.

    Additive only. Existing `service_history_items` rows are left untouched —
    they simply have zero child lines until staff attach them. `create` with
    `checkfirst` is a no-op on a fresh database where `create_all` already
    built the tables.
    """
    from app.domains.service.models import ServiceHistoryLine, ServiceItem  # noqa: PLC0415

    ServiceItem.__table__.create(bind=engine, checkfirst=True)
    ServiceHistoryLine.__table__.create(bind=engine, checkfirst=True)


def _create_service_price_book_tables(engine: Engine) -> None:
    from app.domains.service.models import (  # noqa: PLC0415
        ServiceBoardVehicleModel,
        ServicePriceBookEntry,
        ServicePriceBookVersion,
    )

    ServiceBoardVehicleModel.__table__.create(bind=engine, checkfirst=True)
    ServicePriceBookVersion.__table__.create(bind=engine, checkfirst=True)
    ServicePriceBookEntry.__table__.create(bind=engine, checkfirst=True)


def _create_service_maintenance_tables(engine: Engine) -> None:
    from app.domains.service.models import (  # noqa: PLC0415
        ServiceBoardSettings,
        ServiceInterval,
    )

    ServiceBoardSettings.__table__.create(bind=engine, checkfirst=True)
    ServiceInterval.__table__.create(bind=engine, checkfirst=True)
