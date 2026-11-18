import ipaddress
import os
import socket

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool
from app.database import Base, get_db
from app.main import app

# SQLite in memory by default. CI also runs the suite against Postgres by setting e.g.
# TEST_DATABASE_URL=postgresql+asyncpg://turnup:turnup@localhost:5432/turnup_test
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or "sqlite+aiosqlite:///:memory:"
IS_SQLITE = TEST_DB_URL.startswith("sqlite")

_real_getaddrinfo = socket.getaddrinfo


@pytest.fixture(autouse=True)
def _offline_dns(monkeypatch):
    """Keep the suite independent of real DNS (CI runners and sandboxes often have none).
    IP literals resolve as usual, so SSRF tests against 127.0.0.1 / 10.x / 169.254.x still
    exercise the real checks; any hostname resolves to a fixed public address (example.com's).
    Every outbound HTTP call in the tests is mocked, so nothing ever connects to it."""
    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
        except (TypeError, ValueError):
            if host != "localhost":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 0))]
        return _real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest_asyncio.fixture(scope="session")
async def engine():
    if IS_SQLITE:
        eng = create_async_engine(
            TEST_DB_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        eng = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with eng.begin() as conn:
        if not IS_SQLITE:
            await conn.run_sync(Base.metadata.drop_all)  # start clean on a reused database
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def pytest_collection_modifyitems(items):
    """Run every async test on the session-wide event loop the fixtures use. asyncpg
    connections are bound to the loop that opened them, so tests on their own per-test
    loops can't share the session engine with Postgres (SQLite doesn't mind either way)."""
    session_loop = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if pytest_asyncio.is_async_test(item):
            item.add_marker(session_loop, append=False)
