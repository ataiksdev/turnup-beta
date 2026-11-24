import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

IS_SQLITE = settings.database_url.startswith("sqlite")

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    # SQLite-only driver option; Postgres drivers reject it.
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=not IS_SQLITE,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def decrement_to_zero(column):
    """SQL expression for `column - 1`, never going below 0, evaluated in the database (so
    concurrent updates don't race). Portable: Postgres has GREATEST() but SQLite doesn't, and
    Python's max() can't compare SQL expressions at all."""
    from sqlalchemy import case
    return case((column > 0, column - 1), else_=0)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Added by migrations after the baseline (0001). A database from before migrations gets only
# the baseline schema created for missing tables; the later migrations then add these. Keep
# this in step when a migration adds a column to a baseline table or adds a table.
POST_BASELINE_COLUMNS = {
    "users": {"theme_preference", "plus_until", "show_plus_badge", "wrapped_opt_in",        # 0002, 0003
              "birth_year", "gender", "personalized_recs", "profiling_consent",            # 0008
              "profiling_consent_at", "event_alerts"},                                     # 0008, 0010
    "event_saves": {"price_seen"},                                                          # 0010
    "events": {"host_venue_id", "venue_id", "members_only", "fast_lane_enabled",            # 0003
               "allow_ticket_transfers"},
    "ticket_tiers": {"members_only", "plus_presale_ends_at", "presale_then"},               # 0003
    "ticket_orders": {"venue_id", "recovery_kobo", "admitted_count"},                       # 0003, 0004
    "platform_settings": {"venue_commission_percent", "featured_state_week_kobo",           # 0003
                          "featured_area_week_kobo", "featured_max_per_state", "featured_max_per_area",
                          "max_recovery_percent", "refund_funding_hours", "refund_suspend_days",
                          "refund_referral_days", "venue_debt_pause_days", "strike_suspend_count",
                          "dispute_window_hours", "free_photo_limit", "pro_photo_limit", "free_video_limit",
                          "pro_video_limit", "free_team_seats", "pro_team_seats", "plus_early_alert_hours",
                          "subscription_grace_days", "refund_presets"},
}


def _post_baseline_tables() -> set[str]:
    """Every table defined in app/models/venue.py (migration 0003), app/models/activity.py
    (0008), app/models/discovery.py (0009; consent_log 0012; weather_forecasts 0013) and
    app/models/sharing.py (0011)."""
    from app.models import activity, discovery, sharing, venue
    return {m.__tablename__ for mod in (venue, activity, discovery, sharing) for m in vars(mod).values()
            if isinstance(m, type) and issubclass(m, Base) and m is not Base and hasattr(m, "__tablename__")}


def baseline_metadata():
    """The models' schema minus everything added after the baseline migration."""
    from sqlalchemy import MetaData, Table, UniqueConstraint
    meta = MetaData()
    later_tables = _post_baseline_tables()
    for t in Base.metadata.sorted_tables:
        if t.name in later_tables:
            continue
        drop = POST_BASELINE_COLUMNS.get(t.name, set())
        cols = [c._copy() for c in t.columns if c.name not in drop]
        uniques = [UniqueConstraint(*[c.name for c in uc.columns])
                   for uc in t.constraints if isinstance(uc, UniqueConstraint)
                   and all(c.name not in drop for c in uc.columns) and len(uc.columns) > 1]
        Table(t.name, meta, *cols, *uniques)
    return meta


async def _legacy_column_patches(conn):
    """Only for databases created before Alembic was introduced: the app used to build its
    schema with create_all() plus this list of ADD COLUMNs at every startup. Brings such a
    database up to the baseline schema so it can be stamped and handed over to Alembic.
    Each statement runs in its own SAVEPOINT -- on Postgres a failed statement (column
    already exists) would otherwise abort the whole transaction."""
    new_columns = [
        ("events", "event_type", "VARCHAR(20) NOT NULL DEFAULT 'physical'"),
        ("events", "meeting_url", "VARCHAR(500)"),
        ("ticket_orders", "payment_reference", "VARCHAR(100)"),
        ("ticket_orders", "payment_channel", "VARCHAR(30)"),
        ("users", "display_name", "VARCHAR(80)"),
        ("events", "series_id", "VARCHAR(36)"),
        ("users", "city", "VARCHAR(100)"),
        ("users", "price_sensitivity", "VARCHAR(20)"),
        ("users", "event_format_pref", "VARCHAR(20)"),
        ("users", "goes_out_when", "VARCHAR(20)"),
        # No UNIQUE here: SQLite can't add a UNIQUE column (it raised, and the column was never
        # added); uniqueness comes from the index created below, as in the baseline schema.
        ("ticket_orders", "ticket_code", "VARCHAR(36)"),
        ("ticket_orders", "checked_in_at", "DATETIME"),
        ("events", "review_status", "VARCHAR(20) NOT NULL DEFAULT 'approved'"),
        ("events", "review_note", "TEXT"),
        ("events", "reviewed_by_id", "VARCHAR(36)"),
        ("events", "reviewed_at", "DATETIME"),
        ("events", "created_via", "VARCHAR(20) NOT NULL DEFAULT 'manual'"),
        ("ticket_orders", "idempotency_key", "VARCHAR(64)"),
        ("events", "refund_policy", "TEXT"),
        ("ticket_orders", "platform_fee_percent", "FLOAT"),
        ("ticket_orders", "platform_fee_amount", "FLOAT"),
        ("organizer_profiles", "verification_status", "VARCHAR(20) NOT NULL DEFAULT 'none'"),
        ("organizer_profiles", "verification_note", "TEXT"),
        ("organizer_profiles", "verification_requested_at", "DATETIME"),
        ("organizer_profiles", "reviewed_by_id", "VARCHAR(36)"),
        ("organizer_profiles", "reviewed_at", "DATETIME"),
    ]
    from sqlalchemy import text
    for table, column, definition in new_columns:
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        except Exception as exc:
            # Expected when the column is already there. Anything else must not pass silently:
            # the database would be stamped as up to date without the column.
            if not _is_duplicate_column(exc):
                logger.error("Upgrading the legacy database: couldn't add %s.%s: %s", table, column, exc)
    try:
        async with conn.begin_nested():
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_ticket_orders_ticket_code ON ticket_orders (ticket_code)"))
    except Exception as exc:
        logger.error("Upgrading the legacy database: couldn't index ticket_orders.ticket_code: %s", exc)


def _is_duplicate_column(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "duplicate column" in msg or "already exists" in msg


async def _ensure_scout_bot(session):
    import uuid
    from sqlalchemy import select
    from app.config import settings
    from app.models.user import User

    existing = (await session.execute(
        select(User).where(User.username == settings.scout_bot_username)
    )).scalar_one_or_none()
    if existing:
        return
    session.add(User(
        id=str(uuid.uuid4()),
        username=settings.scout_bot_username,
        full_name="Turnup Scout",
        hashed_password=None,  # bot account: cannot log in, only used internally by the scout job
        role="moderator",
        is_active=True,
        is_verified=True,
    ))
    await session.commit()


async def _ensure_platform_settings(session):
    from sqlalchemy import select
    from app.models.settings import PLATFORM_SETTINGS_ID, PlatformSettings

    existing = (await session.execute(
        select(PlatformSettings).where(PlatformSettings.id == PLATFORM_SETTINGS_ID)
    )).scalar_one_or_none()
    if existing:
        return
    session.add(PlatformSettings(id=PLATFORM_SETTINGS_ID))
    await session.commit()


# The first Alembic revision: the schema as it stood when migrations were introduced.
BASELINE_REVISION = "0001"


def alembic_config():
    from pathlib import Path
    from alembic.config import Config
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return cfg


async def migrate_db():
    """Bring the database schema to the latest Alembic revision.

    New database: runs every migration. Database from before migrations existed (tables but
    no alembic_version): applies the old ad-hoc column patches, stamps it at the baseline,
    then runs any newer migrations. Runs Alembic in a worker thread because its env.py drives
    its own event loop."""
    import asyncio
    from alembic import command
    from sqlalchemy import inspect

    from app.models import (  # noqa: F401
        user, event, social, auth_tokens, organizer, community, scout, venue, activity,
    )
    from app.models import settings as settings_model  # noqa: F401

    async with engine.begin() as conn:
        tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        legacy = "users" in tables and "alembic_version" not in tables
        if legacy:
            # Baseline tables added since it was created (later ones come from migrations).
            await conn.run_sync(baseline_metadata().create_all)
            await _legacy_column_patches(conn)

    cfg = alembic_config()
    if legacy:
        await asyncio.to_thread(command.stamp, cfg, BASELINE_REVISION)
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def init_db():
    await migrate_db()

    async with AsyncSessionLocal() as session:
        await _ensure_scout_bot(session)
        await _ensure_platform_settings(session)
        await ensure_marketplace_defaults(session)


async def ensure_marketplace_defaults(session):
    """Seed the places list and subscription plans if missing (idempotent)."""
    from app.services.places import ensure_areas
    from app.services.plus import ensure_plans
    await ensure_areas(session)
    await ensure_plans(session)
    await session.commit()
