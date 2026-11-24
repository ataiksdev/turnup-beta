"""Alembic environment: async engine, URL from app settings, batch mode on SQLite."""
import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base
from app.models import (  # noqa: F401  (register every table on Base.metadata)
    auth_tokens, community, event, organizer, scout, social, user,
)
from app.models import settings as settings_model  # noqa: F401

target_metadata = Base.metadata


def _url() -> str:
    # Allows `alembic -x url=...` for one-off runs against another database.
    return context.get_x_argument(as_dictionary=True).get("url") or settings.database_url


def _include_object(obj, name, type_, reflected, compare_to):
    # Postgres-only search indexes on expressions (migration 0009, app/services/search.py).
    # The models can't describe them, so they'd otherwise show up as "removed" on every check.
    if type_ == "index" and reflected and compare_to is None and (name or "").startswith("ix_search_"):
        return False
    return True


def _configure(connection=None, url=None):
    is_sqlite = (url or str(connection.engine.url)).startswith("sqlite")
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=_include_object,
        # SQLite can't ALTER most things in place; batch mode copies the table instead.
        render_as_batch=is_sqlite,
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    _configure(url=_url())
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
