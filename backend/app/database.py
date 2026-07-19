from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_migrations(conn):
    """Apply additive column migrations for SQLite (which lacks ALTER TABLE ADD COLUMN IF NOT EXISTS)."""
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
    ]
    for table, column, definition in new_columns:
        try:
            await conn.execute(
                __import__("sqlalchemy").text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            )
        except Exception:
            pass  # column already exists


async def init_db():
    from app.models import user, event, social, auth_tokens, organizer, community  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
