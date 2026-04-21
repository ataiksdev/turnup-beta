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
    ]
    for table, column, definition in new_columns:
        try:
            await conn.execute(
                __import__("sqlalchemy").text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            )
        except Exception:
            pass  # column already exists


async def init_db():
    from app.models import user, event, social, auth_tokens, organizer  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
