from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

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
        ("ticket_orders", "ticket_code", "VARCHAR(36) UNIQUE"),
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
    for table, column, definition in new_columns:
        try:
            async with conn.begin_nested():
                await conn.execute(
                    __import__("sqlalchemy").text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                )
        except Exception:
            pass  # column already exists


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
        user, event, social, auth_tokens, organizer, community, scout,
    )
    from app.models import settings as settings_model  # noqa: F401

    async with engine.begin() as conn:
        tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        legacy = "users" in tables and "alembic_version" not in tables
        if legacy:
            await conn.run_sync(Base.metadata.create_all)  # tables added since it was created
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
